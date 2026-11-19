"""Base for every request and response model."""
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """camelCase on the wire, snake_case in Python. Unknown fields are rejected, not silently dropped."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _blank_strings_to_none(cls, data: Any) -> Any:
        # n8n expressions often produce "" for a missing value; treat it as absent.
        if isinstance(data, dict):
            return {k: (None if isinstance(v, str) and v.strip() == "" else v) for k, v in data.items()}
        return data


class ActionGate(ApiModel):
    """Whether the caller may take an action now, and if not, why (portal contract, Permission hints)."""

    allowed: bool
    reason: str | None = None
