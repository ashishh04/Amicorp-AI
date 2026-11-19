"""Keyset pagination for every list (portal contract: limit + opaque cursor; blueprint section 7).

The cursor carries the last row's sort key and ID, so a page is a range scan on an index, never an
OFFSET, and rows inserted meanwhile do not shift the pages. It is opaque to clients, not secret.
"""
import base64
import json
from typing import Any

from app.core.errors import BadRequest

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def clamp_limit(limit: int | None) -> int:
    return min(max(limit or DEFAULT_LIMIT, 1), MAX_LIMIT)


def encode_cursor(values: dict[str, Any]) -> str:
    raw = json.dumps(values, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, expected_keys: set[str]) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise BadRequest("The cursor is not valid; start again from the first page") from exc
    if not isinstance(values, dict) or set(values) != expected_keys:
        raise BadRequest("The cursor is not valid; start again from the first page")
    return values
