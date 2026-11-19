"""SQLAlchemy models for rulesets and gate runs."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Integer, LargeBinary, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Ruleset(Base):
    __tablename__ = "ruleset"
    __table_args__ = {"schema": "rules"}

    ruleset_key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    owner_team: Mapped[str] = mapped_column(Text)
    use_case: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    outcomes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    default_outcome: Mapped[str] = mapped_column(Text)  # fail closed: applied when the rules cannot decide
    sample_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    regression_cases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime]


class RulesetVersion(Base):
    """Approved and superseded versions are immutable (a trigger refuses the change; cut a new version)."""

    __tablename__ = "ruleset_version"
    __table_args__ = {"schema": "rules"}

    ruleset_key: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(Text)  # draft | approved | superseded
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    body_sha256: Mapped[bytes] = mapped_column(LargeBinary)
    effective_from: Mapped[datetime | None]
    drafted_by: Mapped[uuid.UUID]
    drafted_at: Mapped[datetime]
    approved_by: Mapped[uuid.UUID | None]
    approved_at: Mapped[datetime | None]
    note: Mapped[str] = mapped_column(Text)


class GateRun(Base):
    """One evaluation: what the engine read, which rule matched and the outcome (LLD, rules.gate_run)."""

    __tablename__ = "gate_run"
    __table_args__ = (
        ForeignKeyConstraint(["ruleset_key", "version"],
                             ["rules.ruleset_version.ruleset_key", "rules.ruleset_version.version"]),
        {"schema": "rules"},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ruleset_key: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    subject_type: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[str] = mapped_column(Text)
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # [{name, value, source, readAt}]
    matched_rule: Mapped[str | None] = mapped_column(Text)
    matched_desc: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    llm: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    screening_ref: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer)
    evaluated_at: Mapped[datetime]
