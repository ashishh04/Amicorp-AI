"""HTTP layer for notifications. Validate input, call the service, return schemas."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationCreate, NotificationQueued
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post(
    "",
    status_code=202,
    response_model=NotificationQueued,
    summary="Queue a Teams notification for a card owner or a role",
)
async def queue_notification(
    body: NotificationCreate,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.queue_notification(uow, body), status_for=lambda _: 202)
