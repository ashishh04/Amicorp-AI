"""Read-only access to audit.audit_event. Nothing here writes: the trail is append-only (app/shared/audit.py)."""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Text, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import AuditEventRow


@dataclass(frozen=True)
class AuditQuery:
    aml_only: bool
    entity: str | None
    actors: list[str] | None  # None: any actor; []: nobody matched the actor filter
    since: datetime | None
    text_pattern: str | None  # ILIKE pattern, escaped with backslash
    text_actors: list[str]  # actors whose name matches the free text
    before_seq: int | None
    limit: int


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def page(self, query: AuditQuery) -> Sequence[AuditEventRow]:
        """Newest first, one row more than the page so the caller knows whether another page follows."""
        conditions: list[ColumnElement[bool]] = []
        if query.aml_only:
            conditions.append(AuditEventRow.payload["_domain"].astext == "AML")
        if query.entity:
            conditions.append(AuditEventRow.entity == query.entity)
        if query.actors is not None:
            conditions.append(AuditEventRow.actor.in_(query.actors))
        if query.since:
            conditions.append(AuditEventRow.at >= query.since)
        if query.text_pattern:
            matches = [
                AuditEventRow.action.ilike(query.text_pattern, escape="\\"),
                AuditEventRow.entity_id.ilike(query.text_pattern, escape="\\"),
                cast(AuditEventRow.payload, Text).ilike(query.text_pattern, escape="\\"),
            ]
            if query.text_actors:
                matches.append(AuditEventRow.actor.in_(query.text_actors))
            conditions.append(or_(*matches))
        if query.before_seq is not None:
            conditions.append(AuditEventRow.seq < query.before_seq)
        statement = select(AuditEventRow).where(*conditions).order_by(AuditEventRow.seq.desc()).limit(query.limit + 1)
        return (await self.session.execute(statement)).scalars().all()
