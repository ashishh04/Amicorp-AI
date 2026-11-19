"""Pydantic request/response models for scans (the UC4 and UC5 workflows' contract)."""
import uuid
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from app.shared.schemas import ApiModel

RulesetKey = Literal["uc4.discrepancy-catalogue", "uc5.violation-catalogue"]
ScanStatus = Literal["queued", "running", "completed", "failed"]


class ScanCreate(ApiModel):
    ruleset: RulesetKey
    layer: Literal["bronze", "silver", "gold"]
    batch_date: date | None = None  # UC4: the Bronze load date
    scan_window: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:._-]{1,64}$")  # UC5: refresh ID or HK hour
    max_new_findings: int = Field(ge=1, le=1000)

    @model_validator(mode="after")
    def _one_window(self) -> Self:
        if (self.batch_date is None) == (self.scan_window is None):
            raise ValueError("send exactly one of batchDate and scanWindow")
        return self


class ScanAccepted(ApiModel):
    scan_id: uuid.UUID
    status: ScanStatus


class ScanView(ApiModel):
    scan_id: uuid.UUID
    ruleset: str
    layer: str
    status: ScanStatus
    batch_date: date | None
    scan_window: str | None
    max_new_findings: int
    findings_total: int | None
    findings_new: int | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class FindingView(ApiModel):
    finding_id: uuid.UUID
    subject_id: str
    dedupe_key: str
    policy_id: str | None
    rule_id: str
    title: str
    detail: dict[str, Any]


class FindingsPage(ApiModel):
    scan_id: uuid.UUID
    findings: list[FindingView]
    truncated: bool  # more new findings exist than maxNewFindings allowed
