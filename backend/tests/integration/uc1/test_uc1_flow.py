"""UC1 end to end: the calls the n8n workflow makes, then the validation workspace and the decision."""
import uuid

import psycopg
import pytest

from app.db.session import UnitOfWork
from app.modules.extraction import service as extraction
from app.shared.audit import verify_chain
from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

CALLBACK = "http://127.0.0.1:5678/webhook/bank-statement-extraction-complete"
OBJECT_KEY = "raw-docs/uc1/2026/10/hsbc-848-838.pdf"
INTAKE = {"channel": "email", "objectKey": OBJECT_KEY, "receivedAt": "2026-10-28T03:00:00Z"}


def n8n(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def register(client) -> str:
    response = await client.post("/v1/bank-statements", json=INTAKE, headers=n8n(OBJECT_KEY))
    assert response.status_code in (200, 201), response.text
    return response.json()["statementId"]


async def register_and_extract(client, run_jobs, callbacks) -> tuple[str, str]:
    statement_id = await register(client)
    job = await client.post("/v1/extraction/jobs", headers=n8n(f"{statement_id}:extract"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": CALLBACK})
    assert job.status_code == 202, job.text
    await run_jobs()
    return statement_id, job.json()["jobId"]


async def validation_card(client, statement_id: str, job_id: str, run_jobs) -> tuple[str, dict]:
    gate = await client.post("/v1/gates/evaluate", headers=n8n(f"48812:{statement_id}:uc1.field-validation"), json={
        "ruleset": "uc1.field-validation", "subjectType": "statement", "subjectId": statement_id})
    assert gate.status_code == 200, gate.text
    card = await client.post("/v1/cards", headers=n8n(f"{statement_id}:{job_id}:validation"), json={
        "type": "uc1.statement-validation", "subjectId": statement_id, "extractionJobId": job_id,
        "gateRunId": gate.json()["runId"], "gateOutcome": gate.json()["outcome"]})
    assert card.status_code == 201, card.text
    await run_jobs()  # the evidence review hands the card to its owner
    return card.json()["cardId"], gate.json()


async def test_a_statement_goes_from_intake_to_a_closed_card(client, run_jobs, callbacks, sign_in, app):
    # n8n: intake is idempotent on objectKey.
    again = await client.post("/v1/bank-statements", json=INTAKE, headers=n8n(OBJECT_KEY))
    statement_id, job_id = await register_and_extract(client, run_jobs, callbacks)
    repeat = await client.post("/v1/bank-statements", json={**INTAKE, "receivedAt": "2026-10-28T03:05:00Z"},
                               headers=n8n(OBJECT_KEY))
    assert again.status_code == 201 and repeat.status_code == 200
    assert repeat.json() == {"statementId": statement_id, "created": False}
    assert callbacks.sent == [(CALLBACK, {"documentId": statement_id, "jobId": job_id, "status": "succeeded"})]

    card_id, gate = await validation_card(client, statement_id, job_id, run_jobs)
    assert (gate["outcome"], gate["rulesetVersion"], gate["matchedRule"]) == ("needs-review", 2, "F-02")

    # The Maker opens the card and the workspace.
    chan, ahmed = await sign_in("u-chan"), await sign_in("u-ahmed")
    card = (await client.get(f"/v1/cards/{card_id}", headers=chan)).json()
    assert card["title"] == "Bank statement Lumen Capital SPC - Segregated Portfolio 2, HSBC Hong Kong, Sep 2026"
    assert card["value"] == {"amount": 179529.35, "currency": "USD"}
    assert (card["owner"]["name"], card["maker"]["name"], card["state"]) == ("Ahmed Khan", "None yet",
                                                                               "AWAITING_DECISION")
    assert card["statement"] == {"id": statement_id, "approved": 0, "total": 12, "status": "IN_REVIEW"}
    assert card["gateRuns"][0]["rulesetName"] == "Bank statement field validation"
    assert {i["name"]: i["value"] for i in card["gateRuns"][0]["inputs"]} == {
        "pages": 2, "minConfidence": 0.0, "balanceBreaks": 1, "datesOutsidePeriod": 1}
    assert card["evidence"][0]["kind"] == "statement" and card["evidence"][0]["statementId"] == statement_id
    assert card["actions"]["APPROVE"] == {
        "allowed": False, "reason": "Approve and Reject need the Checker role in the Operations team."}
    assert card["actions"]["RETURN_TO_AI"] == {"allowed": True, "reason": None}

    header = (await client.get(f"/v1/statements/{statement_id}", headers=chan)).json()
    assert header["cardId"] == card_id and header["editable"]["allowed"] is True
    assert {c["id"]: c["status"] for c in header["checks"]} == {
        "S1": "fail", "S2": "pass", "S3": "fail", "S4": "fail", "S5": "fail", "S6": "fail"}
    assert all(r["valid"] for r in header["references"])

    lines = {line["lineNo"]: line for line in (await client.get(f"/v1/statements/{statement_id}/lines",
                                                                headers=chan)).json()["items"]}
    assert lines[6]["approve"] == {"allowed": False, "reason": "Correct the flagged field first: debit."}

    def line_url(no: int) -> str:
        return f"/v1/statements/{statement_id}/lines/{lines[no]['lineId']}"

    refused = await client.post(f"{line_url(6)}/approve", headers=chan)
    assert refused.status_code == 422 and refused.json()["title"] == "Review required"
    assert (await client.patch(line_url(6), json={"debit": 1250}, headers={**chan, "If-Match": 'W/"9"'})
            ).status_code == 412
    assert (await client.patch(line_url(6), json={"debit": 1250}, headers=chan)).status_code == 428
    unknown = await client.patch(line_url(8), json={"enNumber": "EN-20471"}, headers={**chan, "If-Match": 'W/"1"'})
    assert unknown.status_code == 422 and unknown.json()["detail"].startswith("EN-20471 is not in today")

    for no, change in [(6, {"debit": 1250}), (9, {"valueDate": "2026-09-23"}), (5, {"enNumber": "EN-20417"}),
                       (8, {"enNumber": "EN-20417"})]:
        fixed = await client.patch(line_url(no), json=change, headers={**chan, "If-Match": lines[no]["etag"]})
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["etag"] == 'W/"2"' and fixed.json()["correctedBy"]["name"] == "Chan Tai Man"
    for no in lines:
        assert (await client.post(f"{line_url(no)}/approve", headers=chan)).json()["approved"] is True

    submitted = await client.post(f"/v1/statements/{statement_id}/submit", headers=chan)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    assert {c["status"] for c in submitted.json()["checks"]} == {"pass"}
    assert submitted.json()["editable"] == {"allowed": False, "reason": "The statement was submitted and is read only."}

    # The owner, a different person from the maker, approves; the write-back closes the card.
    card = (await client.get(f"/v1/cards/{card_id}", headers=ahmed)).json()
    assert card["maker"]["name"] == "Chan Tai Man" and card["mandatoryChecks"][0]["met"] is True
    assert card["actions"]["APPROVE"]["allowed"] is True
    approved = await client.post(f"/v1/cards/{card_id}/decisions", headers=ahmed,
                                 json={"decision": "APPROVE", "rationale": "Lines reconcile to the bank figure"})
    assert approved.status_code == 200 and approved.json()["state"] == "WRITING_BACK"
    await run_jobs()
    closed = (await client.get(f"/v1/cards/{card_id}", headers=ahmed)).json()
    assert closed["state"] == "CLOSED"
    assert [h["action"] for h in closed["history"]][-4:] == [
        "Submitted statement", "Approve", "Write-back started", "Write-back confirmed"]

    async with UnitOfWork(app.state.session_factory, actor="test", correlation_id=None) as uow:
        assert (await verify_chain(uow.session)).ok


async def test_unfinished_lines_block_the_submit_and_the_approve(client, run_jobs, callbacks, sign_in):
    statement_id, job_id = await register_and_extract(client, run_jobs, callbacks)
    card_id, _ = await validation_card(client, statement_id, job_id, run_jobs)
    chan, ahmed = await sign_in("u-chan"), await sign_in("u-ahmed")

    refused = await client.post(f"/v1/statements/{statement_id}/submit", headers=chan)
    body = refused.json()
    assert refused.status_code == 422 and body["title"] == "Checks failed"
    assert body["detail"] == "5 of 6 requirements-before-save gates failed. The statement stays with you."
    assert {"message": "S1: Line 9: 2026-10-23 is outside 2026-09-01 to 2026-09-30", "lineNo": 9,
            "field": "valueDate"} in body["failures"]

    early = await client.post(f"/v1/cards/{card_id}/decisions", headers=ahmed,
                              json={"decision": "APPROVE", "rationale": "Looks fine"})
    assert early.status_code == 422 and early.json()["detail"].startswith("Approve once every mandatory check is met")


async def test_only_makers_of_the_owning_team_edit(client, run_jobs, callbacks, sign_in):
    statement_id, _ = await register_and_extract(client, run_jobs, callbacks)
    chan = await sign_in("u-chan")
    line = (await client.get(f"/v1/statements/{statement_id}/lines", headers=chan)).json()["items"][0]
    url = f"/v1/statements/{statement_id}/lines/{line['lineId']}/approve"

    checker = await client.post(url, headers=await sign_in("u-priya"))  # holds no Maker role
    other_team = await client.get(f"/v1/statements/{statement_id}", headers=await sign_in("u-sofia"))
    auditor = await client.get(f"/v1/statements/{statement_id}", headers=await sign_in("u-martin"))
    assert checker.status_code == 403
    assert other_team.status_code == 403 and other_team.json()["title"] == "Outside your scope"
    assert auditor.status_code == 200 and auditor.json()["editable"]["allowed"] is False


async def test_extraction_calls_back_only_to_the_n8n_webhook(client, run_jobs, callbacks):
    statement_id = await register(client)
    elsewhere = await client.post("/v1/extraction/jobs", headers=n8n("k-1"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": "http://169.254.169.254/latest"})
    missing = await client.post("/v1/extraction/jobs", headers=n8n("k-2"), json={
        "documentId": str(uuid.uuid4()), "profile": "bank-statement", "callbackUrl": CALLBACK})
    assert elsewhere.status_code == 422 and elsewhere.json()["code"] == "CALLBACK_NOT_ALLOWED"
    assert missing.status_code == 404

    await client.post("/v1/extraction/jobs", headers=n8n("k-3"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": CALLBACK})
    await run_jobs()
    twice = await client.post("/v1/extraction/jobs", headers=n8n("k-4"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": CALLBACK})
    assert twice.status_code == 409


async def test_a_failed_extraction_still_calls_n8n_back(client, run_jobs, callbacks, app, database):
    statement_id = await register(client)
    job_id = (await client.post("/v1/extraction/jobs", headers=n8n(f"{statement_id}:extract"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": CALLBACK})).json()["jobId"]
    async with UnitOfWork(app.state.session_factory, actor="svc:jobs-worker", correlation_id="test") as uow:
        await extraction.run_failed(uow, {"jobId": job_id}, "TimeoutError: the GPU node did not answer")
    await run_jobs()
    assert callbacks.sent == [(CALLBACK, {"documentId": statement_id, "jobId": job_id, "status": "failed",
                                          "error": "TimeoutError: the GPU node did not answer"})]
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT state FROM stmt.statement").fetchone()[0] == "FAILED"
    retry = await client.post("/v1/extraction/jobs", headers=n8n(f"{statement_id}:extract:2"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": CALLBACK})
    assert retry.status_code == 202  # a failed statement may be extracted again


async def test_a_callback_n8n_refuses_is_retried_not_lost(client, run_jobs, callbacks, database):
    callbacks.refuse = True
    statement_id, job_id = await register_and_extract(client, run_jobs, callbacks)
    with psycopg.connect(database) as conn:
        acked = conn.execute("SELECT callback_acked FROM ops.extraction_job").fetchone()[0]
        status, attempts = conn.execute(
            "SELECT status, attempts FROM ops.job WHERE kind = 'extraction.callback'").fetchone()
    assert (acked, status, attempts) == (False, "QUEUED", 1)

    callbacks.refuse = False
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("UPDATE ops.job SET run_after = now() WHERE kind = 'extraction.callback'")
    await run_jobs()
    assert callbacks.sent == [(CALLBACK, {"documentId": statement_id, "jobId": job_id, "status": "succeeded"})]


async def test_gate_evaluations_replay_and_refuse_what_they_cannot_read(client, run_jobs, callbacks):
    statement_id = await register(client)
    body = {"ruleset": "uc1.field-validation", "subjectType": "statement", "subjectId": statement_id}
    not_extracted = await client.post("/v1/gates/evaluate", json=body, headers=n8n("e1"))
    unknown = await client.post("/v1/gates/evaluate", json={**body, "ruleset": "uc9.none"}, headers=n8n("e2"))
    wrong_type = await client.post("/v1/gates/evaluate", json={**body, "subjectType": "transaction"},
                                   headers=n8n("e3"))
    assert (not_extracted.status_code, unknown.status_code, wrong_type.status_code) == (409, 404, 422)

    await client.post("/v1/extraction/jobs", headers=n8n("x"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": CALLBACK})
    await run_jobs()
    first = await client.post("/v1/gates/evaluate", json=body, headers=n8n("e4"))
    replay = await client.post("/v1/gates/evaluate", json=body, headers=n8n("e4"))
    assert first.json()["runId"] == replay.json()["runId"]
    assert replay.headers["Idempotent-Replayed"] == "true"
