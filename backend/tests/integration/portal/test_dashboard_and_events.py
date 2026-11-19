"""The KPI summary (GET /v1/dashboard/summary) and live events (GET /v1/events/ticket and /stream)."""
import pytest

from app.modules.events import service as events
from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def n8n(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


def extraction_exception(subject: str) -> dict:
    return {"type": "uc1.extraction-exception", "subjectId": subject, "extractionJobId": "6f1c3b52-9d0e-4b5a-8f3e-"
            "2a6c1d7e9b40", "status": "failed", "error": "Unreadable scan"}


async def test_the_kpis_count_what_happened(client, sign_in, run_jobs):
    await client.post("/v1/cards", headers=n8n("k1"), json=extraction_exception("ST-K1"))
    closed = (await client.post("/v1/cards", headers=n8n("k2"), json=extraction_exception("ST-K2"))).json()["cardId"]
    await run_jobs()  # the evidence review hands each card to its owner
    await client.post(f"/v1/cards/{closed}/decisions", headers=await sign_in("u-priya"),
                      json={"decision": "REJECT", "rationale": "Duplicate upload"})  # Priya owns the second card
    await client.post("/v1/transactions", headers=n8n("TX-K"), json={
        "transactionId": "TX-K", "source": "realtime", "receivedAt": "2026-10-30T02:00:00Z"})
    await client.post("/v1/transactions/enrich", headers=n8n("e:TX-K"), json={"transactionId": "TX-K"})
    await client.post("/v1/gates/evaluate", headers=n8n("g:TX-K"), json={
        "ruleset": "aml.gate1-entry", "subjectType": "transaction", "subjectId": "TX-K"})

    kpis = (await client.get("/v1/dashboard/summary", params={"days": 7}, headers=await sign_in("u-grace"))).json()
    assert (kpis["rangeDays"], kpis["openCards"], kpis["decisions"]) == (7, 1, 1)
    assert len(kpis["daily"]) == 7 and kpis["daily"][-1]["created"] == 2
    assert {"rulesetKey": "aml.gate1-entry", "outcome": "below-threshold", "count": 1} in kpis["gateOutcomes"]
    assert kpis["uc2HoldRatePct"] == 0.0 and kpis["writebackSuccessPct"] == 100.0
    assert {len(values) for values in kpis["series"].values()} == {7}
    assert set(kpis["previous"]) == set(kpis["series"])
    assert kpis["llmTokens"]["budgetIn"] == 30_000_000
    assert (await client.get("/v1/dashboard/summary", params={"days": 5},
                             headers=await sign_in("u-grace"))).status_code == 422
    assert (await client.get("/v1/dashboard/summary", headers=await sign_in("u-chan"))).status_code == 403


async def stream_body(client, headers: dict, last_event_id: int | None = 0) -> tuple[int, str]:
    ticket = (await client.get("/v1/events/ticket", headers=headers)).json()["ticket"]
    params = {"ticket": ticket} | ({"lastEventId": last_event_id} if last_event_id is not None else {})
    response = await client.get("/v1/events/stream", params=params)
    return response.status_code, response.text


async def test_each_officer_gets_only_the_events_of_cards_they_may_see(client, sign_in, monkeypatch, run_jobs):
    monkeypatch.setattr(events, "MAX_STREAM_SECONDS", 0.6)
    monkeypatch.setattr(events, "POLL_SECONDS", 0.1)
    ops = (await client.post("/v1/cards", headers=n8n("e1"), json=extraction_exception("ST-E1"))).json()["cardId"]
    aml = (await client.post("/v1/cards", headers=n8n("e2"), json={
        "type": "aml.gate-exception", "subjectId": "TX-E2", "blocksTransaction": True,
        "failedAt": "Gate 1 Entry", "error": "Timeout"})).json()["cardId"]
    await run_jobs()

    status, priya_body = await stream_body(client, await sign_in("u-priya"))
    assert status == 200
    assert f'"cardId": "{ops}"' in priya_body and "event: card.created" in priya_body
    assert "event: card.assigned" in priya_body and aml not in priya_body
    _, daniel_body = await stream_body(client, await sign_in("u-daniel"))
    assert aml in daniel_body and ops not in daniel_body  # the MLRO sees AML cards only
    _, from_now = await stream_body(client, await sign_in("u-martin"), last_event_id=None)
    assert "event:" not in from_now  # no lastEventId: only what happens from now on


async def test_a_ticket_works_once(client, sign_in):
    priya = await sign_in("u-priya")
    ticket = (await client.get("/v1/events/ticket", headers=priya)).json()["ticket"]
    events.MAX_STREAM_SECONDS, saved = 0.2, events.MAX_STREAM_SECONDS
    try:
        first = await client.get("/v1/events/stream", params={"ticket": ticket})
        second = await client.get("/v1/events/stream", params={"ticket": ticket})
    finally:
        events.MAX_STREAM_SECONDS = saved
    assert (first.status_code, second.status_code) == (200, 401)
    assert (await client.get("/v1/events/stream", params={"ticket": "x" * 43})).status_code == 401
    assert (await client.get("/v1/events/ticket")).status_code == 401
