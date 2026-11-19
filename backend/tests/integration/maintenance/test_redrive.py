"""The stuck-item sweeper (POST /v1/maintenance/redrive), as n8n's Platform stuck-item sweeper calls it."""
import psycopg
import pytest

from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

CALLBACK = "http://127.0.0.1:5678/webhook/bank-statement-extraction-complete"


def n8n(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def redrive(client, key: str, *scopes: str, max_attempts: int = 3) -> dict:
    response = await client.post("/v1/maintenance/redrive", headers=n8n(key), json={
        "olderThanMinutes": 30, "maxAttempts": max_attempts, "scopes": list(scopes)})
    assert response.status_code == 200, response.text
    return response.json()


async def stuck_statement(client, database: str, name: str) -> str:
    statement_id = (await client.post("/v1/bank-statements", headers=n8n(name), json={
        "channel": "email", "objectKey": name, "receivedAt": "2026-10-30T01:00:00Z"})).json()["statementId"]
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("UPDATE stmt.statement SET created_at = now() - interval '2 hours' WHERE statement_id = %s",
                     (statement_id,))
    return statement_id


async def test_a_statement_never_sent_to_extraction_is_sent_again(client, database, run_jobs, callbacks):
    statement_id = await stuck_statement(client, database, "raw-docs/uc1/stuck-1.pdf")
    result = await redrive(client, "redrive:1", "uc1.statement", "uc3.nav-statement")
    assert (result["redrivenCount"], result["escalatedCount"]) == (1, 0)
    assert result["items"] == [{"scope": "uc1.statement", "itemId": statement_id, "action": "redriven"}]
    await run_jobs()
    assert callbacks.sent[-1][1]["documentId"] == statement_id  # n8n hears about it as if it had asked
    assert (await redrive(client, "redrive:2", "uc1.statement"))["items"] == []  # no longer stuck


async def test_an_item_out_of_attempts_is_escalated_once(client, database):
    statement_id = await stuck_statement(client, database, "raw-docs/uc1/stuck-2.pdf")
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("INSERT INTO ops.redrive (scope, item_id, attempts, last_redriven_at) "
                     "VALUES ('uc1.statement', %s, 2, now())", (statement_id,))
    result = await redrive(client, "redrive:3", "uc1.statement", max_attempts=2)
    assert result["items"] == [{"scope": "uc1.statement", "itemId": statement_id, "action": "escalated"}]
    assert result["escalatedCount"] == 1
    assert (await redrive(client, "redrive:4", "uc1.statement", max_attempts=2))["items"] == []
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT workflow_id, failed_node FROM ops.incident").fetchall() == [
            ("platform.stuck-item-sweeper", "uc1.statement")]


async def test_a_callback_n8n_never_acknowledged_is_sent_again(client, database, run_jobs, callbacks):
    callbacks.refuse = True
    statement_id = (await client.post("/v1/bank-statements", headers=n8n("raw-docs/uc1/cb.pdf"), json={
        "channel": "email", "objectKey": "raw-docs/uc1/cb.pdf", "receivedAt": "2026-10-30T01:00:00Z"})).json()[
        "statementId"]
    await client.post("/v1/extraction/jobs", headers=n8n(f"{statement_id}:extract"), json={
        "documentId": statement_id, "profile": "bank-statement", "callbackUrl": CALLBACK})
    await run_jobs()
    with psycopg.connect(database, autocommit=True) as conn:  # the callback job gave up long ago
        conn.execute("UPDATE ops.job SET status = 'FAILED' WHERE kind = 'extraction.callback'")
        conn.execute("UPDATE ops.extraction_job SET finished_at = now() - interval '2 hours'")
    callbacks.refuse = False
    result = await redrive(client, "redrive:5", "extraction.job")
    assert result["redrivenCount"] == 1
    await run_jobs()
    assert callbacks.sent and callbacks.sent[-1][1]["documentId"] == statement_id


async def test_a_payment_never_enriched_is_offered_to_the_poller_again(client, database):
    await client.post("/v1/transactions", headers=n8n("TX-STUCK-1"), json={
        "transactionId": "TX-STUCK-1", "source": "realtime", "receivedAt": "2026-10-30T01:00:00Z"})
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("UPDATE txn.transaction SET received_at = now() - interval '2 hours'")
    assert (await redrive(client, "redrive:6", "uc2.transaction"))["redrivenCount"] == 1
    claimed = await client.post("/v1/payment-requests/claim", headers=n8n("uc2-poll:9"), json={"status": "new"})
    assert [i["transactionId"] for i in claimed.json()["items"]] == ["TX-STUCK-1"]
