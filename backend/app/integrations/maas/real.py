"""Card recommendations from the model on ModelArts Studio MaaS (UC4 discrepancies, UC5 violations).

The model sees the card's finding as evidence item E1, the first item the portal lists for these cards, and
answers with a summary, a proposed action, a suggested decision and the evidence it relied on. It suggests;
the officer decides. A failed call or a failed guard raises LlmError, so the jobs worker retries, and after the
last attempt the card reaches a person without a summary (cards.recommend_failed).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.ai.errors import LlmError
from app.ai.guards import input_guard, output_guard
from app.ai.llm_client import LlmClient
from app.ai.prompts.registry import PROMPTS
from app.modules.cards.ports import Recommendation, RecommendationRequest

PROMPT_FOR_MODE = {
    "assemble-and-recommend": "cards.assemble-and-recommend@1",
    "propose-correction": "cards.propose-correction@1",
}
# What the model may see of a finding. The scan ID and anything added later stay out.
FINDING_FIELDS = ("title", "ruleId", "policyId", "subjectId", "detail")
# The cap includes the model's reasoning when MAAS_THINKING=enabled: about 250 tokens for a simple finding on the
# 29 Oct 2026 check, so this leaves room for messier ones. A cut-off answer fails closed.
MAX_TOKENS = 2_000


class CardAdvice(BaseModel):
    """The answer the card prompts ask for."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=1_000)
    proposed_action: str = Field(min_length=1, max_length=500)
    decision: Literal["APPROVE", "REJECT"]
    confidence: float = Field(ge=0, le=1)
    citations: list[str] = Field(max_length=10)


class MaasRecommender:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    async def recommend(self, request: RecommendationRequest) -> Recommendation:
        if not request.evidence:
            raise LlmError("input", "the card has no finding to summarise")
        finding = {k: request.evidence[k] for k in FINDING_FIELDS if k in request.evidence}
        card = {"cardType": request.card_type, "subjectId": request.subject_id, "evidence": [{"id": "E1", **finding}]}
        completion = await self._client.complete_structured(
            PROMPTS[PROMPT_FOR_MODE[request.mode]],
            {"card": input_guard.as_data(card), "officer_note": input_guard.note(request.instruction)},
            CardAdvice,
            max_tokens=MAX_TOKENS,
        )
        advice = completion.value
        return Recommendation(
            summary=advice.summary, proposed_action=advice.proposed_action, model_id=completion.model_id,
            decision=advice.decision, confidence=advice.confidence,
            citations=tuple(output_guard.check_citations(advice.citations, given={"E1"})), llm=completion.trace(),
        )
