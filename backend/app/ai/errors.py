"""The one error a model call raises, whatever went wrong. Callers fail closed on it."""
from typing import Literal

Reason = Literal["input", "timeout", "unavailable", "refused", "parse", "guard"]


class LlmError(Exception):
    """`status` is the HTTP status when MaaS answered with an error."""

    def __init__(self, reason: Reason, detail: str, status: int | None = None) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        self.status = status
