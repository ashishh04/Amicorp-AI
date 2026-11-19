"""Business rules for audit search. No HTTP or SQL here.

Auditors read the whole trail; the MLRO reads only the AML domain (portal contract, Audit). Actors are
stored as 'user:<oid>' or 'svc:<name>' and shown by name, so a search by name resolves the IDs first.
"""
import json
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.core.errors import BadRequest
from app.core.principal import Principal, Role
from app.db.session import UnitOfWork
from app.modules.audit_log.repository import AuditQuery, AuditRepository
from app.modules.audit_log.schemas import AuditEventView, AuditPage
from app.modules.identity import service as identity
from app.shared.models import AuditEventRow
from app.shared.pagination import clamp_limit, decode_cursor, encode_cursor

_HIDDEN = {"_domain", "_role"}
_DETAIL_LENGTH = 300


async def list_events(
    uow: UnitOfWork,
    principal: Principal,
    *,
    q: str | None,
    entity: str | None,
    actor: str | None,
    since: datetime | None,
    limit: int | None,
    cursor: str | None,
) -> AuditPage:
    size = clamp_limit(limit)
    before_seq = _before(cursor)
    async with uow:
        actors = await identity.actors_named(uow, actor) if actor else None
        text_actors = await identity.actors_named(uow, q) if q else []
        rows = await AuditRepository(uow.session).page(AuditQuery(
            aml_only=Role.AUDITOR not in principal.roles, entity=entity, actors=actors, since=since,
            text_pattern=_contains(q) if q else None, text_actors=text_actors, before_seq=before_seq, limit=size,
        ))
        page = rows[:size]
        names = await identity.display_names(uow, _user_ids(page))
    next_cursor = encode_cursor({"seq": page[-1].seq}) if len(rows) > size else None
    return AuditPage(items=[_view(r, names) for r in page], next_cursor=next_cursor)


def _view(row: AuditEventRow, names: dict[uuid.UUID, str]) -> AuditEventView:
    payload: dict[str, Any] = row.payload or {}
    return AuditEventView(
        id=str(row.seq), at=row.at, actor=identity.actor_name(row.actor, names),
        actor_role=payload.get("_role") or ("System" if row.actor.startswith("svc:") else "Unknown"),
        action=row.action, entity=row.entity, entity_id=row.entity_id, detail=_detail(payload),
        domain="AML" if payload.get("_domain") == "AML" else "General",
    )


def _detail(payload: dict[str, Any]) -> str:
    parts = []
    for key, value in payload.items():
        if key in _HIDDEN or value is None:
            continue
        shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        parts.append(f"{key}: {shown}")
    text = "; ".join(parts)
    return text if len(text) <= _DETAIL_LENGTH else text[: _DETAIL_LENGTH - 1] + "…"


def _before(cursor: str | None) -> int | None:
    values = decode_cursor(cursor, {"seq"})
    if values is None:
        return None
    if not isinstance(values["seq"], int) or isinstance(values["seq"], bool):
        raise BadRequest("The cursor is not valid; start again from the first page")
    return values["seq"]


def _contains(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _user_ids(rows: Iterable[AuditEventRow]) -> set[uuid.UUID]:
    ids = set()
    for row in rows:
        if row.actor.startswith("user:"):
            try:
                ids.add(uuid.UUID(row.actor[5:]))
            except ValueError:
                continue
    return ids
