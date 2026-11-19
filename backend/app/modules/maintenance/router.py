"""HTTP layer for maintenance: the stuck-item sweeper's re-drive."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.config import Settings, get_settings
from app.core.principal import Principal
from app.modules.extraction.service import allowed_callbacks
from app.modules.maintenance import service
from app.modules.maintenance.schemas import RedriveRequest, RedriveResult
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.post("/redrive", response_model=RedriveResult, summary="Re-drive stuck items (Platform stuck-item sweeper)")
async def redrive(
    body: RedriveRequest,
    settings: Settings = Depends(get_settings),
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    callbacks = allowed_callbacks(settings.n8n_webhook_base)
    return await cmd.run(lambda uow: service.redrive(uow, body, callbacks), status_for=lambda _: 200)
