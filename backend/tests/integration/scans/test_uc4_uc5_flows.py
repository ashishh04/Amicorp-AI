"""UC4 and UC5 the way the workflows run them: scan, poll, fetch, a card per finding, recommend, notify."""
import psycopg
import pytest

from app.shared.audit import verify_chain
from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def headers(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def submit_uc4(client, batch_date: str = "2026-10-28", cap: int = 200, key: str | None = None) -> str:
    body = {"ruleset": "uc4.discrepancy-catalogue", "layer": "bronze", "batchDate": batch_date, "maxNewFindings": cap}
    response = await client.post("/v1/scans", json=body, headers=headers(key or f"uc4:{batch_date}"))
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    return response.json()["scanId"]


async def create_card(client, finding: dict, scan_id: str, card_type: str = "uc4.discrepancy"):
    body = {"type": card_type, "subjectId": finding["subjectId"], "findingId": finding["findingId"],
            "dedupeKey": finding["dedupeKey"], "scanId": scan_id}
    if card_type == "uc5.violation":
        body["policyId"] = finding["policyId"]
    return await client.post("/v1/cards", json=body, headers=headers(finding["dedupeKey"]))


async def test_a_whole_uc4_run(client, run_jobs, database, app):
    scan_id = await submit_uc4(client)
    assert (await client.get(f"/v1/scans/{scan_id}", headers=AUTH)).json()["status"] == "queued"
    early = await client.get(f"/v1/scans/{scan_id}/findings", headers=AUTH)
    assert early.status_code == 409
    assert early.json()["code"] == "SCAN_NOT_COMPLETE"

    await run_jobs()
    assert (await client.get(f"/v1/scans/{scan_id}", headers=AUTH)).json()["status"] == "completed"
    findings = (await client.get(f"/v1/scans/{scan_id}/findings", headers=AUTH)).json()["findings"]
    assert len(findings) == 3
    assert all(f["dedupeKey"] and f["subjectId"] and f["findingId"] for f in findings)  # the "Finding valid?" node

    for finding in findings:
        card = await create_card(client, finding, scan_id)
        assert card.status_code == 201
        assert card.json()["created"] is True and card.json()["state"] == "ASSEMBLING"
        card_id = card.json()["cardId"]
        recommend = await client.post(f"/v1/cards/{card_id}/recommend", json={"mode": "assemble-and-recommend"},
                                      headers=headers(f"{card_id}:recommend"))
        assert recommend.status_code == 202
        notify = await client.post("/v1/notifications", headers=headers(f"{card_id}:card-created"), json={
            "audience": "card-owner", "cardId": card_id, "channel": "teams", "event": "card-created", "digest": True,
        })
        assert notify.status_code == 202

    await run_jobs()
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT state, count(*) FROM card.card GROUP BY state").fetchall() == [
            ("AWAITING_DECISION", 3)
        ]
        assert conn.execute(
            "SELECT kind, count(*) FROM card.card_evidence GROUP BY kind ORDER BY kind"
        ).fetchall() == [("finding", 3), ("recommendation", 3)]
        assert conn.execute("SELECT count(*) FROM ops.notification WHERE status = 'SENT'").fetchone() == (3,)
        assert conn.execute("SELECT count(*) FROM ops.job WHERE status <> 'DONE'").fetchone() == (0,)
    async with app.state.session_factory() as session:
        assert (await verify_chain(session)).ok


async def test_the_next_scan_reports_only_new_problems_and_a_resent_card_is_not_duplicated(client, run_jobs):
    scan_id = await submit_uc4(client, "2026-10-28")
    await run_jobs()
    first = (await client.get(f"/v1/scans/{scan_id}/findings", headers=AUTH)).json()["findings"][0]
    created = await create_card(client, first, scan_id)
    assert created.status_code == 201

    next_scan = await submit_uc4(client, "2026-10-29")
    await run_jobs()
    page = (await client.get(f"/v1/scans/{next_scan}/findings", headers=AUTH)).json()
    assert first["dedupeKey"] not in {f["dedupeKey"] for f in page["findings"]}
    assert len(page["findings"]) == 2

    # Same business key with a different body (tomorrow's scan): the existing card, not a 409.
    again = await create_card(client, first, next_scan)
    assert again.status_code == 200
    assert again.json() == {"cardId": created.json()["cardId"], "created": False, "state": "ASSEMBLING"}


async def test_a_retried_scan_request_returns_the_same_scan(client):
    assert await submit_uc4(client) == await submit_uc4(client)


async def test_max_new_findings_caps_what_is_returned(client, run_jobs):
    scan_id = await submit_uc4(client, cap=2, key="uc4:capped")
    await run_jobs()
    page = (await client.get(f"/v1/scans/{scan_id}/findings", headers=AUTH)).json()
    assert len(page["findings"]) == 2
    assert page["truncated"] is True


async def test_a_scan_needs_exactly_one_window(client):
    body = {"ruleset": "uc4.discrepancy-catalogue", "layer": "bronze", "maxNewFindings": 5}
    assert (await client.post("/v1/scans", json=body, headers=headers("uc4:none"))).status_code == 422


async def test_a_uc5_run_proposes_corrections(client, run_jobs, database):
    body = {"ruleset": "uc5.violation-catalogue", "layer": "gold", "scanWindow": "2026-10-28T09",
            "maxNewFindings": 200}
    scan_id = (await client.post("/v1/scans", json=body, headers=headers("uc5:2026-10-28T09"))).json()["scanId"]
    await run_jobs()
    findings = (await client.get(f"/v1/scans/{scan_id}/findings", headers=AUTH)).json()["findings"]
    assert len(findings) == 2 and all(f["policyId"] for f in findings)
    for finding in findings:
        card_id = (await create_card(client, finding, scan_id, "uc5.violation")).json()["cardId"]
        await client.post(f"/v1/cards/{card_id}/recommend", json={"mode": "propose-correction"},
                          headers=headers(f"{card_id}:recommend"))
    await run_jobs()
    with psycopg.connect(database) as conn:
        rows = conn.execute(
            "SELECT c.state, c.severity, e.detail->>'mode' FROM card.card c "
            "JOIN card.card_evidence e ON e.card_id = c.card_id AND e.kind = 'recommendation'"
        ).fetchall()
    assert rows == [("AWAITING_DECISION", "medium", "propose-correction")] * 2
