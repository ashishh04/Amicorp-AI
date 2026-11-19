"""The evidence review of UC1, UC2 and UC3 cards: when n8n creates a card, the API assembles its evidence and the
model (a stand-in, or the real adapter talking to a fake MaaS server) reads it. The officer sees both."""
import json

import psycopg
import pytest

from app.db.session import UnitOfWork
from app.integrations.maas.review import MaasEvidenceReviewer
from app.modules.cards import service as cards
from app.modules.statements import service as statements
from tests.integration.uc1.test_uc1_flow import OBJECT_KEY, register_and_extract, validation_card
from tests.integration.uc2.test_uc2_flow import gate, intake, n8n
from tests.integration.uc3.test_uc3_flow import extracted_nav, nav_checks
from tests.unit.ai.fake_maas import FakeMaas, answer
from tests.unit.ai.fake_maas import client as maas_client

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

ADVICE = {
    "summary": "The NAV per share rose 6.50 %, beyond the fund's 3 % tolerance.",
    "proposedAction": "Ask the administrator to confirm the NAV before accepting it.",
    "decision": "REJECT", "confidence": 0.62, "citations": ["E1"],
}


async def uc2_card(client, tx: str, card_type: str, outcome: str) -> str:
    await intake(client, tx)
    runs = [await gate(client, tx, "aml.gate1-entry"), await gate(client, tx, "aml.gate2-profile"),
            await gate(client, tx, "aml.gate3-risk", screening="live")]
    created = await client.post("/v1/cards", headers=n8n(f"{tx}:{card_type}"), json={
        "type": card_type, "subjectId": tx, "screeningOutcome": outcome, "gateRunIds": [r["runId"] for r in runs]})
    assert created.status_code == 201 and created.json()["state"] == "ASSEMBLING", created.text
    return created.json()["cardId"]


async def nav_exception(client, run_jobs, callbacks, object_key: str) -> str:
    statement_id, job_id = await extracted_nav(client, run_jobs, callbacks, object_key)
    checks = await nav_checks(client, statement_id)
    created = await client.post("/v1/cards", headers=n8n(f"{statement_id}:{job_id}:nav-exception"), json={
        "type": "nav.exception", "subjectId": statement_id, "extractionJobId": job_id, "gateRunId": checks["runId"],
        "gateOutcome": checks["outcome"]})
    assert created.status_code == 201, created.text
    return created.json()["cardId"]


async def nav_evidence(uow, card_type, subject_id, runs):
    return await statements.card_evidence(uow, card_type, subject_id)


async def test_a_uc2_card_lists_the_payment_the_profile_and_the_screening(client, run_jobs, sign_in, database):
    card_id = await uc2_card(client, "TX-2026-LARGE-0101", "aml.compliance-decision", "clear")
    await run_jobs()

    card = (await client.get(f"/v1/cards/{card_id}", headers=await sign_in("u-ava"))).json()
    assert (card["state"], card["owner"]["name"]) == ("AWAITING_DECISION", "Ava Leung")
    assert [(e["id"], e["kind"], e["label"]) for e in card["evidence"]] == [
        ("E1", "record", "Payment"), ("E2", "record", "Client profile"), ("E3", "screening", "Live screening")]
    assert card["evidence"][0]["detail"].startswith(
        "USD 48,000.00 from Lumen Capital SPC (CL-1001) to Straits Asset Management Pte Ltd (CP-30411)")
    assert "largest expected payment USD 60,000" in card["evidence"][1]["detail"]
    assert card["evidence"][2]["detail"].endswith(": no match.")
    recommendation = card["recommendation"]
    assert (recommendation["modelId"], recommendation["confidence"]) == ("fake-local", 0.0)
    assert recommendation["citations"] == ["E1", "E2", "E3"]

    with psycopg.connect(database) as conn:  # what the model read is kept with its answer
        seen = conn.execute("SELECT detail FROM card.card_evidence WHERE kind = 'recommendation'").fetchone()[0]
    assert seen["mode"] == "review-evidence"
    assert [e["id"] for e in seen["evidence"]] == ["E1", "E2", "E3"] and len(seen["ruleResults"]) == 3


async def test_return_to_ai_reviews_again_and_the_evidence_keeps_its_ids(client, run_jobs, sign_in, database):
    card_id = await uc2_card(client, "TX-2026-SANCTION-0102", "aml.mlro-escalation", "alert")
    await run_jobs()
    daniel = await sign_in("u-daniel")
    returned = await client.post(f"/v1/cards/{card_id}/decisions", headers=daniel, json={
        "decision": "RETURN_TO_AI", "rationale": "Compare the registration numbers"})
    assert returned.json()["state"] == "ASSEMBLING"
    await run_jobs()

    card = (await client.get(f"/v1/cards/{card_id}", headers=daniel)).json()
    assert [e["id"] for e in card["evidence"]] == ["E1", "E2", "E3"]
    assert card["evidence"][2]["detail"].endswith(": possible match, score 92.")
    assert card["recommendation"]["version"] == 2
    assert card["recommendation"]["summary"].startswith(
        'Re-reviewed after the instruction "Compare the registration numbers".')
    with psycopg.connect(database) as conn:  # brought up to date, not added again
        assert conn.execute("SELECT count(*) FROM card.card_evidence WHERE kind <> 'recommendation'"
                            ).fetchone()[0] == 3


async def test_the_model_reads_a_nav_exception(client, run_jobs, callbacks, sign_in, app):
    card_id = await nav_exception(client, run_jobs, callbacks, "raw-docs/uc3/2026/10/mgf-JUMP-nav.pdf")
    payload = {"cardId": card_id, "mode": "review-evidence"}
    server = FakeMaas(answer(json.dumps(ADVICE)))
    async with UnitOfWork(app.state.session_factory, actor="svc:jobs-worker", correlation_id="test") as uow:
        await cards.assemble_job(uow, payload, nav_evidence)
    async with UnitOfWork(app.state.session_factory, actor="svc:jobs-worker", correlation_id="test") as uow:
        await cards.review_job(uow, payload, MaasEvidenceReviewer(maas_client(server)), statements.card_facts)

    user = server.user_message()
    assert "Meridian Growth Fund class A (MGF)" in user and "(+6.50 %; fund tolerance 3" in user
    assert "N-02" in user  # the rule that raised the card goes with it
    card = (await client.get(f"/v1/cards/{card_id}", headers=await sign_in("u-lars"))).json()
    assert [e["label"] for e in card["evidence"]] == ["NAV statement"]
    assert (card["state"], card["recommendation"]["decision"]) == ("AWAITING_DECISION", "REJECT")
    assert card["recommendation"]["modelId"] == "deepseek-v4-flash" and card["recommendation"]["citations"] == ["E1"]


async def test_a_review_that_fails_for_good_still_shows_the_evidence(client, run_jobs, callbacks, sign_in, app):
    card_id = await nav_exception(client, run_jobs, callbacks, "raw-docs/uc3/2026/10/afs-STALE-nav.pdf")
    payload = {"cardId": card_id, "mode": "review-evidence"}
    async with UnitOfWork(app.state.session_factory, actor="svc:jobs-worker", correlation_id="test") as uow:
        await cards.assemble_job(uow, payload, nav_evidence)
    async with UnitOfWork(app.state.session_factory, actor="svc:jobs-worker", correlation_id="test") as uow:
        await cards.recommend_failed(uow, payload, "LlmError: the model did not answer")

    card = (await client.get(f"/v1/cards/{card_id}", headers=await sign_in("u-lars"))).json()
    assert (card["state"], card["owner"]["name"], card["recommendation"]) == ("AWAITING_DECISION", "Lars Jansen", None)
    assert card["evidence"][0]["detail"].startswith("Ardent Fund SPC class A (AFS), valued")


async def test_uc1_cards_are_reviewed_from_the_statement_and_the_reported_error(client, run_jobs, callbacks, sign_in):
    statement_id, job_id = await register_and_extract(client, run_jobs, callbacks)
    card_id, _ = await validation_card(client, statement_id, job_id, run_jobs)
    ahmed = await sign_in("u-ahmed")
    card = (await client.get(f"/v1/cards/{card_id}", headers=ahmed)).json()
    assert card["evidence"][0]["detail"].endswith("0 of 12 lines approved, in review")
    assert card["recommendation"]["citations"] == ["E1"]

    failed = await client.post("/v1/cards", headers=n8n(f"{statement_id}:{job_id}:extraction-exception"), json={
        "type": "uc1.extraction-exception", "subjectId": statement_id, "extractionJobId": job_id,
        "status": "failed", "error": "Unreadable scan"})
    await run_jobs()
    card = (await client.get(f"/v1/cards/{failed.json()['cardId']}", headers=ahmed)).json()
    assert [(e["label"], e["source"]) for e in card["evidence"]] == [
        ("Source document", OBJECT_KEY), ("Reported error", f"Workflow report, extraction job {job_id}")]
    assert card["evidence"][1]["detail"] == "failed: Unreadable scan"
    assert card["recommendation"]["citations"] == ["E1", "E2"]
