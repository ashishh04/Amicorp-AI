"""SQLAlchemy models for cards."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Card(Base):
    __tablename__ = "card"
    __table_args__ = {"schema": "card"}

    card_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    type_version: Mapped[int] = mapped_column(Integer)
    use_case: Mapped[str] = mapped_column(Text)
    subject_type: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    owner_team: Mapped[str] = mapped_column(Text)
    owner_oid: Mapped[uuid.UUID | None]
    maker_oid: Mapped[uuid.UUID | None]
    due_at: Mapped[datetime]
    blocks_subject: Mapped[bool]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    gate_run_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid))
    delegation_chain: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid))  # previous owners, oldest first
    return_count: Mapped[int] = mapped_column(Integer)
    # The business identity n8n sends as Idempotency-Key: a dedupe key, document and job, or transaction.
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    version: Mapped[int] = mapped_column(Integer)  # bumps on every change; the portal's If-Match


class CardEvent(Base):
    __tablename__ = "card_event"
    __table_args__ = {"schema": "card"}

    event_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card.card.card_id"))
    from_state: Mapped[str | None] = mapped_column(Text)
    to_state: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)
    at: Mapped[datetime]


class CardEvidence(Base):
    __tablename__ = "card_evidence"
    __table_args__ = {"schema": "card"}

    evidence_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card.card.card_id"))
    kind: Mapped[str] = mapped_column(Text)  # finding | recommendation | document | gate-run
    ref: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime]
