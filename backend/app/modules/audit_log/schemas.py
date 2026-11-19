"""Pydantic models for audit search (frontend portal.models.ts AuditEvent)."""
from datetime import datetime
from typing import Literal

from app.shared.schemas import ApiModel


class AuditEventView(ApiModel):
    id: str
    at: datetime
    actor: str
    actor_role: str
    action: str
    entity: str
    entity_id: str
    detail: str
    domain: Literal["AML", "General"]


class AuditPage(ApiModel):
    items: list[AuditEventView]
    next_cursor: str | None
