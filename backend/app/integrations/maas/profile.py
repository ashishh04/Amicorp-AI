"""Gate 2 on ModelArts Studio MaaS: does the payment fit the client's KYC profile?

The model reads the payment and the profile and says match, mismatch or uncertain. Any failure (timeout,
refusal, an answer that does not parse or fails the guards) becomes "uncertain", which the ruleset maps to
mismatch: LLM uncertainty must never let a payment through (n8n README, gate 2).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.errors import LlmError
from app.ai.guards import input_guard
from app.ai.llm_client import LlmClient
from app.ai.prompts.registry import PROMPTS
from app.modules.transaction_monitoring.ports import ClientProfile, Payment, ProfileJudgement

PROMPT = PROMPTS["aml.gate2-profile@1"]
MAX_TOKENS = 1_500  # room for the reasoning when MAAS_THINKING=enabled


class ProfileVerdict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    verdict: Literal["match", "mismatch", "uncertain"]
    reason: str = Field(min_length=1, max_length=600)


class MaasProfileInterpreter:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    async def judge(self, payment: Payment, profile: ClientProfile) -> ProfileJudgement:
        case = {
            "payment": {
                "amountUsd": str(payment.amount_usd), "currency": payment.currency,
                "counterparty": payment.counterparty_name,
                "beneficiaryCountry": payment.beneficiary_ctry, "purpose": payment.purpose,
            },
            "profile": {
                "client": profile.name, "expectedCountries": list(profile.countries),
                "maxSinglePaymentUsd": str(profile.max_amount_usd), "expectedPurposes": list(profile.purposes),
            },
        }
        try:
            completion = await self._client.complete_structured(
                PROMPT, {"case": input_guard.as_data(case)}, ProfileVerdict, max_tokens=MAX_TOKENS,
            )
        except LlmError as exc:
            return ProfileJudgement(
                "uncertain", f"The model could not judge the payment ({exc.reason}), so it counts as a mismatch.",
                {"promptKey": PROMPT.key, "promptSha": PROMPT.sha, "error": exc.reason},
            )
        return ProfileJudgement(completion.value.verdict, completion.value.reason, completion.trace())
