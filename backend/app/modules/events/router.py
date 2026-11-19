"""HTTP layer for live events: GET /v1/events/ticket and GET /v1/events/stream (SSE)."""
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.core.authz import PERM_MARKER, POLICY, Perm, permit
from app.core.errors import Forbidden
from app.core.principal import Principal
from app.modules.events import service
from app.shared.schemas import ApiModel

router = APIRouter(prefix="/events", tags=["events"])


class Ticket(ApiModel):
    ticket: str


def _ticket_principal() -> Callable[..., Awaitable[Principal]]:
    """EventSource cannot send a bearer token, so the stream authenticates with its ticket, then checks the same
    permission as every other route."""
    allowed = POLICY[Perm.EVENTS_READ]

    async def check(request: Request, ticket: str = Query(min_length=16, max_length=128)) -> Principal:
        principal = await service.redeem_ticket(request.app.state.redis, ticket)
        if not principal.roles & allowed:
            raise Forbidden("Live updates need a portal role.")
        return principal

    setattr(check, PERM_MARKER, Perm.EVENTS_READ)
    return check


ticket_principal = _ticket_principal()


@router.get("/ticket", response_model=Ticket, summary="A one-minute, single-use ticket for the event stream")
async def ticket(request: Request, principal: Principal = Depends(permit(Perm.EVENTS_READ))) -> Ticket:
    return Ticket(ticket=await service.issue_ticket(request.app.state.redis, principal))


@router.get(
    "/stream",
    summary="Server-sent events: card.created, card.updated, card.assigned, statement.updated",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream(
    request: Request,
    last_event_id: int | None = Query(default=None, alias="lastEventId", ge=0),
    principal: Principal = Depends(ticket_principal),
) -> StreamingResponse:
    events = service.stream(request.app.state.session_factory, principal, last_event_id, request.is_disconnected)
    return StreamingResponse(events, media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",  # proxies must pass each event on at once
    })
