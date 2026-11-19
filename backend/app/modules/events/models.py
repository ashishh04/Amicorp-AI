"""SQLAlchemy model for the live-event outbox."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Identity, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventRow(Base):
    """One event the portal may receive. The card's type, team and owner travel with it, so the stream can apply
    the same visibility rule as GET /v1/cards before it sends anything."""

    __tablename__ = "event_log"
    __table_args__ = {"schema": "ops"}

    event_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    type: Mapped[str] = mapped_column(Text)  # card.created | card.updated | card.assigned | statement.updated
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    card_type: Mapped[str | None] = mapped_column(Text)
    team: Mapped[str | None] = mapped_column(Text)
    owner_oid: Mapped[uuid.UUID | None]
    at: Mapped[datetime]
