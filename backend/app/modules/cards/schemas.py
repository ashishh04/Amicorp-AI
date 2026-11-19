"""Pydantic request/response models for cards.

POST /v1/cards takes one body per card type, chosen by `type`. Each lists exactly the fields its workflow
sends, so a misspelt or unexpected field is rejected (422) instead of being stored silently.
"""
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.modules.cards.types import Severity
from app.modules.gates.schemas import GateRunView
from app.modules.identity.schemas import PersonRef
from app.shared.schemas import ActionGate, ApiModel

Text64 = Annotated[str, Field(min_length=1, max_length=64)]
Text200 = Annotated[str, Field(min_length=1, max_length=200)]
ErrorText = Annotated[str, Field(min_length=1, max_length=2000)]


class _NewCard(ApiModel):
    subject_id: str = Field(min_length=1, max_length=128)


class Uc1StatementValidation(_NewCard):
    type: Literal["uc1.statement-validation"]
    extraction_job_id: uuid.UUID
    gate_run_id: uuid.UUID
    gate_outcome: Text64


class Uc1ExtractionException(_NewCard):
    type: Literal["uc1.extraction-exception"]
    extraction_job_id: uuid.UUID
    status: Text64
    error: ErrorText


class NavApproval(_NewCard):
    type: Literal["nav.approval"]
    extraction_job_id: uuid.UUID
    gate_run_id: uuid.UUID


class NavException(_NewCard):
    type: Literal["nav.exception"]
    extraction_job_id: uuid.UUID
    gate_run_id: uuid.UUID
    gate_outcome: Text64


class NavExtractionException(_NewCard):
    type: Literal["nav.extraction-exception"]
    extraction_job_id: uuid.UUID
    status: Text64
    error: ErrorText


class AmlProfileUpdate(_NewCard):
    type: Literal["aml.profile-update"]
    gate_run_id: uuid.UUID
    blocks_transaction: bool = True
    revalidate_from: Text64


class AmlComplianceDecision(_NewCard):
    type: Literal["aml.compliance-decision"]
    screening_outcome: Text64
    gate_run_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)


class AmlMlroEscalation(_NewCard):
    type: Literal["aml.mlro-escalation"]
    severity: Severity | None = None
    blocks_transaction: bool = True
    screening_outcome: Text64
    gate_run_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)


class AmlGateException(_NewCard):
    type: Literal["aml.gate-exception"]
    severity: Severity | None = None
    blocks_transaction: bool = True
    failed_at: Text200
    outcome: Text64 | None = None
    error: ErrorText | None = None


class Uc4Discrepancy(_NewCard):
    type: Literal["uc4.discrepancy"]
    finding_id: uuid.UUID
    dedupe_key: Text200
    scan_id: uuid.UUID


class Uc5Violation(_NewCard):
    type: Literal["uc5.violation"]
    policy_id: Text64
    finding_id: uuid.UUID
    dedupe_key: Text200
    scan_id: uuid.UUID


# The router reads it with Body(discriminator="type"), so pydantic picks the model from `type` directly.
CardCreate = (
    Uc1StatementValidation | Uc1ExtractionException | NavApproval | NavException | NavExtractionException
    | AmlProfileUpdate | AmlComplianceDecision | AmlMlroEscalation | AmlGateException
    | Uc4Discrepancy | Uc5Violation
)


class CardCreated(ApiModel):
    card_id: uuid.UUID
    created: bool
    state: str


class RecommendRequest(ApiModel):
    mode: Literal["assemble-and-recommend", "propose-correction"]


class RecommendAccepted(ApiModel):
    card_id: uuid.UUID
    status: Literal["QUEUED"]


# ---------------------------------------------------------------- portal (frontend portal.models.ts)

class Money(ApiModel):
    amount: float
    currency: str


class CardSummary(ApiModel):
    id: str
    type: str
    title: str
    subject_id: str
    state: str
    severity: str
    team: str
    owner: PersonRef
    maker: PersonRef
    value: Money | None = None
    created_at: datetime
    due_at: datetime
    updated_at: datetime
    returns: int


class CardPage(ApiModel):
    items: list[CardSummary]
    next_cursor: str | None


class CardCounts(ApiModel):
    mine: int
    team: int
    due_soon: int = Field(alias="due-soon")
    overdue: int
    escalated: int
    closed: int


class Evidence(ApiModel):
    id: str
    kind: Literal["document", "record", "screening", "lake-row", "statement"]
    label: str
    source: str
    detail: str
    statement_id: str | None = None


class Recommendation(ApiModel):
    decision: Literal["APPROVE", "REJECT", "RETURN_TO_AI", "DELEGATE"]
    confidence: float
    summary: str
    model_id: str
    version: int
    generated_at: datetime
    citations: list[str]


class HistoryEntry(ApiModel):
    at: datetime
    actor: str
    action: str
    from_state: str | None = Field(default=None, alias="from")
    to_state: str | None = Field(default=None, alias="to")
    note: str | None = None


class MandatoryCheck(ApiModel):
    id: str
    desc: str
    met: bool


class StatementProgress(ApiModel):
    id: str
    approved: int
    total: int
    status: Literal["IN_REVIEW", "SUBMITTED"]


class CardDetail(CardSummary):
    description: str
    sla: str
    calendar: Literal["HK", "EU"]
    escalation_role: str
    on_approval: str
    hold: str | None = None
    recommendation: Recommendation | None
    evidence: list[Evidence]
    gate_runs: list[GateRunView]
    mandatory_checks: list[MandatoryCheck]
    history: list[HistoryEntry]
    delegation_chain: list[PersonRef]
    actions: dict[str, ActionGate]
    statement: StatementProgress | None = None


class DecisionRequest(ApiModel):
    decision: Literal["APPROVE", "REJECT", "RETURN_TO_AI", "DELEGATE"]
    # Mandatory, but checked by the decision rules, so a missing one gets the officer's message, not a 422 list.
    rationale: str | None = Field(default=None, max_length=4000)
    delegate_to: str | None = Field(default=None, max_length=64)


class PersonPage(ApiModel):
    items: list[PersonRef]


class CardTypeView(ApiModel):
    type: str
    version: int
    team: str
    severity: str
    sla: str
    escalation_role: str
    on_approval: str
    decided_by: str


class CardTypePage(ApiModel):
    items: list[CardTypeView]


class AssistantQuestion(ApiModel):
    question: str = Field(min_length=1, max_length=1000)
    scope: Literal["card", "entities"] = "card"


class AssistantCitation(ApiModel):
    id: str
    title: str
    doc_id: str
    page: int
    snippet: str


class AssistantAnswer(ApiModel):
    answer: str
    grounded: bool  # false on a refusal: no citation, no answer
    citations: list[AssistantCitation]
