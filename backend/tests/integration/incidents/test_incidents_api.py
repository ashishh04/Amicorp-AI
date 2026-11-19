"""POST /v1/incidents as the Platform error handler (AmiErrHandler001) calls it."""
import asyncio
import uuid

import psycopg
import pytest

from app.shared.audit import verify_chain
from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

INCIDENT = {
    "source": "n8n",
    "workflowId": "vPwRzUT00rVmHcz6",
    "workflowName": "UC1 Bank statement processing",
    "executionId": "1001",
    "executionUrl": "http://localhost:5678/workflow/vPwRzUT00rVmHcz6/executions/1001",
    "failedNode": "Register statement",
    "message": "The resource you are requesting could not be found",
}


def headers(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def test_needs_a_bearer_token(client):
    response = await client.post("/v1/incidents", json=INCIDENT, headers={"Idempotency-Key": "incident:1001"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_needs_an_idempotency_key(client):
    response = await client.post("/v1/incidents", json=INCIDENT, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_records_an_incident_and_audits_it(client, app):
    response = await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001"))
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    uuid.UUID(body["incidentId"])

    async with app.state.session_factory() as session:
        check = await verify_chain(session)
    assert check.ok and check.checked == 1


async def test_a_retry_replays_the_first_response(client):
    first = await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001"))
    second = await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001"))
    assert second.status_code == first.status_code == 201
    assert second.json() == first.json()
    assert second.headers["idempotent-replayed"] == "true"


async def test_a_reused_key_with_a_different_body_is_refused(client):
    await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001"))
    changed = {**INCIDENT, "message": "something else"}
    response = await client.post("/v1/incidents", json=changed, headers=headers("incident:1001"))
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_the_same_execution_reported_again_returns_the_existing_incident(client):
    first = await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001"))
    again = await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001:second-report"))
    assert again.status_code == 200
    assert again.json() == {"incidentId": first.json()["incidentId"], "created": False}


async def test_concurrent_duplicates_create_one_incident(client, database):
    responses = await asyncio.gather(*[
        client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001")) for _ in range(5)
    ])
    assert {r.status_code for r in responses} <= {201, 409}
    assert any(r.status_code == 201 for r in responses)
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM ops.incident").fetchone() == (1,)


async def test_unknown_fields_are_rejected_without_echoing_values(client):
    response = await client.post(
        "/v1/incidents", json={**INCIDENT, "accountNumber": "GB82WEST12345698765432"}, headers=headers("k-1")
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert "GB82WEST12345698765432" not in response.text
    assert body["errors"][0]["loc"][-1] == "accountNumber"


async def test_the_automation_role_cannot_read_incidents(client):
    created = await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001"))
    response = await client.get(f"/v1/incidents/{created.json()['incidentId']}", headers=AUTH)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_oversized_bodies_are_refused(client):
    huge = {**INCIDENT, "message": "x" * 1_100_000}
    response = await client.post("/v1/incidents", json=huge, headers=headers("k-2"))
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


async def test_audit_rows_cannot_be_changed_even_in_the_database(client, database):
    await client.post("/v1/incidents", json=INCIDENT, headers=headers("incident:1001"))
    with psycopg.connect(database) as conn, pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("UPDATE audit.audit_event SET actor = 'someone-else'")


async def test_the_correlation_id_is_echoed_or_replaced(client):
    kept = await client.get("/health", headers={"X-Correlation-Id": "n8n-exec-1001"})
    assert kept.headers["x-correlation-id"] == "n8n-exec-1001"
    replaced = await client.get("/health", headers={"X-Correlation-Id": "bad id\nwith newline"})
    assert replaced.headers["x-correlation-id"] != "bad id\nwith newline"
