"""Sanitize/validate content before it reaches the LLM.

Evidence goes to the model as JSON inside fixed tags, with < and > escaped so that no value can close a tag
early. Control characters are dropped. Long digit runs (account, passport and phone numbers) are masked with a
stable reference: no card task needs the number itself, but the model can still tell whether two values are
the same number formatted differently. Oversized evidence is refused, not cut, so the model never judges half
of it.
"""
import hashlib
import json
import re
from typing import Any

from app.ai.errors import LlmError

MAX_DATA_CHARS = 12_000
MAX_NOTE_CHARS = 4_000  # the decision rationale's own limit

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Nine or more digits, optionally split by single spaces or hyphens. ISO dates (eight digits) stay readable, and
# so do amounts: a run followed by a decimal part is not masked. A full stop that ends a sentence is no decimal.
_LONG_NUMBER = re.compile(r"(?<![\w.])\d(?:[ -]?\d){8,}(?!\w|\.\d)")


def mask_numbers(text: str) -> str:
    def mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        return f"[number ...{digits[-4:]} #{hashlib.sha256(digits.encode()).hexdigest()[:6]}]"

    return _LONG_NUMBER.sub(mask, text)


def clean(value: Any) -> Any:
    """Every string in a JSON-like value, keys included, without control characters or long numbers."""
    if isinstance(value, str):
        return mask_numbers(_CONTROL.sub(" ", value))
    if isinstance(value, dict):
        return {clean(str(k)): clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean(v) for v in value]
    return value


def as_data(value: Any) -> str:
    """JSON for a tagged data block of a prompt."""
    text = json.dumps(clean(value), ensure_ascii=False, sort_keys=True, default=str)
    if len(text) > MAX_DATA_CHARS:
        raise LlmError("input", f"the evidence is {len(text)} characters; the limit is {MAX_DATA_CHARS}")
    return text.replace("<", "\\u003c").replace(">", "\\u003e")


def note(text: str | None) -> str:
    """An officer's free text (the Return-to-AI rationale) for a tagged block."""
    if not text or not text.strip():
        return "(none)"
    cleaned: str = clean(text.strip())[:MAX_NOTE_CHARS]
    return cleaned.replace("<", "&lt;").replace(">", "&gt;")
