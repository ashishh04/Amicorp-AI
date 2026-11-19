"""Pydantic request/response models for incidents."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.shared.schemas import ApiModel


class IncidentCreate(ApiModel):
    """What the Platform error handler (AmiErrHandler001) sends when a workflow fails."""

    source: Literal["n8n"] = "n8n"
    workflow_id: str = Field(min_length=1, max_length=64)
    workflow_name: str | None = Field(default=None, max_length=200)
    execution_id: str | None = Field(default=None, max_length=64)
    execution_url: str | None = Field(default=None, max_length=500)
    failed_node: str | None = Field(default=None, max_length=200)
    message: str = Field(min_length=1, max_length=4000)


class IncidentCreated(ApiModel):
    incident_id: uuid.UUID
    created: bool


class IncidentView(ApiModel):
    incident_id: uuid.UUID
    source: str
    workflow_id: str
    workflow_name: str | None
    execution_id: str | None
    execution_url: str | None
    failed_node: str | None
    message: str
    status: str
    opened_at: datetime
