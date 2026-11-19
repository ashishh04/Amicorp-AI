"""SQLAlchemy models for incidents."""
import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Incident(Base):
    __tablename__ = "incident"
    __table_args__ = {"schema": "ops"}

    incident_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    # source:workflowId:executionId. Reports of the same failed execution share it, even with new keys.
    incident_key: Mapped[str | None] = mapped_column(Text, unique=True)
    source: Mapped[str] = mapped_column(Text)
    workflow_id: Mapped[str] = mapped_column(Text)
    workflow_name: Mapped[str | None] = mapped_column(Text)
    execution_id: Mapped[str | None] = mapped_column(Text)
    execution_url: Mapped[str | None] = mapped_column(Text)
    failed_node: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # OPEN | ACKNOWLEDGED | RESOLVED
    opened_at: Mapped[datetime]
    updated_at: Mapped[datetime]
