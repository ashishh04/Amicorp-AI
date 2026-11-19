"""Domain errors and their RFC 9457 problem responses (LLD, Error model)."""
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_BASE = "https://api.amc.internal/problems/"
PROBLEM_MEDIA_TYPE = "application/problem+json"

log = structlog.get_logger()


class AppError(Exception):
    status = 500
    code = "INTERNAL_ERROR"
    title = "Internal error"
    retryable = False

    def __init__(
        self,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.headers = headers or {}
        self.extra = extra  # more problem members, e.g. the portal's failures[]


class BadRequest(AppError):
    status, code, title = 400, "BAD_REQUEST", "Bad request"


class Unauthorized(AppError):
    status, code, title = 401, "UNAUTHORIZED", "Authentication required"


class Forbidden(AppError):
    status, code, title = 403, "FORBIDDEN", "Not permitted"


class NotFound(AppError):
    status, code, title = 404, "NOT_FOUND", "Not found"


class Conflict(AppError):
    status, code, title = 409, "CONFLICT", "Conflict"


class PreconditionFailed(AppError):
    status, code, title = 412, "PRECONDITION_FAILED", "Changed since you loaded it"


class Unprocessable(AppError):
    status, code, title = 422, "UNPROCESSABLE", "Request refused"


class RuleRefused(AppError):
    """A business rule said no. The rule chooses the status (403 role or duty, 409 state, 422 check), and the
    title and detail are written for officers: the portal shows them verbatim."""

    def __init__(self, status: int, code: str, title: str, detail: str, *, extra: dict[str, Any] | None = None):
        super().__init__(detail, extra=extra)
        self.status, self.code, self.title = status, code, title


class IdempotencyKeyRequired(BadRequest):
    code, title = "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header required"


class IdempotencyKeyReused(Conflict):
    code, title = "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key already used for a different request"


class RequestInProgress(Conflict):
    code, title, retryable = "REQUEST_IN_PROGRESS", "A request with this Idempotency-Key is in progress", True

    def __init__(self) -> None:
        super().__init__(headers={"Retry-After": "2"})


class ServiceUnavailable(AppError):
    status, code, title, retryable = 503, "SERVICE_UNAVAILABLE", "Service unavailable", True


def problem(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    retryable: bool = False,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": PROBLEM_BASE + code.lower().replace("_", "-"),
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": request.url.path,
        "traceId": getattr(request.state, "correlation_id", None),
        "retryable": retryable,
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE)


_HTTP_CODES = {
    400: ("BAD_REQUEST", "Bad request"),
    401: ("UNAUTHORIZED", "Authentication required"),
    403: ("FORBIDDEN", "Not permitted"),
    404: ("NOT_FOUND", "Not found"),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed"),
    412: ("PRECONDITION_FAILED", "Changed since you loaded it"),
    413: ("PAYLOAD_TOO_LARGE", "Request body too large"),
}


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - registered for AppError only
    return problem(
        request, status=exc.status, code=exc.code, title=exc.title, detail=exc.detail,
        retryable=exc.retryable, headers=exc.headers, extra=exc.extra,
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Field locations and messages only. Submitted values are never echoed back: they may be sensitive.
    errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return problem(
        request, status=422, code="VALIDATION_FAILED", title="Request failed validation",
        detail="One or more fields are missing or invalid", extra={"errors": errors},
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code, title = _HTTP_CODES.get(exc.status_code, ("HTTP_ERROR", "Request failed"))
    return problem(
        request, status=exc.status_code, code=code, title=title, detail=str(exc.detail),
        headers=dict(exc.headers or {}),
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("request.unhandled_error", error_type=type(exc).__name__)
    return problem(
        request, status=500, code="INTERNAL_ERROR", title="Internal error",
        detail="The request could not be completed. Quote the traceId when reporting it.", retryable=True,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
