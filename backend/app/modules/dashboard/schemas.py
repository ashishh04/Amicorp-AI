"""Pydantic models for GET /v1/dashboard/summary (frontend portal.models.ts KpiSummary)."""
from app.shared.schemas import ApiModel


class KpiValues(ApiModel):
    open_cards: float
    critical_past_due: float
    sla_breaches: float
    decisions: float
    writeback_success_pct: float
    uc2_hold_rate_pct: float
    gate_latency_p95_ms: float
    low_confidence_field_pct: float


class KpiSeries(ApiModel):
    open_cards: list[float]
    critical_past_due: list[float]
    sla_breaches: list[float]
    decisions: list[float]
    writeback_success_pct: list[float]
    uc2_hold_rate_pct: list[float]
    gate_latency_p95_ms: list[float]
    low_confidence_field_pct: list[float]


class DailyCount(ApiModel):
    date: str
    created: int
    decided: int
    breaches: int


class TypeStateCount(ApiModel):
    type: str
    state: str
    count: int


class GateOutcomeCount(ApiModel):
    ruleset_key: str
    outcome: str
    count: int


class FormatPct(ApiModel):
    format: str
    pct: float


class TeamCount(ApiModel):
    team: str
    count: int


class LlmTokens(ApiModel):
    used_in: int
    used_out: int
    budget_in: int
    budget_out: int


class KpiSummary(KpiValues):
    range_days: int
    daily: list[DailyCount]
    open_by_type_state: list[TypeStateCount]
    gate_outcomes: list[GateOutcomeCount]
    low_confidence_by_format: list[FormatPct]
    breaches_by_team: list[TeamCount]
    llm_tokens: LlmTokens
    series: KpiSeries
    previous: KpiValues
