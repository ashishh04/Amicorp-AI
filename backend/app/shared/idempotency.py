"""Idempotency-Key handling (LLD, Idempotency; blueprint section 5).

n8n retries every node, so every state-changing POST must be safe to repeat:

- same key, same body, finished    -> replay the stored response, header `Idempotent-Replayed: true`
- same key, different body         -> 409 IDEMPOTENCY_KEY_REUSED, nothing runs
- same key, first request running  -> 409 REQUEST_IN_PROGRESS with Retry-After
- no key                           -> 400 IDEMPOTENCY_KEY_REQUIRED

The key is scoped to the caller, method and path, so one caller can never replay another's response.
Redis holds a short in-flight lock as an accelerator. The guarantee is the row in ops.idempotency_key,
written in the same transaction as the state change: if Redis is down, a concurrent duplicate fails on
the primary key and replays the first response instead of running twice.

Business-key mode (POST /v1/cards): the key is the business identity (a finding's dedupe key, a
document and job, a transaction). A later request with the same key but a different body, such as the
same discrepancy found by tomorrow's scan, must return the existing resource with `created: false`
rather than 409. The service owns that lookup; this layer only serialises concurrent duplicates.
"""
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

import structlog
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Conflict, IdempotencyKeyRequired, IdempotencyKeyReused, RequestInProgress
from app.core.principal import Principal
from app.core.security import current_principal
from app.db.session import UnitOfWork, get_uow
from app.shared.audit import canonical_json
from app.shared.models import IdempotencyRecord

log = structlog.get_logger()

LOCK_TTL_SECONDS = 120
_KEY_FORMAT = re.compile(r"^[\x21-\x7e]{1,200}$")  # 1-200 printable ASCII characters, no spaces
_PK_NAME = "pk_idempotency_key"

M = TypeVar("M", bound=BaseModel)


class ConcurrentWrite(Conflict):
    code, title, retryable = "CONCURRENT_WRITE", "A concurrent request changed the same record", True

    def __init__(self) -> None:
        super().__init__(headers={"Retry-After": "1"})


@dataclass(frozen=True)
class IdempotencyContext:
    key: str
    key_hash: bytes
    request_hash: bytes
    principal: str
    route: str


async def idempotency_context(
    request: Request, principal: Principal = Depends(current_principal)
) -> IdempotencyContext:
    key = request.headers.get("idempotency-key")
    if not key:
        raise IdempotencyKeyRequired()
    if not _KEY_FORMAT.fullmatch(key):
        raise BadRequest("Idempotency-Key must be 1 to 200 printable ASCII characters without spaces")
    raw = await request.body()
    try:
        body = canonical_json(json.loads(raw)) if raw else ""
    except ValueError:
        body = raw.decode("utf-8", "replace")  # the body model will reject it with a 422
    route = request.url.path
    key_hash = hashlib.sha256("\n".join([principal.actor, request.method, route, key]).encode()).digest()
    return IdempotencyContext(
        key=key,
        key_hash=key_hash,
        request_hash=hashlib.sha256(body.encode()).digest(),
        principal=principal.actor,
        route=route,
    )


class IdempotencyStore:
    def __init__(self, redis: Redis | None) -> None:
        self._redis = redis

    async def run(
        self,
        ctx: IdempotencyContext,
        uow: UnitOfWork,
        action: Callable[[UnitOfWork], Awaitable[M]],
        status_for: Callable[[M], int],
        mode: Literal["exact", "business-key"] = "exact",
    ) -> JSONResponse:
        lock = await self._acquire(ctx)
        try:
            if mode == "business-key":
                return await self._run_business_key(lock, uow, action, status_for)
            if lock == "held":
                return await self._replay_or_in_progress(ctx, uow)
            try:
                async with uow:
                    stored = await _find(uow.session, ctx.key_hash)
                    if stored is not None:
                        return _replay(stored, ctx)
                    result = await action(uow)
                    body = result.model_dump(mode="json", by_alias=True)
                    status = status_for(result)
                    await uow.session.execute(insert(IdempotencyRecord).values(
                        key_hash=ctx.key_hash, request_hash=ctx.request_hash, principal=ctx.principal,
                        route=ctx.route, http_status=status, response=body, created_at=uow.now,
                    ))
                return JSONResponse(body, status_code=status)
            except IntegrityError as exc:
                if _constraint_name(exc) == _PK_NAME:
                    log.info("idempotency.concurrent_duplicate")
                    return await self._replay_or_in_progress(ctx, uow)
                raise ConcurrentWrite() from exc
        finally:
            if lock == "acquired":
                await self._release(ctx)

    async def _run_business_key(
        self,
        lock: Literal["acquired", "held", "unavailable"],
        uow: UnitOfWork,
        action: Callable[[UnitOfWork], Awaitable[M]],
        status_for: Callable[[M], int],
    ) -> JSONResponse:
        if lock == "held":
            raise RequestInProgress()  # the retry will find the resource the first request created
        try:
            async with uow:
                result = await action(uow)
        except IntegrityError as exc:
            raise ConcurrentWrite() from exc  # a concurrent duplicate won; the retry returns it
        return JSONResponse(result.model_dump(mode="json", by_alias=True), status_code=status_for(result))

    async def _replay_or_in_progress(self, ctx: IdempotencyContext, uow: UnitOfWork) -> JSONResponse:
        async with uow:
            stored = await _find(uow.session, ctx.key_hash)
        if stored is None:
            raise RequestInProgress()
        return _replay(stored, ctx)

    async def _acquire(self, ctx: IdempotencyContext) -> Literal["acquired", "held", "unavailable"]:
        if self._redis is None:
            return "unavailable"
        try:
            ok = await self._redis.set(_lock_name(ctx), ctx.request_hash.hex(), nx=True, ex=LOCK_TTL_SECONDS)
        except RedisError:
            log.warning("idempotency.redis_unavailable")
            return "unavailable"
        return "acquired" if ok else "held"

    async def _release(self, ctx: IdempotencyContext) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(_lock_name(ctx))
        except RedisError:
            log.warning("idempotency.redis_unavailable")


@dataclass
class IdempotentCommand:
    """What a state-changing route needs: the key context (None when optional and absent), the store
    and a unit of work."""

    ctx: IdempotencyContext | None
    store: IdempotencyStore
    uow: UnitOfWork

    async def run(
        self,
        action: Callable[[UnitOfWork], Awaitable[M]],
        status_for: Callable[[M], int],
        mode: Literal["exact", "business-key"] = "exact",
    ) -> JSONResponse:
        if self.ctx is None:
            # A portal action sent without a key: the resource's own state checks prevent a repeat.
            async with self.uow:
                result = await action(self.uow)
            return JSONResponse(result.model_dump(mode="json", by_alias=True), status_code=status_for(result))
        return await self.store.run(self.ctx, self.uow, action, status_for, mode)

    @property
    def key(self) -> str:
        """The raw Idempotency-Key, for routes where it is the business identity."""
        if self.ctx is None:
            raise IdempotencyKeyRequired()
        return self.ctx.key


def idempotent(
    request: Request,
    ctx: IdempotencyContext = Depends(idempotency_context),
    uow: UnitOfWork = Depends(get_uow),
) -> IdempotentCommand:
    """Idempotency-Key required: every route n8n calls."""
    return IdempotentCommand(ctx=ctx, store=request.app.state.idempotency, uow=uow)


async def optional_idempotency_context(
    request: Request, principal: Principal = Depends(current_principal)
) -> IdempotencyContext | None:
    if not request.headers.get("idempotency-key"):
        return None
    return await idempotency_context(request, principal)


def idempotent_optional(
    request: Request,
    ctx: IdempotencyContext | None = Depends(optional_idempotency_context),
    uow: UnitOfWork = Depends(get_uow),
) -> IdempotentCommand:
    """Idempotency-Key accepted: portal actions (portal contract: every state-changing POST accepts one)."""
    return IdempotentCommand(ctx=ctx, store=request.app.state.idempotency, uow=uow)


async def _find(session: AsyncSession, key_hash: bytes) -> IdempotencyRecord | None:
    result = await session.execute(select(IdempotencyRecord).where(IdempotencyRecord.key_hash == key_hash))
    return result.scalar_one_or_none()


def _replay(stored: IdempotencyRecord, ctx: IdempotencyContext) -> JSONResponse:
    if bytes(stored.request_hash) != ctx.request_hash:
        raise IdempotencyKeyReused()
    log.info("idempotency.replayed")
    return JSONResponse(stored.response, status_code=stored.http_status, headers={"Idempotent-Replayed": "true"})


def _lock_name(ctx: IdempotencyContext) -> str:
    return f"api:idem:{ctx.key_hash.hex()}"


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
