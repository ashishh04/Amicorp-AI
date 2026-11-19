"""SQLAlchemy models for reference lookups."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnNumber(Base):
    """Today's EN-number lookup table (entity booking references), refreshed daily from 5 Series."""

    __tablename__ = "en_number"
    __table_args__ = {"schema": "ref"}

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime]


class Bank(Base):
    __tablename__ = "bank"
    __table_args__ = {"schema": "ref"}

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    bic: Mapped[str] = mapped_column(Text)


class NamedList(Base):
    """A list the rules check with inList, for example the AML exclusion list of internal counterparties."""

    __tablename__ = "named_list"
    __table_args__ = {"schema": "ref"}

    list_name: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)


class CountryRisk(Base):
    """Compliance's country-risk table (countryRisk); a country not listed is low risk."""

    __tablename__ = "country_risk"
    __table_args__ = {"schema": "ref"}

    country: Mapped[str] = mapped_column(Text, primary_key=True)  # ISO 3166 alpha-2
    risk: Mapped[str] = mapped_column(Text)  # high | medium | low


class FundTemplate(Base):
    """Fund accounting's template per fund and share class: the NAV move it tolerates (nav.checks)."""

    __tablename__ = "fund_template"
    __table_args__ = {"schema": "ref"}

    fund_code: Mapped[str] = mapped_column(Text, primary_key=True)
    share_class: Mapped[str] = mapped_column(Text, primary_key=True)
    fund_name: Mapped[str] = mapped_column(Text)
    tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3))
