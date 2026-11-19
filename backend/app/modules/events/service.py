"""Live events (portal contract, Live events; decision D-16). No HTTP here.

Producers call publish() inside their own unit of work, so an event exists if and only if its change
committed (an outbox). Payloads are small and never sensitive: the portal re-reads the REST resource.

EventSource cannot send an Authorization header, so the portal first exchanges its bearer token for a ticket:
random, valid for one minute, single use, kept in Redis. The stream then polls the outbox (an index range
scan on event_id) and sends each event only to people who may see its card.
"""
import asyncio
import hashlib
import json
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ServiceUnavailable, Unauthorized
from app.core.principal import Principal, Role
from app.db.session import UnitOfWork
from app.modules.cards import domain as card_rules
from app.modules.events.models import EventRow
from app.modules.identity import service as identity

log = structlog.get_logger()

TICKET_TTL_SECONDS = 60
POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 15.0
# The portal reconnects with a fresh ticket and its lastEventId, so a connection may end at any time.
MAX_STREAM_SECONDS = 1800.0
REPLAY_LIMIT = 500


def publish(
    uow: UnitOfWork,
    event_type: str,
    data: dict[str, Any],
    *,
    card_type: str | None = None,
    team: str | None = None,
    owner_oid: uuid.UUID | None = None,
) -> None:
    """Record an event in the caller's unit of work."""
    uow.session.add(EventRow(type=event_type, data=data, card_type=card_type, team=team, owner_oid=owner_oid,
                             at=uow.now))


async def issue_ticket(redis: Redis, principal: Principal) -> str:
    ticket = secrets.token_urlsafe(32)
    value = json.dumps({"subject": principal.subject, "kind": principal.kind,
                        "roles": sorted(r.value for r in principal.roles), "tokenId": principal.token_id})
    try:
        await redis.set(_ticket_key(ticket), value, ex=TICKET_TTL_SECONDS)
    except RedisError as exc:
        raise ServiceUnavailable("Live updates are unavailable right now; the portal keeps working without them.") \
            from exc
    return ticket


async def redeem_ticket(redis: Redis, ticket: str) -> Principal:
    """The ticket's principal. A ticket works once: GETDEL makes a replayed URL useless."""
    try:
        raw = await redis.getdel(_ticket_key(ticket))
    except RedisError as exc:
        raise ServiceUnavailable("Live updates are unavailable right now.") from exc
    if raw is None:
        raise Unauthorized("The event ticket is not valid or has expired; get a new one")
    data = json.loads(raw)
    roles = frozenset(Role(r) for r in data["roles"] if r in Role._value2member_map_)
    return Principal(subject=data["subject"], kind=data["kind"], roles=roles, token_id=data.get("tokenId"))


async def stream(
    session_factory: async_sessionmaker[AsyncSession],
    principal: Principal,
    last_event_id: int | None,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    """Server-sent events for one person, from after last_event_id (or from now), until they disconnect."""
    async with UnitOfWork(session_factory, actor=principal.actor, correlation_id=None) as uow:
        caller = await identity.caller(uow, principal)
        cursor = last_event_id if last_event_id is not None else await _last_id(uow.session)
    who = card_rules.Who(user_id=caller.user_id, roles=caller.roles, teams=caller.teams)
    started = last_beat = time.monotonic()
    yield ": connected\n\n"
    while time.monotonic() - started < MAX_STREAM_SECONDS and not await is_disconnected():
        async with session_factory() as session:
            rows = (await session.execute(
                select(EventRow).where(EventRow.event_id > cursor).order_by(EventRow.event_id).limit(REPLAY_LIMIT)
            )).scalars().all()
        for row in rows:
            cursor = row.event_id
            if _visible(row, who):
                yield f"id: {row.event_id}\nevent: {row.type}\ndata: {json.dumps(row.data, default=str)}\n\n"
        if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
            last_beat = time.monotonic()
            yield ": keep-alive\n\n"
        if not rows:
            await asyncio.sleep(POLL_SECONDS)


def _visible(row: EventRow, who: card_rules.Who) -> bool:
    if row.card_type is None or row.team is None:
        return False  # every portal event concerns a card; anything else stays on the server
    return card_rules.can_see(row.card_type, row.team, row.owner_oid, who)


async def _last_id(session: AsyncSession) -> int:
    return int((await session.execute(select(func.coalesce(func.max(EventRow.event_id), 0)))).scalar_one())


def _ticket_key(ticket: str) -> str:
    return "api:sse:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()
