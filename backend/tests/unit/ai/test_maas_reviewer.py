import json
from typing import Any

import pytest

from app.ai.errors import LlmError
from app.integrations.maas.fake import FakeEvidenceReviewer
from app.integrations.maas.review import MaasEvidenceReviewer
from app.modules.cards.ports import EvidenceItem, ReviewRequest
from tests.unit.ai.fake_maas import FakeMaas, answer, client

pytestmark = pytest.mark.anyio

EVIDENCE = (
    EvidenceItem("E1", "Payment", "5 Series payment TX-1", "USD 12,000.00 to Kowloon Trading Ltd, HK. "
                 "Beneficiary account 4521 8890 1234 5678."),
    EvidenceItem("E2", "Live screening", "Screening WC-LOCAL-1", "Kowloon Trading Ltd (HK): possible match, score 92."),
)
ADVICE = {
    "summary": "Screening found a possible match, score 92, for the beneficiary.",
    "proposedAction": "Confirm the match, freeze the payment and prepare the STR pack.",
    "decision": "APPROVE", "confidence": 0.7, "citations": ["E2"],
}


def request(**overrides: Any) -> ReviewRequest:
    values: dict[str, Any] = {
        "card_type": "aml.mlro-escalation", "subject_id": "TX-1", "title": "MLRO escalation: payment TX-1",
        "purpose": "A screening match needs the MLRO's decision.",
        "on_approval": "Incident, STR pack, freeze or return of funds", "evidence": EVIDENCE,
        "rule_results": ("AML gate 3: risk and screening v1: alert. Rule G3-01 (Screening hit with score 85 or "
                         "more: the MLRO decides). Inputs: screeningHit = True, screeningScore = 92",),
    }
    return ReviewRequest(**(values | overrides))


async def test_a_review_carries_the_advice_and_its_trace():
    server = FakeMaas(answer(json.dumps(ADVICE)))
    result = await MaasEvidenceReviewer(client(server)).review(request())

    assert (result.decision, result.confidence, result.citations) == ("APPROVE", 0.7, ("E2",))
    assert result.llm is not None and result.llm["promptKey"] == "cards.review-evidence@1"
    user = server.user_message()
    assert user.startswith("Task: review this card's evidence")
    assert "Incident, STR pack" in user and "G3-01" in user  # what an Approve does, and why the card exists
    assert "4521 8890 1234 5678" not in user and "[number ...5678" in user  # account numbers are masked
    assert "tipping off" in server.body()["messages"][0]["content"]


async def test_the_officer_note_goes_with_a_return_to_ai():
    server = FakeMaas(answer(json.dumps(ADVICE)))
    await MaasEvidenceReviewer(client(server)).review(request(instruction="Check the registration number"))
    assert "<officer_note>\nCheck the registration number\n</officer_note>" in server.user_message()


async def test_without_evidence_the_model_is_not_called():
    server = FakeMaas()
    with pytest.raises(LlmError) as refused:
        await MaasEvidenceReviewer(client(server)).review(request(evidence=()))
    assert refused.value.reason == "input" and server.requests == []


@pytest.mark.parametrize("citations", [["E3"], []])
async def test_advice_must_cite_evidence_it_was_given(citations):
    server = FakeMaas(answer(json.dumps(ADVICE | {"citations": citations})))
    with pytest.raises(LlmError) as refused:
        await MaasEvidenceReviewer(client(server)).review(request())
    assert refused.value.reason == "guard"


async def test_the_local_stand_in_says_no_model_was_called():
    result = await FakeEvidenceReviewer().review(request(instruction="Recheck"))
    assert result.confidence == 0.0 and result.citations == ("E1", "E2")
    assert result.summary.startswith('Re-reviewed after the instruction "Recheck".')
    assert "no model was called" in result.summary
