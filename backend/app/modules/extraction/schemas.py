"""Pydantic models for POST /v1/extraction/jobs (n8n UC1 and UC3)."""
import uuid
from typing import Literal

from pydantic import Field

from app.shared.schemas import ApiModel


class ExtractionJobRequest(ApiModel):
    document_id: uuid.UUID
    profile: Literal["bank-statement", "nav-statement"]
    callback_url: str = Field(min_length=1, max_length=512)


class ExtractionJobAccepted(ApiModel):
    job_id: uuid.UUID
    status: Literal["QUEUED"]
