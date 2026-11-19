import json
from typing import Any, get_args

import pytest

from app.ai.errors import LlmError
from app.ai.prompts.registry import PROMPTS
from app.core.config import Settings
from app.integrations import maas
from app.integrations.maas.fake import FakeRecommender
from app.integrations.maas.real import PROMPT_FOR_MODE, MaasRecommender
from app.modules.cards.ports import RecommendationRequest
from app.modules.cards.schemas import RecommendRequest
from tests.unit.ai.fake_maas import FakeMaas, answer, client

pytestmark = pytest.mark.anyio

FINDING = {
    "title": "Registered address differs between CARE and 5 Series", "ruleId": "D-01", "subjectId": "ENT-10017",
    "policyId": None, "scanId": "0b9d6f0e-1c1a-4e43-9d0e-3f1f8f1b2c11",
    "detail": {"field": "registeredAddress", "care": "12 Harbour Road, Wan Chai",
               "fiveSeries": "12 Harbor Rd, Wanchai"},
}
ADVICE = {
    "summary": "Both systems hold the same address, spelled differently.",
    "proposedAction": "Align the 5 Series address with the CARE spelling.",
    "decision": "APPROVE", "confidence": 0.82, "citations": ["E1"],
}


def request(mode: str = "assemble-and-recommend", **overrides: Any) -> RecommendationRequest:
    values: dict[str, Any] = {"card_type": "uc4.discrepancy", "mode": mode, "subject_id": "ENT-10017",
                              "evidence": FINDING}
    return RecommendationRequest(**(values | overrides))


async def test_a_recommendation_carries_the_advice_and_its_trace():
    server = FakeMaas(answer(json.dumps(ADVICE)))
    result = await MaasRecommender(client(server)).recommend(request())

    assert (result.decision, result.confidence, result.citations) == ("APPROVE", 0.82, ("E1",))
    assert result.proposed_action == ADVICE["proposedAction"]
    assert result.llm is not None and result.llm["promptKey"] == "cards.assemble-and-recommend@1"
    user = server.user_message()
    assert "Harbour Road" in user and "scanId" not in user
    assert "<officer_note>\n(none)\n</officer_note>" in user


async def test_the_mode_picks_the_prompt_and_the_officer_note_goes_with_it():
    server = FakeMaas(answer(json.dumps(ADVICE)))
    await MaasRecommender(client(server)).recommend(request("propose-correction", instruction="Check the 2026 return"))
    user = server.user_message()
    assert user.startswith("Task: a record breaches an Amicorp data policy.")
    assert "Check the 2026 return" in user


async def test_without_a_finding_the_model_is_not_called():
    server = FakeMaas()
    with pytest.raises(LlmError) as refused:
        await MaasRecommender(client(server)).recommend(request(evidence={}))
    assert refused.value.reason == "input"
    assert server.requests == []


async def test_advice_citing_evidence_it_was_not_given_is_refused():
    server = FakeMaas(answer(json.dumps(ADVICE | {"citations": ["E2"]})))
    with pytest.raises(LlmError) as refused:
        await MaasRecommender(client(server)).recommend(request())
    assert refused.value.reason == "guard"


def test_every_mode_has_a_registered_prompt():
    assert set(PROMPT_FOR_MODE) == set(get_args(RecommendRequest.model_fields["mode"].annotation))
    assert set(PROMPT_FOR_MODE.values()) <= set(PROMPTS)


def test_a_prompt_is_never_sent_half_filled():
    with pytest.raises(KeyError):
        PROMPTS["cards.propose-correction@1"].render({"card": "{}"})


def test_the_settings_choose_the_recommender(monkeypatch):
    monkeypatch.delenv("MAAS_API_KEY", raising=False)

    def make(**values: Any) -> Settings:
        return Settings(_env_file=None, database_url="postgresql+psycopg://u@127.0.0.1/db", environment="local",
                        integrations="fake", **values)

    assert isinstance(maas.recommender(make(maas_integration="fake")), FakeRecommender)
    with pytest.raises(RuntimeError, match="MAAS_API_KEY is not set"):
        maas.recommender(make(maas_integration="real"))
    assert isinstance(maas.recommender(make(maas_integration="real", maas_api_key="k")), MaasRecommender)
