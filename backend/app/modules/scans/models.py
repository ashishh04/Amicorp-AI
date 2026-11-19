"""SQLAlchemy models for scans."""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Scan(Base):
    __tablename__ = "scan"
    __table_args__ = {"schema": "rules"}

    scan_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ruleset_key: Mapped[str] = mapped_column(Text)
    layer: Mapped[str] = mapped_column(Text)
    batch_date: Mapped[date | None]
    scan_window: Mapped[str | None] = mapped_column(Text)
    max_new_findings: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)  # queued | running | completed | failed (n8n contract)
    findings_total: Mapped[int | None] = mapped_column(Integer)
    findings_new: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class Finding(Base):
    __tablename__ = "finding"
    __table_args__ = {"schema": "rules"}

    finding_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.scan.scan_id"))
    rule_id: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(Text)
    policy_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_new: Mapped[bool]  # no card had this dedupe key when the scan ran
    new_rank: Mapped[int | None] = mapped_column(Integer)
