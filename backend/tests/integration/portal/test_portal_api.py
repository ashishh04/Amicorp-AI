"""The portal endpoints (frontend docs/portal-api-contract.md), with the sample officers signed in locally."""
import uuid

import psycopg
import pytest

from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def n8n(key: str) -> dict[str, str]:
    return {**AUTH, "Idempotency-Key": key}


async def new_card(client, body: dict, key: str | None = None) -> str:
    response = await client.post("/v1/cards", json=body, headers=n8n(key or str(uuid.uuid4())))
    assert response.status_code == 201, response.text
    return response.json()["cardId"]


def extraction_exception(subject: str) -> dict:
    return {"type": "uc1.extraction-exception", "subjectId": subject, "extractionJobId": str(uuid.uuid4()),
            "status": "failed", "error": "Unreadable scan"}


def gate_exception(subject: str) -> dict:
    return {"type": "aml.gate-exception", "subjectId": subject, "blocksTransaction": True,
            "failedAt": "Gate 3 Risk and screening", "error": "Screening provider unavailable"}


async def test_me_and_the_data_scope(client, sign_in):
    me = (await client.get("/v1/me", headers=await sign_in("u-sofia"))).json()
    assert (me["displayName"], me["roles"], me["teams"], me["calendar"]) == (
        "Sofia Rossi", ["Maker"], ["Fund accounting"], "EU")
    groups = (await client.get("/v1/settings/data-scope", headers=await sign_in("u-grace"))).json()["items"]
    assert {"group": "AMC-IPA-Checker-Operations", "team": "Operations", "role": "Checker", "calendar": "HK",
            "members": 2, "scope": "HK client book"} in groups
    assert (await client.get("/v1/settings/data-scope", headers=await sign_in("u-priya"))).status_code == 403
    assert (await client.get("/v1/me", headers={"Authorization": "Bearer not-a-token"})).status_code == 401


async def test_each_officer_sees_only_their_scope(client, sign_in):
    ops = await new_card(client, extraction_exception("ST-1"))
    compliance = await new_card(client, gate_exception("TX-1"))
    escalation = await new_card(client, {"type": "aml.mlro-escalation", "subjectId": "TX-2", "blocksTransaction": True,
                                         "screeningOutcome": "alert", "gateRunIds": [str(uuid.uuid4())]})

    async def ids(handle: str) -> set[str]:
        response = await client.get("/v1/cards", headers=await sign_in(handle))
        assert response.status_code == 200, response.text
        return {c["id"] for c in response.json()["items"]}

    assert await ids("u-priya") == {ops}
    assert await ids("u-kenneth") == {compliance}
    assert await ids("u-daniel") == {compliance, escalation}  # the MLRO sees every AML card
    assert await ids("u-martin") == {ops, compliance, escalation}
    assert (await client.get("/v1/cards", headers=await sign_in("u-grace"))).status_code == 403  # Admins see none

    outside = await client.get(f"/v1/cards/{compliance}", headers=await sign_in("u-priya"))
    assert outside.status_code == 403
    assert outside.json()["title"] == "Outside your scope"
    assert outside.json()["detail"].endswith("belongs to the Compliance team, which is outside your data scope.")

    held = (await client.get(f"/v1/cards/{compliance}", headers=await sign_in("u-kenneth"))).json()
    assert held["hold"] == "Payment TX-1 is held in 5 Series until this card is decided."
    assert (held["sla"], held["calendar"], held["escalationRole"]) == ("2 business hours", "HK", "MLRO")


async def test_inbox_views_filters_counts_and_paging(client, sign_in, run_jobs):
    for n in range(3):
        await new_card(client, extraction_exception(f"ST-{n}"))
    await new_card(client, gate_exception("TX-9"))
    await run_jobs()  # the evidence review hands each card to its owner
    priya, martin = await sign_in("u-priya"), await sign_in("u-martin")

    counts = (await client.get("/v1/cards/counts", headers=priya)).json()
    assert counts == {"mine": 1, "team": 3, "due-soon": 0, "overdue": 0, "escalated": 0, "closed": 0}
    mine = (await client.get("/v1/cards", params={"view": "mine"}, headers=priya)).json()["items"]
    assert [c["owner"]["name"] for c in mine] == ["Priya Lam"]  # the three were shared out by load

    first = (await client.get("/v1/cards", params={"limit": 2}, headers=priya)).json()
    second = (await client.get("/v1/cards", params={"limit": 2, "cursor": first["nextCursor"]}, headers=priya)).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1 and second["nextCursor"] is None
    dues = [c["dueAt"] for c in first["items"] + second["items"]]
    assert dues == sorted(dues)
    assert (await client.get("/v1/cards", params={"cursor": "bm90LWEtY3Vyc29y"}, headers=priya)).status_code == 400

    uc2 = (await client.get("/v1/cards", params={"useCase": "UC2"}, headers=martin)).json()["items"]
    assert [c["subjectId"] for c in uc2] == ["TX-9"]
    found = (await client.get("/v1/cards", params={"q": "st-1"}, headers=martin)).json()["items"]
    assert [c["subjectId"] for c in found] == ["ST-1"]


async def test_reject_needs_a_rationale_and_only_the_owner_decides(client, sign_in, run_jobs):
    card_id = await new_card(client, extraction_exception("ST-7"))
    await run_jobs()
    ahmed, priya, martin = await sign_in("u-ahmed"), await sign_in("u-priya"), await sign_in("u-martin")
    url = f"/v1/cards/{card_id}/decisions"

    not_owner = await client.post(url, json={"decision": "REJECT", "rationale": "Duplicate upload"}, headers=priya)
    assert not_owner.status_code == 403
    assert not_owner.json()["detail"] == "Only the owner (Ahmed Khan) or their delegate can decide this card."
    assert (await client.post(url, json={"decision": "REJECT", "rationale": "x"}, headers=martin)).status_code == 403
    blank = await client.post(url, json={"decision": "REJECT", "rationale": ""}, headers=ahmed)
    assert blank.status_code == 422 and blank.json()["title"] == "Rationale required"

    rejected = await client.post(url, json={"decision": "REJECT", "rationale": "Duplicate upload"}, headers=ahmed)
    assert rejected.status_code == 200 and rejected.json()["state"] == "CLOSED"
    history = [(h["actor"], h["action"], h["note"]) for h in rejected.json()["history"]]
    assert ("Ahmed Khan", "Reject", "Duplicate upload") in history
    assert rejected.json()["actions"]["APPROVE"]["reason"].startswith("The card is closed")
    again = await client.post(url, json={"decision": "REJECT", "rationale": "Duplicate upload"}, headers=ahmed)
    assert again.status_code == 409


async def test_delegation_goes_only_to_someone_on_the_list(client, sign_in, run_jobs):
    card_id = await new_card(client, extraction_exception("ST-8"))
    await run_jobs()
    ahmed = await sign_in("u-ahmed")
    delegates = (await client.get(f"/v1/cards/{card_id}/delegates", headers=ahmed)).json()["items"]
    assert [d["name"] for d in delegates] == ["Priya Lam"]

    url = f"/v1/cards/{card_id}/decisions"
    stranger = await client.post(url, headers=ahmed, json={
        "decision": "DELEGATE", "rationale": "On leave", "delegateTo": str(uuid.uuid4())})
    assert stranger.status_code == 422 and stranger.json()["title"] == "Choose a delegate"
    moved = await client.post(url, headers={**ahmed, "Idempotency-Key": "delegate-1"}, json={
        "decision": "DELEGATE", "rationale": "On leave", "delegateTo": delegates[0]["id"]})
    replayed = await client.post(url, headers={**ahmed, "Idempotency-Key": "delegate-1"}, json={
        "decision": "DELEGATE", "rationale": "On leave", "delegateTo": delegates[0]["id"]})
    assert moved.status_code == 200 and replayed.headers["Idempotent-Replayed"] == "true"
    card = moved.json()
    assert card["owner"]["name"] == "Priya Lam" and [p["name"] for p in card["delegationChain"]] == ["Ahmed Khan"]
    assert card["history"][-1]["action"] == "Delegated to Priya Lam"
    assert card["state"] == "AWAITING_DECISION"


async def test_return_to_ai_reassembles_and_the_fourth_return_escalates(client, sign_in, run_jobs):
    card_id = await new_card(client, {"type": "uc4.discrepancy", "subjectId": "ENT-61027",
                                      "findingId": str(uuid.uuid4()), "dedupeKey": "uc4:D-01:ENT-61027",
                                      "scanId": str(uuid.uuid4())})
    await client.post(f"/v1/cards/{card_id}/recommend", json={"mode": "assemble-and-recommend"},
                      headers=n8n(f"{card_id}:recommend"))
    await run_jobs()
    meiling = await sign_in("u-meiling")  # the least-loaded Data team Checker, first by name
    card = (await client.get(f"/v1/cards/{card_id}", headers=meiling)).json()
    assert (card["state"], card["owner"]["name"], card["recommendation"]["version"]) == (
        "AWAITING_DECISION", "Mei Ling Tan", 1)

    url = f"/v1/cards/{card_id}/decisions"
    for n in range(1, 4):
        returned = await client.post(url, headers=meiling, json={"decision": "RETURN_TO_AI",
                                                                 "rationale": f"Check the address ({n})"})
        assert returned.json()["state"] == "ASSEMBLING"
        await run_jobs()
    card = (await client.get(f"/v1/cards/{card_id}", headers=meiling)).json()
    assert card["returns"] == 3 and card["recommendation"]["version"] == 4
    assert card["recommendation"]["summary"].startswith('Re-assembled after the instruction "Check the address (3)"')

    fourth = await client.post(url, headers=meiling, json={"decision": "RETURN_TO_AI", "rationale": "Once more"})
    assert fourth.json()["state"] == "ESCALATED"
    assert fourth.json()["history"][-1]["note"] == "More than 3 returns to the AI"
    counts = (await client.get("/v1/cards/counts", headers=meiling)).json()
    assert counts["escalated"] == 1


async def test_return_to_ai_runs_the_card_type_s_own_step(client, sign_in, run_jobs, database):
    uc5 = await new_card(client, {"type": "uc5.violation", "subjectId": "ENT-61028", "policyId": "P-07",
                                  "findingId": str(uuid.uuid4()), "dedupeKey": "uc5:P-07:ENT-61028",
                                  "scanId": str(uuid.uuid4())})
    await client.post(f"/v1/cards/{uc5}/recommend", json={"mode": "propose-correction"},
                      headers=n8n(f"{uc5}:recommend"))
    await run_jobs()
    returned = await client.post(f"/v1/cards/{uc5}/decisions", headers=await sign_in("u-meiling"),
                                 json={"decision": "RETURN_TO_AI", "rationale": "Propose the 5 Series change"})
    assert returned.json()["state"] == "ASSEMBLING"
    await run_jobs()
    with psycopg.connect(database) as conn:
        modes = conn.execute("SELECT detail->>'mode' FROM card.card_evidence WHERE card_id = %s AND kind = "
                             "'recommendation'", (uuid.UUID(uc5),)).fetchall()
    assert modes == [("propose-correction",)] * 2  # UC5's own prompt both times, not UC4's

    # A UC1 card runs its evidence review again, with the officer's instruction; the return counts.
    ops = await new_card(client, extraction_exception("ST-7"))
    await run_jobs()
    ahmed = await sign_in("u-ahmed")
    card = (await client.post(f"/v1/cards/{ops}/decisions", headers=ahmed,
                              json={"decision": "RETURN_TO_AI", "rationale": "Try the second scan"})).json()
    assert (card["state"], card["returns"]) == ("ASSEMBLING", 1)
    await run_jobs()
    after = (await client.get(f"/v1/cards/{ops}", headers=ahmed)).json()
    assert (after["state"], after["recommendation"]["version"]) == ("AWAITING_DECISION", 2)
    assert after["recommendation"]["summary"].startswith('Re-reviewed after the instruction "Try the second scan".')


async def test_audit_search_and_the_mlro_s_view(client, sign_in, run_jobs):
    ops = await new_card(client, extraction_exception("ST-5"))
    await new_card(client, gate_exception("TX-5"))
    await run_jobs()
    await client.post(f"/v1/cards/{ops}/decisions", headers=await sign_in("u-ahmed"),
                      json={"decision": "REJECT", "rationale": "Duplicate upload"})
    martin, daniel = await sign_in("u-martin"), await sign_in("u-daniel")

    events = (await client.get("/v1/audit/events", headers=martin)).json()["items"]
    seqs = [int(e["id"]) for e in events]
    assert seqs == sorted(seqs, reverse=True)
    created = next(e for e in events if e["action"] == "card.created")
    assert (created["actor"], created["actorRole"]) == ("n8n (automation)", "Automation")
    decided = next(e for e in events if e["action"] == "card.decided")
    assert (decided["actor"], decided["actorRole"], decided["domain"]) == ("Ahmed Khan", "Checker", "General")
    assert "Duplicate upload" in decided["detail"]

    aml = (await client.get("/v1/audit/events", headers=daniel)).json()["items"]
    assert aml and {e["domain"] for e in aml} == {"AML"}
    by_ahmed = (await client.get("/v1/audit/events", params={"actor": "ahmed"}, headers=martin)).json()["items"]
    assert {e["actor"] for e in by_ahmed} == {"Ahmed Khan"}
    page = (await client.get("/v1/audit/events", params={"limit": 2}, headers=martin)).json()
    rest = (await client.get("/v1/audit/events", params={"limit": 2, "cursor": page["nextCursor"]},
                             headers=martin)).json()
    assert int(rest["items"][0]["id"]) < int(page["items"][-1]["id"])
    assert (await client.get("/v1/audit/events", headers=await sign_in("u-priya"))).status_code == 403


async def test_reference_endpoints(client, sign_in):
    grace = await sign_in("u-grace")
    types = (await client.get("/v1/card-types", headers=grace)).json()["items"]
    assert len(types) == 11 and {"type": "uc5.violation", "version": 1, "team": "Data team", "severity": "by policy",
                                 "sla": "by policy", "escalationRole": "Head of Data",
                                 "onApproval": "Approved correction written to CARE or 5 Series",
                                 "decidedBy": "Checker"} in types
    lumen = (await client.get("/v1/lookups/en-numbers", params={"q": "lumen"}, headers=await sign_in("u-chan"))).json()
    assert [e["code"] for e in lumen["items"]] == ["EN-20415", "EN-20416", "EN-20417", "EN-20418"]
    assert (await client.get("/v1/card-types", headers=await sign_in("u-chan"))).status_code == 403
