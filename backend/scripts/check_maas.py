"""Check the ModelArts Studio MaaS settings in backend/.env with three real calls (synthetic data only).

    python -m scripts.check_maas

1. A connectivity prompt: is the key active, the model subscribed, the URL right?
2. A recommendation for a synthetic UC4 finding, through the same code as the jobs worker.
3. The evidence review of a synthetic UC2 MLRO escalation, through the same code as the jobs worker.

Together they cost far less than a US cent. MAAS_INTEGRATION does not need to be set to run this.
"""
import asyncio
import io
import sys

from pydantic import BaseModel

from app.ai.errors import LlmError
from app.ai.llm_client import LlmClient
from app.ai.prompts.registry import PROMPTS
from app.core.config import get_settings
from app.integrations.maas.real import MaasRecommender
from app.integrations.maas.review import MaasEvidenceReviewer
from app.modules.cards.ports import EvidenceItem, Recommendation, RecommendationRequest, ReviewRequest

SAMPLE = RecommendationRequest(
    card_type="uc4.discrepancy", mode="assemble-and-recommend", subject_id="ENT-10017",
    evidence={
        "title": "Registered address differs between CARE and 5 Series", "ruleId": "D-01", "subjectId": "ENT-10017",
        "detail": {"field": "registeredAddress", "care": "12 Harbour Road, Wan Chai",
                   "fiveSeries": "12 Harbor Rd, Wanchai"},
    },
)
REVIEW_SAMPLE = ReviewRequest(
    card_type="aml.mlro-escalation", subject_id="TX-DEMO-SANCTION-0001", title="MLRO escalation: payment TX-DEMO",
    purpose="A screening match needs the MLRO's decision.",
    on_approval="Incident, STR pack, freeze or return of funds",
    evidence=(
        EvidenceItem("E1", "Payment", "5 Series payment TX-DEMO-SANCTION-0001",
                     "USD 12,000.00 from Lumen Capital SPC (CL-1001) to Kowloon Trading Ltd (CP-66120), beneficiary "
                     "country HK. Purpose: Trade settlement. Flagged unusual by 5 Series: no."),
        EvidenceItem("E2", "Client profile", "CARE profile CL-1001",
                     "Lumen Capital SPC: expected beneficiary countries SG, HK, GB; largest expected payment USD "
                     "60,000; expected purposes: Trade settlement; Supplier invoice. Risk rating 35 of 100. PEP: no."),
        EvidenceItem("E3", "Live screening", "Screening WC-LOCAL-0001",
                     "Kowloon Trading Ltd (HK) screened: possible match, score 92."),
    ),
    rule_results=("AML gate 3: risk and screening v1: alert. Rule G3-01 (Screening hit with score 85 or more: the "
                  "MLRO decides). Inputs: screeningHit = True, screeningScore = 92, riskScore = 35, pepFlag = False",),
)


def show(n: int, what: str, result: Recommendation) -> None:
    llm = result.llm or {}
    print(f"OK    {n}/3 {what}: {llm.get('latencyMs')} ms, "
          f"{llm.get('inputTokens')} + {llm.get('outputTokens')} tokens, USD {llm.get('costUsd')}")
    print(f"      decision {result.decision}, confidence {result.confidence:.2f}, cites {', '.join(result.citations)}")
    print(f"      summary: {result.summary}")
    print(f"      action:  {result.proposed_action}")


class Pong(BaseModel):
    ok: bool


def hint(exc: LlmError) -> str:
    if exc.status in (401, 403):
        return "The API key is wrong, or not active yet: a new key works a few minutes after it is created."
    if exc.status == 404:
        return ("Compare MAAS_BASE_URL and MAAS_MODEL with 'API Calling' on the Real-Time Inference page, and check "
                "that the model is subscribed.")
    if exc.status == 400:
        return "MaaS refused a parameter. If the message mentions thinking, set MAAS_THINKING=default and run again."
    if exc.status == 429:
        return "Rate limited, or the subscription's quota is used up. Wait a minute, then check the subscription."
    if exc.reason == "timeout":
        return "No answer in time. Run again, or raise MAAS_TIMEOUT_SECONDS."
    if exc.reason == "unavailable":
        return "MaaS could not be reached. Check the network or proxy between this machine and CN-Hong Kong."
    if exc.reason in ("parse", "guard"):
        return "The model answered, but not in the expected form. Run again; if it repeats, keep the line above."
    return ""


async def main() -> int:
    settings = get_settings()
    try:
        client = LlmClient.from_settings(settings)
    except RuntimeError as exc:
        print(f"FAIL  {exc}")
        return 1
    print(f"MaaS  {client.url}\n      model {client.model}, thinking {settings.maas_thinking}")
    try:
        pong = await client.complete_structured(PROMPTS["platform.connectivity-check@1"], {}, Pong, max_tokens=300)
        print(f"OK    1/3 connectivity: {pong.latency_ms} ms, model {pong.model_id}, "
              f"{pong.input_tokens} + {pong.output_tokens} tokens")
        show(2, "card recommendation", await MaasRecommender(client).recommend(SAMPLE))
        show(3, "evidence review", await MaasEvidenceReviewer(client).review(REVIEW_SAMPLE))
    except LlmError as exc:
        print(f"FAIL  {exc}")
        if advice := hint(exc):
            print(f"      {advice}")
        return 1
    if settings.maas_mode != "real":
        print("\nThe app still uses the stand-in. To use this model for every card's AI step, set "
              "MAAS_INTEGRATION=real in backend/.env and restart the API.")
    return 0


if __name__ == "__main__":
    if isinstance(sys.stdout, io.TextIOWrapper):  # a redirected Windows console is cp1252
        sys.stdout.reconfigure(errors="replace")
    sys.exit(asyncio.run(main()))
