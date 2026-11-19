"""Pydantic models for the UC1 validation workspace (frontend portal.models.ts) and statement intake."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field

from app.modules.identity.schemas import PersonRef
from app.shared.schemas import ActionGate, ApiModel

LineField = Literal["valueDate", "description", "debit", "credit", "balance", "enNumber"]


class CheckFailure(ApiModel):
    message: str
    line_no: int | None = None
    field: LineField | None = None


class StatementCheck(ApiModel):
    id: str
    desc: str
    status: Literal["pass", "fail"]
    failures: list[CheckFailure]


class StatementReference(ApiModel):
    key: Literal["bankId", "accountNo", "entity"]
    label: str
    value: str | None
    valid: bool
    message: str | None = None


class ExtractionInfo(ApiModel):
    model_id: str
    job_id: str
    completed_at: datetime
    threshold: float


class StatementHeader(ApiModel):
    id: str
    card_id: str | None  # null until n8n has created the validation card
    bank: str
    account_no: str
    account_name: str
    currency: str
    period_from: str
    period_to: str
    opening_balance: float
    closing_balance: float
    pages: int
    status: Literal["IN_REVIEW", "SUBMITTED"]
    extraction: ExtractionInfo
    references: list[StatementReference]
    checks: list[StatementCheck]
    editable: ActionGate


class LineBox(ApiModel):
    page: int
    top: float
    height: float


class StatementLineView(ApiModel):
    line_id: str
    line_no: int
    value_date: str
    description: str
    debit: float | None
    credit: float | None
    balance: float | None
    en_number: str | None
    confidence: dict[LineField, float]
    corrected: list[LineField]
    corrected_by: PersonRef | None = None
    approved: bool
    approve: ActionGate
    box: LineBox
    etag: str


class StatementLinePage(ApiModel):
    items: list[StatementLineView]


class LinePatch(ApiModel):
    """A Maker's correction: only the fields sent change. Values are checked by the service, so a wrong one
    gets the officer's message ("Line 6: debit cannot be negative"), not a generic validation list."""

    value_date: str | None = Field(default=None, max_length=10)
    description: str | None = Field(default=None, max_length=500)
    debit: float | None = None
    credit: float | None = None
    balance: float | None = None
    en_number: str | None = Field(default=None, max_length=32)


class ReferencesPatch(ApiModel):
    bank_id: str | None = Field(default=None, max_length=64)
    account_no: str | None = Field(default=None, max_length=64)
    entity: str | None = Field(default=None, max_length=32)


# ---------------------------------------------------------------- intake (n8n)

class StatementIntake(ApiModel):
    channel: str = Field(min_length=1, max_length=32)
    object_key: str = Field(min_length=1, max_length=1024)
    received_at: AwareDatetime


class StatementRegistered(ApiModel):
    statement_id: uuid.UUID
    created: bool
