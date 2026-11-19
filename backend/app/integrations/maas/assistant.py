"""The card assistant on ModelArts Studio MaaS: answers an officer's question from the card's evidence.

No citation, no answer: an answer that cites nothing becomes the refusal, and one that cites evidence it was
not given fails the output guard (LlmError), which the cards service also turns into the refusal.
"""
from pydantic import BaseModel, ConfigDict, Field

from app.ai.guards import input_guard, output_guard
from app.ai.llm_client import LlmClient
from app.ai.prompts.registry import PROMPTS
from app.modules.cards.ports import AssistantReply, AssistantRequest

PROMPT = PROMPTS["cards.assistant@1"]
MAX_TOKENS = 2_000


class AssistantAnswer(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    answer: str = Field(min_length=1, max_length=1_500)
    citations: list[str] = Field(default_factory=list, max_length=10)


class MaasAssistant:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    async def ask(self, request: AssistantRequest) -> AssistantReply:
        card = {
            "cardType": request.card_type, "title": request.title, "subjectId": request.subject_id,
            "evidence": [{"id": e.id, "title": e.title, "source": e.source, "detail": e.detail}
                         for e in request.evidence],
        }
        completion = await self._client.complete_structured(
            PROMPT, {"card": input_guard.as_data(card), "question": input_guard.note(request.question)},
            AssistantAnswer, max_tokens=MAX_TOKENS,
        )
        answer = completion.value
        if not answer.citations:
            return AssistantReply(answer.answer, (), completion.trace())
        cited = output_guard.check_citations(answer.citations, given={e.id for e in request.evidence})
        return AssistantReply(answer.answer, tuple(cited), completion.trace())
