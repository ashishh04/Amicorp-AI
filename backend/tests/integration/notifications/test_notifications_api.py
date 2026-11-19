"""POST /v1/notifications with the bodies the workflows send."""
import uuid

import pytest

from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def headers(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def test_queues_a_card_created_notification(client):
    card_id = str(uuid.uuid4())
    body = {"audience": "card-owner", "cardId": card_id, "channel": "teams", "event": "card-created", "digest": True}
    response = await client.post("/v1/notifications", json=body, headers=headers(f"{card_id}:card-created"))
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    uuid.UUID(response.json()["notificationId"])


async def test_queues_the_sweeper_escalation(client):
    body = {
        "audience": "role:platform-support", "channel": "teams", "event": "stuck-items-escalated",
        "sweepId": "sweep-7", "escalatedCount": 2,
    }
    response = await client.post("/v1/notifications", json=body, headers=headers("redrive:77:notify"))
    assert response.status_code == 202


async def test_the_worker_delivers_a_queued_notification(client, run_jobs, database):
    body = {"audience": "role:platform-support", "channel": "teams", "event": "workflow-failed"}
    assert (await client.post("/v1/notifications", json=body, headers=headers("incident:1:notify"))).status_code == 202
    assert await run_jobs() == 1
    import psycopg

    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT status, attempts FROM ops.notification").fetchone() == ("SENT", 1)


async def test_card_owner_needs_a_card(client):
    body = {"audience": "card-owner", "channel": "teams", "event": "card-created"}
    response = await client.post("/v1/notifications", json=body, headers=headers("k-1"))
    assert response.status_code == 422


async def test_free_text_audiences_are_refused(client):
    body = {"audience": "someone@example.com", "channel": "teams", "event": "card-created"}
    response = await client.post("/v1/notifications", json=body, headers=headers("k-2"))
    assert response.status_code == 422
