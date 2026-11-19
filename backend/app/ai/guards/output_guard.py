"""Validate LLM output; uncertain results map to the fail-closed outcome.

The task's Pydantic model checks the answer's shape and lengths while it is parsed. Here: no links, no markup,
and every citation names evidence the model was actually given. A failed check raises LlmError, and the
caller decides what failing closed means for its task.
"""
import re
from collections.abc import Collection, Iterable, Iterator
from typing import Any

from pydantic import BaseModel

from app.ai.errors import LlmError

_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)
_MARKUP = re.compile(r"</?[a-z][^>]*>|```", re.IGNORECASE)


def check_strings(answer: BaseModel) -> None:
    """No string in the answer may hold a link (the model has no business pointing anywhere) or markup."""
    for path, text in _strings(answer.model_dump(), "answer"):
        if _LINK.search(text):
            raise LlmError("guard", f"{path} contains a link")
        if _MARKUP.search(text):
            raise LlmError("guard", f"{path} contains markup")


def check_citations(citations: Iterable[str], given: Collection[str]) -> list[str]:
    cited = list(dict.fromkeys(c.strip() for c in citations))
    if not cited:
        raise LlmError("guard", "the answer cites no evidence")
    unknown = sorted(set(cited) - set(given))
    if unknown:
        raise LlmError("guard", f"the answer cites evidence it was not given: {', '.join(unknown)}")
    return cited


def _strings(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _strings(item, f"{path}[{i}]")
