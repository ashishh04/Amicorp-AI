"""Database access for cards.

`visible_to` and `in_view` are domain.can_see and domain.in_view written as SQL, so a list, a count and a
single read can never disagree about which cards a person sees.
"""
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Text, and_, cast, false, func, or_, select, true, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Role
from app.modules.cards import domain
from app.modules.cards.models import Card, CardEvent, CardEvidence

VIEWS = ("mine", "team", "due-soon", "overdue", "escalated", "closed")


@dataclass(frozen=True)
class CardQuery:
    view: str | None
    text: str | None
    type_prefix: str | None
    type: str | None
    severity: str | None
    by_recent: bool  # -updatedAt instead of dueAt
    limit: int
    after: tuple[datetime, uuid.UUID] | None  # the previous page's last sort key and card ID


def visible_to(who: domain.Who) -> ColumnElement[bool]:
    if who.has(Role.AUDITOR):
        return true()
    clauses: list[ColumnElement[bool]] = [Card.owner_oid == who.user_id]
    if who.has(Role.MLRO):
        clauses.append(Card.type.startswith("aml.", autoescape=True))
    if (who.has(Role.MAKER) or who.has(Role.CHECKER)) and who.teams:
        clauses.append(Card.owner_team.in_(who.teams))
    return or_(*clauses)


def in_view(view: str, who: domain.Who, now: datetime) -> ColumnElement[bool]:
    match view:
        case "mine":
            return and_(Card.state.in_(domain.OPEN_STATES), Card.owner_oid == who.user_id)
        case "team":
            return Card.state.in_(domain.OPEN_STATES)
        case "due-soon":
            return and_(Card.state.in_(domain.WAITING_STATES), Card.due_at >= now, Card.due_at <= now + domain.DUE_SOON)
        case "overdue":
            return and_(Card.state.in_(domain.WAITING_STATES), Card.due_at < now)
        case "escalated":
            return Card.state == "ESCALATED"
        case "closed":
            return Card.state.in_(domain.CLOSED_STATES)
    return false()


def _contains(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class CardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, card_id: uuid.UUID) -> Card | None:
        return await self.session.get(Card, card_id)

    async def get_by_key(self, idempotency_key: str) -> Card | None:
        result = await self.session.execute(select(Card).where(Card.idempotency_key == idempotency_key))
        return result.scalar_one_or_none()

    async def get_for_update(self, card_id: uuid.UUID) -> Card | None:
        # populate_existing: a card this session read earlier is refreshed with what the lock sees.
        query = select(Card).where(Card.card_id == card_id).with_for_update().execution_options(populate_existing=True)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def latest_for_subject(self, card_type: str, subject_id: str) -> Card | None:
        result = await self.session.execute(
            select(Card).where(Card.type == card_type, Card.subject_id == subject_id)
            .order_by(Card.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def existing_keys(self, keys: Iterable[str]) -> set[str]:
        wanted = list(keys)
        if not wanted:
            return set()
        result = await self.session.execute(select(Card.idempotency_key).where(Card.idempotency_key.in_(wanted)))
        return set(result.scalars())

    async def page(self, who: domain.Who, now: datetime, query: CardQuery) -> Sequence[Card]:
        """One page plus one row, so the caller knows whether another page follows."""
        statement = select(Card).where(visible_to(who))
        if query.view:
            statement = statement.where(in_view(query.view, who, now))
        if query.text:
            pattern = _contains(query.text)
            statement = statement.where(or_(
                cast(Card.card_id, Text).ilike(pattern, escape="\\"),
                Card.title.ilike(pattern, escape="\\"),
                Card.subject_id.ilike(pattern, escape="\\"),
            ))
        if query.type_prefix:
            statement = statement.where(Card.type.startswith(query.type_prefix, autoescape=True))
        if query.type:
            statement = statement.where(Card.type == query.type)
        if query.severity:
            statement = statement.where(Card.severity == query.severity)
        if query.by_recent:
            if query.after:
                statement = statement.where(tuple_(Card.updated_at, Card.card_id) < tuple_(*query.after))
            statement = statement.order_by(Card.updated_at.desc(), Card.card_id.desc())
        else:
            if query.after:
                statement = statement.where(tuple_(Card.due_at, Card.card_id) > tuple_(*query.after))
            statement = statement.order_by(Card.due_at, Card.card_id)
        return (await self.session.execute(statement.limit(query.limit + 1))).scalars().all()

    async def counts(self, who: domain.Who, now: datetime) -> dict[str, int]:
        columns = [func.count().filter(in_view(view, who, now)).label(view) for view in VIEWS]
        row = (await self.session.execute(select(*columns).select_from(Card).where(visible_to(who)))).one()
        return {view: int(row._mapping[view]) for view in VIEWS}

    async def open_load(self, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int]:
        """How many open cards each person owns: new cards go to the least loaded."""
        wanted = list(user_ids)
        if not wanted:
            return {}
        result = await self.session.execute(
            select(Card.owner_oid, func.count())
            .where(Card.owner_oid.in_(wanted), Card.state.in_(domain.OPEN_STATES))
            .group_by(Card.owner_oid)
        )
        return {owner: int(count) for owner, count in result if owner is not None}

    async def events(self, card_id: uuid.UUID) -> Sequence[CardEvent]:
        result = await self.session.execute(
            select(CardEvent).where(CardEvent.card_id == card_id).order_by(CardEvent.event_id)
        )
        return result.scalars().all()

    async def evidence(self, card_id: uuid.UUID) -> Sequence[CardEvidence]:
        result = await self.session.execute(
            select(CardEvidence).where(CardEvidence.card_id == card_id)
            .order_by(CardEvidence.created_at, CardEvidence.kind, CardEvidence.evidence_id)
        )
        return result.scalars().all()

    async def add(self, card: Card) -> None:
        self.session.add(card)
        await self.session.flush()  # the card row must exist before its events and evidence

    def add_event(self, event: CardEvent) -> None:
        self.session.add(event)

    def add_evidence(self, evidence: CardEvidence) -> None:
        self.session.add(evidence)
