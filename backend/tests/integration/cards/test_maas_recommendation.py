"""A UC4 card recommended through the real MaaS adapter (talking to a fake MaaS server), read back as the portal
sees it."""
import json

import psycopg
import pytest

from app.db.session import UnitOfWork
from app.integrations.maas.real import MaasRecommender
from app.modules.cards import service as cards
from app.modules.scans import service as scans
from tests.conftest import AUTH
from tests.integration.scans.test_uc4_uc5_flows import create_card, submit_uc4
from tests.unit.ai.fake_maas import FakeMaas, answer
from tests.unit.ai.fake_maas import client as maas_client

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

ADVICE = {
    "summary": "CARE and 5 Series disagree about this record.", "proposedAction": "Correct 5 Series from CARE.",
    "decision": "APPROVE", "confidence": 0.74, "citations": ["E1"],
}


async def test_the_models_recommendation_reaches_the_card_with_its_trace(client, run_jobs, database, app, sign_in):
    scan_id = await submit_uc4(client)
    await run_jobs()
    finding = (await client.get(f"/v1/scans/{scan_id}/findings", headers=AUTH)).json()["findings"][0]
    card_id = (await create_card(client, finding, scan_id)).json()["cardId"]

    server = FakeMaas(answer(json.dumps(ADVICE)))
    async with UnitOfWork(app.state.session_factory, actor="svc:jobs-worker", correlation_id="test") as uow:
        await cards.recommend_job(uow, {"cardId": card_id, "mode": "assemble-and-recommend"},
                                  MaasRecommender(maas_client(server)), scans.finding_evidence)

    assert finding["subjectId"] in server.user_message()
    detail = (await client.get(f"/v1/cards/{card_id}", headers=await sign_in("u-ravi"))).json()
    assert detail["state"] == "AWAITING_DECISION"
    assert detail["recommendation"]["summary"] == ADVICE["summary"]
    assert detail["recommendation"]["modelId"] == "deepseek-v4-flash"
    assert detail["recommendation"]["citations"] == ["E1"]
    assert [e["id"] for e in detail["evidence"]] == ["E1"]  # the finding the model cited
    with psycopg.connect(database) as conn:
        llm = conn.execute("SELECT detail->'llm' FROM card.card_evidence WHERE kind = 'recommendation'").fetchone()[0]
        audit = conn.execute(
            "SELECT payload FROM audit.audit_event WHERE action = 'card.recommendation_ready'"
        ).fetchone()[0]
    assert llm["promptKey"] == audit["promptKey"] == "cards.assemble-and-recommend@1"
    assert llm["costUsd"] == "0.000270"
