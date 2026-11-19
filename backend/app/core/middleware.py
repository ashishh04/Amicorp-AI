"""Request context: correlation ID, body-size limit, security headers and one access-log line per request."""
import json
import re
import time
import uuid
from typing import Any

import structlog
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger()

# n8n sends its execution ID; anything else is replaced so it cannot inject text into logs.
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9:._-]{1,64}$")

_SECURITY_HEADERS = [
    (b"cache-control", b"no-store"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
]


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        incoming = headers.get("x-correlation-id", "")
        correlation_id = incoming if _CORRELATION_ID.fullmatch(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_body_bytes:
            await _reject_too_large(scope, send, correlation_id)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    # An HTTPException, because FastAPI turns any other error raised while it reads
                    # the body into a generic 400.
                    raise HTTPException(413, f"The body exceeds {self.max_body_bytes} bytes")
            return message

        status = 500
        started = time.perf_counter()

        async def send_with_headers(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                extra = [*_SECURITY_HEADERS, (b"x-correlation-id", correlation_id.encode())]
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        try:
            await self.app(scope, limited_receive, send_with_headers)
        finally:
            log.info(
                "http.request",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )


async def _reject_too_large(scope: Scope, send: Send, correlation_id: str) -> None:
    body: dict[str, Any] = {
        "type": "https://api.amc.internal/problems/payload-too-large",
        "title": "Request body too large",
        "status": 413,
        "code": "PAYLOAD_TOO_LARGE",
        "detail": "The request body is larger than this API accepts",
        "instance": scope["path"],
        "traceId": correlation_id,
        "retryable": False,
    }
    payload = json.dumps(body).encode()
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/problem+json"),
            (b"content-length", str(len(payload)).encode()),
            (b"x-correlation-id", correlation_id.encode()),
            *_SECURITY_HEADERS,
        ],
    })
    await send({"type": "http.response.body", "body": payload})
