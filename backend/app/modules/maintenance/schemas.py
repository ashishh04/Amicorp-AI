"""Pydantic models for maintenance (the n8n Platform stuck-item sweeper)."""
import uuid
from typing import Literal

from pydantic import Field

from app.shared.schemas import ApiModel

Scope = Literal["uc1.statement", "uc2.transaction", "uc3.nav-statement", "extraction.job"]


class RedriveRequest(ApiModel):
    older_than_minutes: int = Field(default=30, ge=1, le=1440)
    max_attempts: int = Field(default=3, ge=1, le=10)
    scopes: list[Scope] = Field(min_length=1, max_length=4)


class RedriveItem(ApiModel):
    scope: Scope
    item_id: str
    action: Literal["redriven", "escalated"]


class RedriveResult(ApiModel):
    sweep_id: uuid.UUID
    redriven_count: int
    escalated_count: int
    items: list[RedriveItem]
