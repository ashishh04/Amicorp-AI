"""The audit trail: append-only and hash-chained (LLD, Audit immutability; blueprint section 7).

The audit trail lives here, not in n8n execution logs. A unit of work buffers its events and writes
them as the last step before COMMIT:

1. lock the chain head (SELECT ... FOR UPDATE);
2. number the events from the head, so the sequence has no gaps;
3. hash each event together with the previous event's hash;
4. insert the events and move the head.

The head lock is held only for those final milliseconds, so chain order equals commit order. This
must run under READ COMMITTED, so the head is re-read once the lock is granted.
"""
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import AuditEventRow, ChainHead

CHAIN_ID = 0
GENESIS_HASH = bytes(32)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class AuditEvent:
    action: str
    entity: str
    entity_id: str
    payload: dict[str, Any]
    actor: str
    correlation_id: str | None
    at: datetime


def chain_hash(prev_hash: bytes, seq: int, event: AuditEvent) -> bytes:
    body = canonical_json({
        "seq": seq,
        "at": _iso(event.at),
        "actor": event.actor,
        "action": event.action,
        "entity": event.entity,
        "entityId": event.entity_id,
        "correlationId": event.correlation_id,
        "payload": event.payload,
    })
    return hashlib.sha256(prev_hash + body.encode("utf-8")).digest()


@dataclass
class AuditBuffer:
    actor: str
    correlation_id: str | None
    actor_role: str | None = None
    events: list[AuditEvent] = field(default_factory=list)

    def record(
        self,
        action: str,
        entity: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
        *,
        domain: str = "General",
    ) -> None:
        # `_role` and `_domain` ride in the hashed payload: the audit search shows the role, and the MLRO
        # sees only domain AML. Normalise through JSON now, so what is hashed is what JSONB returns.
        enriched = {**(payload or {}), "_domain": domain}
        if self.actor_role:
            enriched["_role"] = self.actor_role
        normalised = json.loads(canonical_json(enriched))
        self.events.append(AuditEvent(
            action=action, entity=entity, entity_id=entity_id, payload=normalised,
            actor=self.actor, correlation_id=self.correlation_id, at=datetime.now(UTC),
        ))


async def write_chained(session: AsyncSession, events: list[AuditEvent]) -> None:
    """Append the buffered events to the chain. Call as the last statement before COMMIT."""
    if not events:
        return
    head = (
        await session.execute(select(ChainHead).where(ChainHead.chain_id == CHAIN_ID).with_for_update())
    ).scalar_one()
    seq, prev = head.last_seq, bytes(head.last_hash)
    rows = []
    for event in events:
        seq += 1
        digest = chain_hash(prev, seq, event)
        rows.append({
            "seq": seq, "at": event.at, "actor": event.actor, "action": event.action,
            "entity": event.entity, "entity_id": event.entity_id, "correlation_id": event.correlation_id,
            "payload": event.payload, "prev_hash": prev, "hash": digest,
        })
        prev = digest
    await session.execute(insert(AuditEventRow), rows)
    await session.execute(
        update(ChainHead).where(ChainHead.chain_id == CHAIN_ID).values(last_seq=seq, last_hash=prev)
    )


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    first_bad_seq: int | None = None


def verify_rows(rows: Iterable[AuditEventRow]) -> ChainCheck:
    """Recompute the chain from its first event. Rows must be ordered by seq."""
    prev, expected_seq, checked = GENESIS_HASH, 1, 0
    for row in rows:
        event = AuditEvent(
            action=row.action, entity=row.entity, entity_id=row.entity_id, payload=row.payload,
            actor=row.actor, correlation_id=row.correlation_id, at=row.at,
        )
        if row.seq != expected_seq or bytes(row.prev_hash) != prev or chain_hash(prev, row.seq, event) != bytes(
            row.hash
        ):
            return ChainCheck(ok=False, checked=checked, first_bad_seq=row.seq)
        prev, expected_seq, checked = bytes(row.hash), expected_seq + 1, checked + 1
    return ChainCheck(ok=True, checked=checked)


async def verify_chain(session: AsyncSession) -> ChainCheck:
    rows = (await session.execute(select(AuditEventRow).order_by(AuditEventRow.seq))).scalars()
    return verify_rows(rows)
