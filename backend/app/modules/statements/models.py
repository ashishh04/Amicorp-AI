"""SQLAlchemy models for statements and their lines."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

Money = Numeric(18, 2)


class Statement(Base):
    """A statement document: registered at intake, filled by extraction, reviewed by a Maker."""

    __tablename__ = "statement"
    __table_args__ = {"schema": "stmt"}

    statement_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(Text)  # bank | nav
    channel: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str] = mapped_column(Text, unique=True)  # the intake's business identity
    received_at: Mapped[datetime]
    state: Mapped[str] = mapped_column(Text)  # REGISTERED, EXTRACTING, IN_REVIEW, SUBMITTED, FAILED
    bank: Mapped[str | None] = mapped_column(Text)
    account_no: Mapped[str | None] = mapped_column(Text)
    account_name: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(Text)
    period_from: Mapped[date | None]
    period_to: Mapped[date | None]
    opening_balance: Mapped[Decimal | None] = mapped_column(Money)
    closing_balance: Mapped[Decimal | None] = mapped_column(Money)
    pages: Mapped[int | None] = mapped_column(Integer)
    extraction_job_id: Mapped[uuid.UUID | None]
    model_id: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None]
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    refs: Mapped[dict[str, Any]] = mapped_column(JSONB)  # bankId, accountNo, entity
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class NavDetail(Base):
    """What extraction reads from a NAV statement (UC3); the document and its state are in Statement."""

    __tablename__ = "nav_detail"
    __table_args__ = {"schema": "stmt"}

    statement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stmt.statement.statement_id"), primary_key=True)
    fund_code: Mapped[str] = mapped_column(Text)
    fund_name: Mapped[str] = mapped_column(Text)
    share_class: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text)
    valuation_date: Mapped[date]
    nav_per_share: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    previous_nav_per_share: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    shares_in_issue: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    register_shares: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    total_nav: Mapped[Decimal] = mapped_column(Money)


class StatementLine(Base):
    __tablename__ = "statement_line"
    __table_args__ = {"schema": "stmt"}

    line_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    statement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stmt.statement.statement_id"))
    line_no: Mapped[int] = mapped_column(Integer)
    value_date: Mapped[date]
    description: Mapped[str] = mapped_column(Text)
    debit: Mapped[Decimal | None] = mapped_column(Money)
    credit: Mapped[Decimal | None] = mapped_column(Money)
    balance: Mapped[Decimal | None] = mapped_column(Money)
    en_number: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[dict[str, float]] = mapped_column(JSONB)
    corrected: Mapped[list[str]] = mapped_column(ARRAY(Text))
    corrected_by: Mapped[uuid.UUID | None]
    approved: Mapped[bool]
    approved_by: Mapped[uuid.UUID | None]
    approved_at: Mapped[datetime | None]
    box: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer)  # the line's etag: W/"<version>"
