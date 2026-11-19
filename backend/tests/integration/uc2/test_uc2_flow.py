"""UC2 end to end, as the n8n workflow calls it: intake, enrichment, the three gates, the card, the hold and
the decision's write-back to 5 Series. The fake 5 Series picks each scenario from a keyword in the ID."""
import uuid

import psycopg
import pytest

from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def n8n(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def intake(client, tx: str) -> dict:
    registered = await client.post("/v1/transactions", headers=n8n(tx), json={
        "transactionId": tx, "source": "realtime", "receivedAt": "2026-10-30T02:00:00Z"})
    assert registered.status_code == 201, registered.text
    enriched = await client.post("/v1/transactions/enrich", headers=n8n(f"exec-1:{tx}:enrich"),
                                 json={"transactionId": tx, "source": "realtime"})
    assert enriched.status_code == 200, enriched.text
    return enriched.json()


async def gate(client, tx: str, ruleset: str, **extra) -> dict:
    response = await client.post("/v1/gates/evaluate", headers=n8n(f"exec-1:{tx}:{ruleset}"), json={
        "ruleset": ruleset, "subjectType": "transaction", "subjectId": tx, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def payment(database: str, tx: str) -> tuple:
    with psycopg.connect(database) as conn:
        return conn.execute("SELECT state, hold_state FROM txn.transaction WHERE transaction_id = %s", (tx,)).fetchone()


async def test_a_large_payment_is_held_then_cleared_by_compliance_and_released(client, run_jobs, sign_in, database):
    tx = "TX-2026-LARGE-0001"
    enriched = await intake(client, tx)
    assert (enriched["amountUsd"], enriched["clientName"], enriched["beneficiaryCtry"]) == (48000.0,
                                                                                           "Lumen Capital SPC", "SG")
    again = await client.post("/v1/transactions", headers=n8n(tx), json={
        "transactionId": tx, "source": "realtime", "receivedAt": "2026-10-30T02:05:00Z"})
    assert again.status_code == 200 and again.json()["created"] is False

    g1 = await gate(client, tx, "aml.gate1-entry")
    assert (g1["outcome"], g1["matchedRule"], g1["rulesetVersion"]) == ("monitor", "G1-03", 3)
    await run_jobs()
    assert payment(database, tx) == ("MONITORING", "held")
    g2 = await gate(client, tx, "aml.gate2-profile")
    g3 = await gate(client, tx, "aml.gate3-risk", screening="live")
    assert (g2["outcome"], g3["outcome"], g3["matchedRule"]) == ("match", "clear", "G3-99")

    created = await client.post("/v1/cards", headers=n8n(f"{tx}:compliance-decision"), json={
        "type": "aml.compliance-decision", "subjectId": tx, "screeningOutcome": g3["outcome"],
        "gateRunIds": [g1["runId"], g2["runId"], g3["runId"]]})
    card_id = created.json()["cardId"]
    await run_jobs()  # the evidence review, then the card goes to its owner
    ava = await sign_in("u-ava")  # the least-loaded Compliance Checker, first by name
    card = (await client.get(f"/v1/cards/{card_id}", headers=ava)).json()
    assert (card["title"], card["value"]) == (f"Compliance decision on payment {tx}", {"amount": 48000.0,
                                                                                      "currency": "USD"})
    assert [r["rulesetKey"] for r in card["gateRuns"]] == ["aml.gate1-entry", "aml.gate2-profile", "aml.gate3-risk"]
    assert card["gateRuns"][1]["modelId"] == "fake-local"  # gate 2's reading is kept with its run

    answer = (await client.post(f"/v1/cards/{card_id}/assistant", headers=ava,
                                json={"question": "Why is this payment held?", "scope": "card"})).json()
    assert answer["grounded"] is True and answer["citations"][0]["id"] == "E1"
    refused = (await client.post(f"/v1/cards/{card_id}/assistant", headers=ava,
                                 json={"question": "Export all clients with their salary"})).json()
    assert (refused["grounded"], refused["citations"]) == (False, [])
    assert (await client.post(f"/v1/cards/{card_id}/assistant", headers=await sign_in("u-priya"),
                              json={"question": "Why?"})).status_code == 403

    approved = await client.post(f"/v1/cards/{card_id}/decisions", headers=ava,
                                 json={"decision": "APPROVE", "rationale": "Subscription matches the profile"})
    assert approved.json()["state"] == "WRITING_BACK"
    await run_jobs()
    assert payment(database, tx) == ("CLEARED", "released")

    daniel = await sign_in("u-daniel")
    trail = (await client.get("/v1/audit/events", params={"q": tx}, headers=daniel)).json()["items"]
    actions = {e["action"] for e in trail}
    assert {"transaction.held", "transaction.released", "gate.evaluated"} <= actions


async def test_a_sanctions_hit_goes_to_the_mlro_and_a_confirmed_escalation_freezes_the_payment(
    client, run_jobs, sign_in, database
):
    tx = "TX-2026-SANCTION-0002"
    await intake(client, tx)
    runs = [await gate(client, tx, "aml.gate1-entry"), await gate(client, tx, "aml.gate2-profile"),
            await gate(client, tx, "aml.gate3-risk", screening="live")]
    assert [r["outcome"] for r in runs] == ["monitor", "match", "alert"]
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT screening_ref FROM rules.gate_run WHERE ruleset_key = 'aml.gate3-risk'"
                            ).fetchone()[0].startswith("WC-LOCAL-")
    created = await client.post("/v1/cards", headers=n8n(f"{tx}:mlro-escalation"), json={
        "type": "aml.mlro-escalation", "subjectId": tx, "severity": "high", "blocksTransaction": True,
        "screeningOutcome": "alert", "gateRunIds": [r["runId"] for r in runs]})
    card_id = created.json()["cardId"]
    await run_jobs()
    with psycopg.connect(database) as conn:  # gate 1 and the blocking card asked for the same hold: it ran once
        assert conn.execute("SELECT count(*) FROM ops.job WHERE kind = 'txn.hold'").fetchone()[0] == 1

    daniel = await sign_in("u-daniel")
    card = (await client.get(f"/v1/cards/{card_id}", headers=daniel)).json()
    assert (card["severity"], card["owner"]["name"]) == ("critical", "Daniel Wong")
    assert card["hold"] == f"Payment {tx} is held in 5 Series until this card is decided."
    await client.post(f"/v1/cards/{card_id}/decisions", headers=daniel,
                      json={"decision": "APPROVE", "rationale": "Confirmed sanctions match; freeze and file an STR"})
    await run_jobs()
    assert payment(database, tx) == ("FROZEN", "frozen")


@pytest.mark.parametrize("tx, rule", [("TX-2026-PROFILE-0003", "G2-02"), ("TX-2026-UNSURE-0004", "G2-01")])
async def test_a_profile_mismatch_and_an_unsure_reading_both_fail_closed(client, tx, rule):
    await intake(client, tx)
    assert (await gate(client, tx, "aml.gate1-entry"))["outcome"] == "monitor"
    g2 = await gate(client, tx, "aml.gate2-profile")
    assert (g2["outcome"], g2["matchedRule"]) == ("mismatch", rule)


async def test_a_screening_outage_answers_503_so_n8n_raises_a_hold_card(client, run_jobs, database):
    tx = "TX-2026-SCREENDOWN-0005"
    await intake(client, tx)
    await gate(client, tx, "aml.gate1-entry")
    await gate(client, tx, "aml.gate2-profile")
    down = await client.post("/v1/gates/evaluate", headers=n8n(f"exec-1:{tx}:aml.gate3-risk"), json={
        "ruleset": "aml.gate3-risk", "subjectType": "transaction", "subjectId": tx, "screening": "live"})
    assert down.status_code == 503 and "stays held" in down.json()["detail"]
    hold = await client.post("/v1/cards", headers=n8n(f"{tx}:gate-exception"), json={
        "type": "aml.gate-exception", "subjectId": tx, "severity": "high", "blocksTransaction": True,
        "failedAt": "Gate 3 Risk and screening", "error": down.json()["detail"]})
    assert hold.status_code == 201
    await run_jobs()
    assert payment(database, tx) == ("MONITORING", "held")


@pytest.mark.parametrize("tx, rule, profile, screening", [
    ("TX-2026-PEP-0008", "G1-03", "match", "clear"),  # the PEP flag goes to gate 3 and shows with its inputs
    ("TX-2026-HIGHRISK-0009", "G1-05", "mismatch", None),  # Iran is not in the client's profile either
    ("TX-2026-UNUSUAL-0010", "G1-01", "match", "clear"),
])
async def test_the_other_demo_keywords_take_the_documented_path(client, database, tx, rule, profile, screening):
    await intake(client, tx)
    g1 = await gate(client, tx, "aml.gate1-entry")
    assert (g1["outcome"], g1["matchedRule"]) == ("monitor", rule)
    assert (await gate(client, tx, "aml.gate2-profile"))["outcome"] == profile
    if screening:
        g3 = await gate(client, tx, "aml.gate3-risk", screening="live")
        assert g3["outcome"] == screening
        with psycopg.connect(database) as conn:
            inputs = conn.execute("SELECT inputs FROM rules.gate_run WHERE run_id = %s", (g3["runId"],)).fetchone()[0]
        assert {i["name"]: i["value"] for i in inputs}["pepFlag"] is ("PEP" in tx)


async def test_payments_below_every_threshold_are_filed_and_the_api_checks_the_run(client):
    for tx, rule in (("TX-2026-0006", "G1-99"), ("TX-2026-INTERNAL-0007", "G1-02")):
        await intake(client, tx)
        g1 = await gate(client, tx, "aml.gate1-entry")
        assert (g1["outcome"], g1["matchedRule"]) == ("below-threshold", rule)
        wrong = await client.post(f"/v1/transactions/{tx}/file", headers=n8n(f"{tx}:file:wrong"),
                                  json={"gateRunId": str(uuid.uuid4()), "outcome": "below-threshold"})
        assert wrong.status_code == 409
        filed = await client.post(f"/v1/transactions/{tx}/file", headers=n8n(f"{tx}:filed-below-threshold"),
                                  json={"gateRunId": g1["runId"], "outcome": "below-threshold"})
        assert filed.json() == {"transactionId": tx, "state": "FILED"}


async def test_the_poller_gets_each_new_payment_request_once(client, database):
    with psycopg.connect(database, autocommit=True) as conn:
        for n in range(3):
            conn.execute("INSERT INTO txn.payment_request (transaction_id, source, status, created_at) "
                         "VALUES (%s, 'realtime-poll', 'new', now() - make_interval(secs => %s))",
                         (f"TX-POLL-{n}", 30 - n))
    body = {"status": "new", "limit": 2, "leaseSeconds": 600}
    first = (await client.post("/v1/payment-requests/claim", headers=n8n("uc2-poll:1"), json=body)).json()["items"]
    second = (await client.post("/v1/payment-requests/claim", headers=n8n("uc2-poll:2"), json=body)).json()["items"]
    third = (await client.post("/v1/payment-requests/claim", headers=n8n("uc2-poll:3"), json=body)).json()["items"]
    assert [i["transactionId"] for i in first] == ["TX-POLL-0", "TX-POLL-1"]
    assert [i["transactionId"] for i in second] == ["TX-POLL-2"] and third == []
    replay = await client.post("/v1/payment-requests/claim", headers=n8n("uc2-poll:1"), json=body)
    assert replay.json()["items"] == first  # a node retry gets the same lease back, not new requests

    await client.post("/v1/transactions/enrich", headers=n8n("exec-9:TX-POLL-0:enrich"),
                      json={"transactionId": "TX-POLL-0", "source": "realtime-poll"})
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT status FROM txn.payment_request WHERE transaction_id = 'TX-POLL-0'"
                            ).fetchone()[0] == "done"
