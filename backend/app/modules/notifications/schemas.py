"""Pydantic request/response models for notifications."""
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator

from app.shared.schemas import ApiModel

# card-owner, or a role queue such as role:platform-support. Never a free-text address.
AUDIENCE_PATTERN = r"^(card-owner|role:[a-z0-9-]{1,48})$"


class NotificationCreate(ApiModel):
    """What the workflows send. Fields beyond the core four are the ones the workflows actually use."""

    audience: str = Field(pattern=AUDIENCE_PATTERN)
    fallback_audience: str | None = Field(default=None, pattern=AUDIENCE_PATTERN)
    channel: Literal["teams"]
    event: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,63}$")
    card_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    digest: bool = False
    sweep_id: str | None = Field(default=None, max_length=64)
    escalated_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _card_owner_needs_a_card(self) -> Self:
        if self.audience == "card-owner" and self.card_id is None:
            raise ValueError("audience 'card-owner' needs a cardId")
        return self


class NotificationQueued(ApiModel):
    notification_id: uuid.UUID
    status: Literal["QUEUED"]
