"""Deterministic stand-ins for the model, for local work. They say plainly that no model wrote them, and the
recommendation's confidence is 0: nothing was judged."""
from app.modules.cards.ports import (
    AssistantReply,
    AssistantRequest,
    Recommendation,
    RecommendationRequest,
    ReviewRequest,
)
from app.modules.transaction_monitoring.ports import ClientProfile, Payment, ProfileJudgement

MODEL_ID = "fake-local"
REFUSAL = "I could not find this in the documents you can access."


class FakeProfileInterpreter:
    """Gate 2 by plain comparison: country and amount against the profile; an unclear purpose is uncertain."""

    async def judge(self, payment: Payment, profile: ClientProfile) -> ProfileJudgement:
        trace = {"modelId": MODEL_ID, "promptKey": "aml.gate2-profile@1"}
        if "unclear" in payment.purpose.lower():
            return ProfileJudgement("uncertain", "The purpose does not say what the payment is for.", trace)
        if payment.beneficiary_ctry not in profile.countries:
            return ProfileJudgement("mismatch", f"The profile does not expect payments to {payment.beneficiary_ctry}.",
                                    trace)
        if payment.amount_usd > profile.max_amount_usd:
            return ProfileJudgement("mismatch", "The amount is above the largest payment the profile expects.", trace)
        return ProfileJudgement("match", "Country and amount fit the client's profile (local placeholder).", trace)


class FakeAssistant:
    """Answers from the evidence titles, citing them, as the portal mock does. No model is called."""

    async def ask(self, request: AssistantRequest) -> AssistantReply:
        question = request.question.lower()
        if not request.evidence or len(question.strip()) < 4:
            return AssistantReply(REFUSAL, ())
        cited = request.evidence[:3]
        listed = "; ".join(f"{e.title} [{e.id}]" for e in cited)
        answer = f"This card covers {request.subject_id}. The evidence on file: {listed}. (Local placeholder answer.)"
        if request.scope == "entities":
            answer += " Only this card's evidence was searched."
        return AssistantReply(answer, tuple(e.id for e in cited), {"modelId": MODEL_ID})


class FakeRecommender:
    async def recommend(self, request: RecommendationRequest) -> Recommendation:
        title = request.evidence.get("title", "the finding")
        if request.mode == "propose-correction":
            action = f"Correct the record for {request.subject_id} so that it no longer breaches the policy."
        else:
            action = f"Confirm which system holds the right value for {request.subject_id}, then correct the other."
        summary = f"{title} (local placeholder summary; no model was called)."
        if request.instruction:
            summary = f'Re-assembled after the instruction "{request.instruction}". {summary}'
        return Recommendation(
            summary=summary, proposed_action=action, model_id=MODEL_ID, decision="APPROVE", confidence=0.0,
            citations=("E1",) if request.evidence else (),  # the finding, as the real recommender cites it
        )


class FakeEvidenceReviewer:
    """Lists the evidence and counts the rule results instead of judging them."""

    async def review(self, request: ReviewRequest) -> Recommendation:
        cited = request.evidence[:3]
        summary = "Evidence on file: " + "; ".join(f"{e.title} [{e.id}]" for e in cited) + "."
        if request.rule_results:
            summary += f" {len(request.rule_results)} rule result(s) raised this card."
        summary += " (Local placeholder summary; no model was called.)"
        if request.instruction:
            summary = f'Re-reviewed after the instruction "{request.instruction}". {summary}'
        return Recommendation(
            summary=summary, model_id=MODEL_ID, decision="APPROVE", confidence=0.0,
            proposed_action=f"Check the evidence, then decide. Approving means: {request.on_approval}.",
            citations=tuple(e.id for e in cited),
        )
