"""Pydantic models for lookups."""
from app.shared.schemas import ApiModel


class LookupEntry(ApiModel):
    code: str
    name: str


class LookupPage(ApiModel):
    items: list[LookupEntry]
