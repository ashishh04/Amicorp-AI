"""HTTP layer for extraction jobs."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.config import Settings, get_settings
from app.core.principal import Principal
from app.modules.extraction import service
from app.modules.extraction.schemas import ExtractionJobAccepted, ExtractionJobRequest
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post(
    "/jobs", status_code=202, response_model=ExtractionJobAccepted, summary="Submit an extraction job (UC1, UC3)"
)
async def submit(
    body: ExtractionJobRequest,
    settings: Settings = Depends(get_settings),
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    callbacks = service.allowed_callbacks(settings.n8n_webhook_base)
    return await cmd.run(lambda uow: service.submit_job(uow, body, callbacks), status_for=lambda _: 202)
