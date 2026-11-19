"""LLM token and cost tracking.

Each call's tokens and USD cost are logged as `llm.usage` (structlog JSON, then LTS and the SIEM) and returned
to the caller, which stores them with the result. The llm_cost_usd_total metric comes with /metrics.
"""
from dataclasses import dataclass
from decimal import Decimal

import structlog

log = structlog.get_logger()

_MILLION = Decimal(1_000_000)
_MICRO_USD = Decimal("0.000001")


@dataclass(frozen=True)
class Prices:
    """USD per million tokens."""

    input_per_m: Decimal
    output_per_m: Decimal


def record(model_id: str, prompt_key: str, input_tokens: int, output_tokens: int, prices: Prices) -> Decimal:
    cost = (prices.input_per_m * input_tokens + prices.output_per_m * output_tokens) / _MILLION
    cost = cost.quantize(_MICRO_USD)
    log.info("llm.usage", model_id=model_id, prompt=prompt_key, input_tokens=input_tokens,
             output_tokens=output_tokens, cost_usd=str(cost))
    return cost
