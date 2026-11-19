"""SQLAlchemy models for maintenance."""
from datetime import datetime

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Redrive(Base):
    """How often the sweeper re-drove a stuck item, and when it gave up and escalated it."""

    __tablename__ = "redrive"
    __table_args__ = {"schema": "ops"}

    scope: Mapped[str] = mapped_column(Text, primary_key=True)  # uc1.statement, uc2.transaction ...
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    last_redriven_at: Mapped[datetime]
    escalated_at: Mapped[datetime | None]
