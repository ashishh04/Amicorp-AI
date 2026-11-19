"""SQLAlchemy models for notifications."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = {"schema": "ops"}

    notification_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    audience: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    event: Mapped[str] = mapped_column(Text)
    card_id: Mapped[uuid.UUID | None]
    incident_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)  # QUEUED | SENT | FAILED
    attempts: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime]
    sent_at: Mapped[datetime | None]
