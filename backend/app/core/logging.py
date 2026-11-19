"""Structured JSON logging with redaction (LLD, Log fields; blueprint section 9).

Logs never carry personal data, account numbers, document text or tokens. The redaction processor
is a safety net behind that rule, not a replacement for it.
"""
import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

_SENSITIVE_KEYS = frozenset({"authorization", "password", "secret", "token", "api_key", "cookie"})

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    # 12 to 19 digits standing alone (account and card numbers). Digit runs inside UUIDs are left alone.
    (re.compile(r"(?<![\w-])\d{12,19}(?![\w-])"), "[NUMBER]"),
]


def redact_text(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if str(k).lower() in _SENSITIVE_KEYS else _redact(v) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value


def redact_processor(_logger: Any, _method: str, event_dict: MutableMapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = _redact(dict(event_dict))
    return redacted


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    # JSON: tracebacks as structured data for LTS. Console: the renderer formats tracebacks itself.
    output: list[Any] = (
        [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()]
        if json_output
        else [structlog.dev.ConsoleRenderer()]
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,
            *output,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level.upper()]),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    # Libraries log through the standard library; keep them quiet unless something is wrong.
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="%(levelname)s %(name)s %(message)s")
