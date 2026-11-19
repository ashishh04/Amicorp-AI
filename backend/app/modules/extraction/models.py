"""SQLAlchemy model for extraction jobs."""
import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExtractionJob(Base):
    __tablename__ = "extraction_job"
    __table_args__ = {"schema": "ops"}

    job_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID]
    profile: Mapped[str] = mapped_column(Text)  # bank-statement | nav-statement
    callback_url: Mapped[str] = mapped_column(Text)  # one of the allow-listed n8n webhooks (finding F2)
    status: Mapped[str] = mapped_column(Text)  # QUEUED, RUNNING, SUCCEEDED, FAILED
    error: Mapped[str | None] = mapped_column(Text)
    callback_acked: Mapped[bool]  # n8n accepted the callback
    created_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
