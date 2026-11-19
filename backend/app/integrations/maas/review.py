"""The evidence review on ModelArts Studio MaaS: UC1, UC2 and UC3 cards.

The model reads the card's evidence items (E1, E2 ... as the portal lists them) next to the results of the rules
that raised the card, and answers with a summary, a next step, a suggested decision and the evidence it relied
on. It suggests; the officer decides. A failed call or a failed guard raises LlmError, so the jobs worker retries;
after the last attempt the card reaches a person without a summary, its evidence still listed.
"""
from app.ai.errors import LlmError
from app.ai.guards import input_guard, output_guard
from app.ai.llm_client import LlmClient
from app.ai.prompts.registry import PROMPTS
from app.integrations.maas.real import MAX_TOKENS, CardAdvice
from app.modules.cards.ports import Recommendation, ReviewRequest

PROMPT = PROMPTS["cards.review-evidence@1"]


class MaasEvidenceReviewer:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    async def review(self, request: ReviewRequest) -> Recommendation:
        if not request.evidence:
            raise LlmError("input", "the card has no evidence to review")
        card = {
            "cardType": request.card_type, "title": request.title, "subjectId": request.subject_id,
            "purpose": request.purpose, "onApproval": request.on_approval,
            "evidence": [{"id": e.id, "title": e.title, "source": e.source, "detail": e.detail}
                         for e in request.evidence],
            "ruleResults": list(request.rule_results),
        }
        completion = await self._client.complete_structured(
            PROMPT, {"card": input_guard.as_data(card), "officer_note": input_guard.note(request.instruction)},
            CardAdvice, max_tokens=MAX_TOKENS,
        )
        advice = completion.value
        return Recommendation(
            summary=advice.summary, proposed_action=advice.proposed_action, model_id=completion.model_id,
            decision=advice.decision, confidence=advice.confidence,
            citations=tuple(output_guard.check_citations(advice.citations, given={e.id for e in request.evidence})),
            llm=completion.trace(),
        )
