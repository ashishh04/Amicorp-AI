"""Ruleset administration (portal contract, Rulesets): Admins draft, a Checker of the team or the MLRO approves,
never the drafter, and only when every regression case passes."""
import pytest

from tests.conftest import AUTH

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

GATE1 = "aml.gate1-entry"


def by_key(page: dict, key: str) -> dict:
    return next(r for r in page["items"] if r["key"] == key)


async def test_each_role_sees_what_it_may_do(client, sign_in):
    grace, priya, daniel = await sign_in("u-grace"), await sign_in("u-priya"), await sign_in("u-daniel")
    as_grace = (await client.get("/v1/rulesets", headers=grace)).json()
    assert {r["key"] for r in as_grace["items"]} == {
        "uc1.field-validation", "aml.gate1-entry", "aml.gate2-profile", "aml.gate3-risk", "nav.checks"}
    gate1 = by_key(as_grace, GATE1)
    assert gate1["actions"]["draft"] == {"allowed": True, "reason": None}
    statuses = [(v["version"], v["status"]) for v in gate1["versions"]]
    assert statuses == [(4, "draft"), (3, "approved"), (2, "superseded")]
    assert gate1["versions"][0]["actions"]["approve"]["reason"] == (
        "Admins draft versions; a Checker or the MLRO approves them.")
    assert gate1["approvers"] == "the MLRO"

    as_priya = (await client.get("/v1/rulesets", headers=priya)).json()
    assert by_key(as_priya, GATE1)["versions"][0]["actions"]["approve"]["reason"] == (
        "Only the MLRO approves aml.* rulesets.")
    assert by_key(as_priya, "uc1.field-validation")["versions"][0]["actions"]["approve"]["allowed"] is True
    assert by_key(as_priya, GATE1)["actions"]["draft"]["reason"] == "Admins draft versions under change control."
    as_daniel = (await client.get("/v1/rulesets", headers=daniel)).json()
    assert by_key(as_daniel, GATE1)["versions"][0]["actions"]["approve"]["allowed"] is True
    assert (await client.get("/v1/rulesets", headers=await sign_in("u-chan"))).status_code == 403


async def test_the_mlro_approves_a_draft_and_n8n_gets_the_new_version(client, sign_in):
    daniel = await sign_in("u-daniel")
    approved = await client.post(f"/v1/rulesets/{GATE1}/versions/4/approve", headers=daniel)
    assert approved.status_code == 200, approved.text
    versions = {v["version"]: v for v in approved.json()["versions"]}
    assert (versions[4]["status"], versions[3]["status"]) == ("approved", "superseded")
    assert versions[4]["approvedBy"]["name"] == "Daniel Wong" and versions[4]["effectiveFrom"] is not None

    again = await client.post(f"/v1/rulesets/{GATE1}/versions/4/approve", headers=daniel)
    assert again.status_code == 409 and again.json()["detail"] == "Only a draft version can be approved."

    await client.post("/v1/transactions", headers={**AUTH, "Idempotency-Key": "TX-V4"}, json={
        "transactionId": "TX-V4", "source": "realtime", "receivedAt": "2026-10-30T02:00:00Z"})
    await client.post("/v1/transactions/enrich", headers={**AUTH, "Idempotency-Key": "e:TX-V4"},
                      json={"transactionId": "TX-V4"})
    run = await client.post("/v1/gates/evaluate", headers={**AUTH, "Idempotency-Key": "g:TX-V4"}, json={
        "ruleset": GATE1, "subjectType": "transaction", "subjectId": "TX-V4"})
    assert run.json()["rulesetVersion"] == 4


async def test_drafting_is_checked_and_four_eyes_holds(client, sign_in):
    grace, priya = await sign_in("u-grace"), await sign_in("u-priya")
    key = "uc1.field-validation"
    exists = await client.post(f"/v1/rulesets/{key}/versions", headers=grace,
                               json={"basedOn": 2, "note": "Another one", "rules": []})
    assert exists.status_code in (409, 422)

    bad = (await client.post(f"/v1/rulesets/{key}/validate", headers=grace, json={"rules": [
        {"id": "F-01", "desc": "x", "when": {"<": [{"var": "pages"}, 1]}, "then": "maybe"}]})).json()
    assert bad["valid"] is False
    assert bad["errors"][0] == 'Rule 1: the outcome "maybe" is not one of pass, needs-review, reject.'

    rules = (await client.get("/v1/rulesets", headers=grace)).json()
    draft_rules = by_key(rules, key)["versions"][0]["rules"]
    check = (await client.post(f"/v1/rulesets/{key}/validate", headers=grace, json={"rules": draft_rules})).json()
    assert check["valid"] is True and all(r["pass"] for r in check["regression"])

    edited = await client.put(f"/v1/rulesets/{key}/versions/3", headers=grace,
                              json={"basedOn": 2, "note": "Red band 0.75 (CR-121), wording", "rules": draft_rules})
    assert edited.status_code == 200 and edited.json()["versions"][0]["note"] == "Red band 0.75 (CR-121), wording"
    no_note = await client.put(f"/v1/rulesets/{key}/versions/3", headers=grace,
                               json={"basedOn": 2, "note": "", "rules": draft_rules})
    assert no_note.status_code == 422 and no_note.json()["title"] == "Note required"

    # Grace drafted v3, so she could not approve it even with a Checker role; Priya (Operations Checker) can.
    approved = await client.post(f"/v1/rulesets/{key}/versions/3/approve", headers=priya)
    assert approved.status_code == 200
    gone = await client.delete(f"/v1/rulesets/{key}/versions/3", headers=grace)
    assert gone.status_code == 409 and gone.json()["detail"] == "Version 3 is not a draft."


async def test_a_draft_can_be_discarded_and_test_runs_change_nothing(client, sign_in):
    grace = await sign_in("u-grace")
    discarded = await client.delete(f"/v1/rulesets/{GATE1}/versions/4", headers=grace)
    assert [v["version"] for v in discarded.json()["versions"]] == [3, 2]
    tested = (await client.post(f"/v1/rulesets/{GATE1}/test", headers=grace, json={"version": 3, "inputs": {
        "unusualFlag": False, "counterpartyId": "CP-1", "amountUsd": 900, "amountUsdSum7d": 900,
        "beneficiaryCtry": "KP", "nearThresholdCount7d": 0}})).json()
    assert (tested["outcome"], tested["matchedRule"]["id"]) == ("monitor", "G1-05")
    assert [t["matched"] for t in tested["trace"]] == [False, False, False, False, True]
    missing = await client.post(f"/v1/rulesets/{GATE1}/test", headers=grace, json={"version": 3, "inputs": {}})
    assert missing.status_code == 422 and missing.json()["title"] == "Evaluation failed"
