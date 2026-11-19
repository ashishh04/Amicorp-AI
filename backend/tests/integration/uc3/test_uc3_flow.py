"""UC3 end to end, as the n8n workflow calls it: NAV intake, extraction and its callback, nav.checks, the card,
and publication on approval. The fake extractor picks the exception from a keyword in the object key."""
import psycopg
import pytest

from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

CALLBACK = "http://127.0.0.1:5678/webhook/nav-statement-extraction-complete"


def n8n(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def extracted_nav(client, run_jobs, callbacks, object_key: str) -> tuple[str, str]:
    registered = await client.post("/v1/nav-statements", headers=n8n(object_key), json={
        "channel": "sftp", "objectKey": object_key, "receivedAt": "2026-10-29T03:00:00Z"})
    assert registered.status_code == 201, registered.text
    statement_id = registered.json()["statementId"]
    job = await client.post("/v1/extraction/jobs", headers=n8n(f"{statement_id}:extract"), json={
        "documentId": statement_id, "profile": "nav-statement", "callbackUrl": CALLBACK})
    assert job.status_code == 202, job.text
    await run_jobs()
    assert callbacks.sent[-1] == (CALLBACK, {"documentId": statement_id, "jobId": job.json()["jobId"],
                                             "status": "succeeded"})
    return statement_id, job.json()["jobId"]


async def nav_checks(client, statement_id: str) -> dict:
    response = await client.post("/v1/gates/evaluate", headers=n8n(f"exec-3:{statement_id}:nav.checks"), json={
        "ruleset": "nav.checks", "subjectType": "nav-statement", "subjectId": statement_id})
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_nav_within_tolerance_is_approved_and_published(client, run_jobs, callbacks, sign_in, database):
    statement_id, job_id = await extracted_nav(client, run_jobs, callbacks, "raw-docs/uc3/2026/10/mgf-nav.pdf")
    checks = await nav_checks(client, statement_id)
    assert (checks["outcome"], checks["matchedRule"]) == ("pass", "N-99")

    created = await client.post("/v1/cards", headers=n8n(f"{statement_id}:{job_id}:nav-approval"), json={
        "type": "nav.approval", "subjectId": statement_id, "extractionJobId": job_id, "gateRunId": checks["runId"]})
    card_id = created.json()["cardId"]
    await run_jobs()  # the evidence review, then the card goes to its owner
    lars = await sign_in("u-lars")
    card = (await client.get(f"/v1/cards/{card_id}", headers=lars)).json()
    assert card["title"].startswith("NAV statement ") and card["title"].endswith("28 Oct 2026")
    assert card["value"]["currency"] == "USD" and card["calendar"] == "EU"
    inputs = {i["name"]: i["value"] for i in card["gateRuns"][0]["inputs"]}
    assert inputs["valuationAgeBusinessDays"] == 1 and inputs["sharesReconciled"] is True

    await client.post(f"/v1/cards/{card_id}/decisions", headers=lars,
                      json={"decision": "APPROVE", "rationale": "NAV checked against the administrator pack"})
    await run_jobs()
    assert (await client.get(f"/v1/cards/{card_id}", headers=lars)).json()["state"] == "CLOSED"
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT state FROM stmt.statement").fetchone()[0] == "SUBMITTED"
        assert conn.execute("SELECT count(*) FROM audit.audit_event WHERE action = 'nav.published'").fetchone()[0] == 1


@pytest.mark.parametrize("keyword, rule", [("STALE", "N-01"), ("JUMP", "N-02"), ("SHARES", "N-03"),
                                           ("afs-JUMP", "N-02")])  # Ardent's 5 % is the widest tolerance
async def test_each_nav_check_raises_an_exception(client, run_jobs, callbacks, keyword, rule):
    statement_id, _ = await extracted_nav(client, run_jobs, callbacks, f"raw-docs/uc3/2026/10/{keyword}-nav.pdf")
    checks = await nav_checks(client, statement_id)
    assert (checks["outcome"], checks["matchedRule"]) == ("exception", rule)


async def test_a_bank_statement_is_not_a_nav_statement(client, run_jobs, callbacks):
    registered = await client.post("/v1/bank-statements", headers=n8n("raw-docs/uc1/x.pdf"), json={
        "channel": "email", "objectKey": "raw-docs/uc1/x.pdf", "receivedAt": "2026-10-29T03:00:00Z"})
    wrong = await client.post("/v1/extraction/jobs", headers=n8n("x:extract"), json={
        "documentId": registered.json()["statementId"], "profile": "nav-statement", "callbackUrl": CALLBACK})
    assert wrong.status_code == 422 and wrong.json()["code"] == "WRONG_PROFILE"
