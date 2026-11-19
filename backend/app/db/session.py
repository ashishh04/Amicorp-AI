"""Async engine, sessions and the unit of work that every command runs in.

One command = one unit of work = one transaction. The state change, its audit events and its stored
idempotency response commit together or not at all (blueprint section 5).
"""
import asyncio
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.principal import Principal
from app.core.security import current_principal
from app.shared.audit import AuditBuffer, write_chained


def make_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC", "connect_timeout": settings.db_connect_timeout_seconds},
    )


def require_selector_loop() -> None:
    """psycopg's async mode cannot run on Windows' default ProactorEventLoop: fail early and clearly."""
    if sys.platform == "win32" and isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
        raise RuntimeError(
            "psycopg async needs the SelectorEventLoop on Windows. Start the API with `python -m app`, "
            "or pass `--loop asyncio:SelectorEventLoop` to uvicorn."
        )


class UnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        actor: str,
        correlation_id: str | None,
        actor_role: str | None = None,
    ):
        self._factory = session_factory
        self._after_commit: list[Callable[[], Awaitable[None]]] = []
        self.actor = actor
        self.actor_role = actor_role
        self.correlation_id = correlation_id

    async def __aenter__(self) -> Self:
        self.session = self._factory()
        self.now = datetime.now(UTC)
        self.audit = AuditBuffer(actor=self.actor, correlation_id=self.correlation_id, actor_role=self.actor_role)
        self._after_commit.clear()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        try:
            if exc_type is None:
                await write_chained(self.session, self.audit.events)  # last statement before COMMIT
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()
        if exc_type is None:
            for hook in self._after_commit:
                await hook()

    def after_commit(self, hook: Callable[[], Awaitable[None]]) -> None:
        """Run `hook` only if the transaction commits (for example, a NOTIFY or a cache delete)."""
        self._after_commit.append(hook)


def get_uow(request: Request, principal: Principal = Depends(current_principal)) -> UnitOfWork:
    return UnitOfWork(
        request.app.state.session_factory,
        actor=principal.actor,
        correlation_id=getattr(request.state, "correlation_id", None),
        actor_role=", ".join(sorted(r.value for r in principal.roles)) or None,
    )
