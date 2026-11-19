from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from app.shared.audit import GENESIS_HASH, AuditEvent, canonical_json, chain_hash, verify_rows


@dataclass(frozen=True)
class Row:
    seq: int
    at: datetime
    actor: str
    action: str
    entity: str
    entity_id: str
    correlation_id: str | None
    payload: dict[str, Any]
    prev_hash: bytes
    hash: bytes


def build_chain(count: int) -> list[Row]:
    rows, prev = [], GENESIS_HASH
    for seq in range(1, count + 1):
        event = AuditEvent(
            action="incident.opened", entity="incident", entity_id=f"id-{seq}", payload={"n": seq},
            actor="svc:automation-dev", correlation_id="exec-1", at=datetime(2026, 10, 28, 9, 0, seq, tzinfo=UTC),
        )
        digest = chain_hash(prev, seq, event)
        rows.append(Row(seq, event.at, event.actor, event.action, event.entity, event.entity_id,
                        event.correlation_id, event.payload, prev, digest))
        prev = digest
    return rows


def test_an_untouched_chain_verifies():
    check = verify_rows(build_chain(5))
    assert check.ok and check.checked == 5


def test_a_changed_payload_is_detected():
    rows = build_chain(5)
    rows[2] = replace(rows[2], payload={"n": 999})
    check = verify_rows(rows)
    assert not check.ok and check.first_bad_seq == 3


def test_a_removed_row_is_detected():
    rows = build_chain(5)
    del rows[1]
    check = verify_rows(rows)
    assert not check.ok and check.first_bad_seq == 3


def test_canonical_json_ignores_key_order():
    assert canonical_json({"b": 1, "a": {"y": 2, "x": 1}}) == canonical_json({"a": {"x": 1, "y": 2}, "b": 1})
