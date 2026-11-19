"""POST /v1/cards for the types UC1-UC3 create, and the recommendation rules."""
import uuid

import psycopg
import pytest

from app.db.session import UnitOfWork
from app.modules.cards import service as cards
from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def headers(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


HOLD_CARD = {
    "type": "aml.gate-exception", "subjectId": "TX-1001", "severity": "high", "blocksTransaction": True,
    "failedAt": "Gate 3 Risk and screening", "outcome": None, "error": "Screening provider unavailable",
}


async def test_the_uc2_hold_card_reaches_compliance_once_its_evidence_is_reviewed(client, database, run_jobs):
    response = await client.post("/v1/cards", json=HOLD_CARD, headers=headers("TX-1001:gate-exception"))
    assert response.status_code == 201
    assert response.json()["state"] == "ASSEMBLING"
    await run_jobs()
    with psycopg.connect(database) as conn:
        row = conn.execute("SELECT severity, owner_team, blocks_subject, due_at > created_at FROM card.card").fetchone()
        moves = [r[0] for r in conn.execute(
            "SELECT to_state FROM card.card_event WHERE from_state IS DISTINCT FROM to_state ORDER BY event_id")]
        owner, assigned = conn.execute(
            "SELECT u.display_name, e.detail->>'action' FROM card.card c "
            "JOIN ref.app_user u ON u.user_id = c.owner_oid "
            "JOIN card.card_event e ON e.card_id = c.card_id AND e.from_state = e.to_state").fetchone()
    assert row == ("high", "Compliance", True, True)
    assert moves == ["NEW", "ASSEMBLING", "AWAITING_DECISION"]
    # The least-loaded Compliance Checker owns it; with no load, the first by name.
    assert (owner, assigned) == ("Ava Leung", "Assigned to Ava Leung")


async def test_an_mlro_escalation_is_never_below_critical(client, database):
    gate_runs = [str(uuid.uuid4()) for _ in range(3)]
    body = {"type": "aml.mlro-escalation", "subjectId": "TX-2002", "severity": "high", "blocksTransaction": True,
            "screeningOutcome": "alert", "gateRunIds": gate_runs}
    assert (await client.post("/v1/cards", json=body, headers=headers("TX-2002:mlro-escalation"))).status_code == 201
    with psycopg.connect(database) as conn:
        severity, team, runs = conn.execute("SELECT severity, owner_team, gate_run_ids FROM card.card").fetchone()
    assert (severity, team) == ("critical", "MLRO office")
    assert [str(r) for r in runs] == gate_runs


async def test_unknown_types_and_unexpected_fields_are_refused(client):
    unknown = await client.post("/v1/cards", json={"type": "uc9.unknown", "subjectId": "X"}, headers=headers("k-1"))
    extra = await client.post("/v1/cards", headers=headers("k-2"), json={
        "type": "uc4.discrepancy", "subjectId": "X", "findingId": str(uuid.uuid4()), "dedupeKey": "d",
        "scanId": str(uuid.uuid4()), "unexpected": 1,
    })
    assert unknown.status_code == extra.status_code == 422


async def test_cards_without_ai_refuse_a_recommendation(client):
    created = await client.post("/v1/cards", json=HOLD_CARD, headers=headers("TX-1001:gate-exception"))
    card_id = created.json()["cardId"]
    response = await client.post(f"/v1/cards/{card_id}/recommend", json={"mode": "assemble-and-recommend"},
                                 headers=headers(f"{card_id}:recommend"))
    assert response.status_code == 409
    assert response.json()["code"] == "CARD_STATE_CONFLICT"


async def test_a_recommendation_for_an_unknown_card_is_404(client):
    response = await client.post(f"/v1/cards/{uuid.uuid4()}/recommend", json={"mode": "propose-correction"},
                                 headers=headers("missing:recommend"))
    assert response.status_code == 404


async def test_when_the_model_never_answers_the_card_still_reaches_a_decision_maker(client, app, database):
    body = {"type": "uc4.discrepancy", "subjectId": "ENT-1", "findingId": str(uuid.uuid4()),
            "dedupeKey": "uc4:D-01:ENT-1", "scanId": str(uuid.uuid4())}
    card_id = (await client.post("/v1/cards", json=body, headers=headers("uc4:D-01:ENT-1"))).json()["cardId"]
    async with UnitOfWork(app.state.session_factory, actor="svc:jobs-worker", correlation_id="test") as uow:
        await cards.recommend_failed(uow, {"cardId": card_id}, "TimeoutError: MaaS did not answer")
    with psycopg.connect(database) as conn:
        state = conn.execute("SELECT state FROM card.card").fetchone()[0]
        summary = conn.execute("SELECT summary FROM card.card_evidence WHERE kind = 'recommendation'").fetchone()[0]
    assert state == "AWAITING_DECISION"
    assert summary.startswith("Summary unavailable")
