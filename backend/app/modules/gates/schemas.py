"""Pydantic models for gates: what n8n sends to POST /v1/gates/evaluate, how the portal shows a run, and the
ruleset administration (frontend portal.models.ts: Ruleset, RulesetDraft, RulesetValidation)."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.modules.identity.schemas import PersonRef
from app.shared.schemas import ActionGate, ApiModel


class EvaluateRequest(ApiModel):
    ruleset: str = Field(min_length=1, max_length=64)
    subject_type: str = Field(min_length=1, max_length=32)
    subject_id: str = Field(min_length=1, max_length=128)
    screening: Literal["live"] | None = None  # UC2 gate 3 asks for a live screening


class EvaluateResult(ApiModel):
    run_id: uuid.UUID
    outcome: str
    ruleset_version: int
    matched_rule: str | None


class GateInput(ApiModel):
    name: str
    value: str | float | bool | None
    source: str
    read_at: datetime


class MatchedRule(ApiModel):
    id: str
    desc: str


class GateRunView(ApiModel):
    run_id: str
    ruleset_key: str
    ruleset_name: str
    ruleset_version: int
    outcome: str
    matched_rule: MatchedRule
    inputs: list[GateInput]
    evaluated_at: datetime
    duration_ms: int
    model_id: str | None = None


# ---------------------------------------------------------------- ruleset administration

class RuleView(ApiModel):
    id: str
    desc: str
    when: Any
    then: str


class VersionActions(ApiModel):
    approve: ActionGate


class RulesetVersionView(ApiModel):
    version: int
    status: Literal["draft", "approved", "superseded"]
    effective_from: datetime | None
    drafted_by: PersonRef
    drafted_at: datetime
    approved_by: PersonRef | None
    note: str
    rules: list[RuleView]
    actions: VersionActions


class RegressionCase(ApiModel):
    name: str
    inputs: dict[str, Any]
    expected: str


class RulesetActions(ApiModel):
    draft: ActionGate


class RulesetView(ApiModel):
    key: str
    name: str
    owner: str
    use_case: str
    description: str
    outcomes: list[str]
    versions: list[RulesetVersionView]
    regression_cases: list[RegressionCase]
    sample_inputs: dict[str, Any]
    approvers: str
    actions: RulesetActions


class RulesetPage(ApiModel):
    items: list[RulesetView]


class RulesetTestRequest(ApiModel):
    version: int = Field(ge=1)
    inputs: dict[str, Any] = Field(default_factory=dict)


class RuleTraceView(ApiModel):
    id: str
    desc: str
    matched: bool


class RulesetTestResult(ApiModel):
    outcome: str
    matched_rule: MatchedRule
    trace: list[RuleTraceView]
    version: int


class RulesetValidateRequest(ApiModel):
    rules: list[Any] = Field(max_length=200)


class RegressionResult(ApiModel):
    name: str
    expected: str
    actual: str
    matched_rule: str
    passed: bool = Field(alias="pass")


class RulesetValidation(ApiModel):
    valid: bool
    errors: list[str]
    regression: list[RegressionResult]


class RulesetDraft(ApiModel):
    based_on: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)  # required; checked with the officer's message
    rules: list[Any] = Field(max_length=200)
