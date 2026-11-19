"""SQLAlchemy models for the user directory."""
import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppUser(Base):
    """A person known to the platform: name, teams and data scope. App roles are copied from Entra for
    routing (who can take a card); a request is always authorised by the roles in its own token."""

    __tablename__ = "app_user"
    __table_args__ = {"schema": "ref"}

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # the Entra object ID
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    calendar: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text))
    teams: Mapped[list[str]] = mapped_column(ARRAY(Text))
    data_scope: Mapped[list[str]] = mapped_column(ARRAY(Text))
    active: Mapped[bool]
    updated_at: Mapped[datetime]
