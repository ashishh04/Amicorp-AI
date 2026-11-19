"""HTTP layer for audit search."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.modules.audit_log import service
from app.modules.audit_log.schemas import AuditPage

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=AuditPage, summary="Search the audit trail, newest first")
async def events(
    q: str | None = Query(default=None, max_length=100),
    entity: str | None = Query(default=None, max_length=64),
    actor: str | None = Query(default=None, max_length=100),
    since: datetime | None = None,
    limit: int | None = Query(default=None, ge=1, le=500),
    cursor: str | None = Query(default=None, max_length=512),
    principal: Principal = Depends(permit(Perm.AUDIT_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> AuditPage:
    return await service.list_events(
        uow, principal, q=q, entity=entity, actor=actor, since=since, limit=limit, cursor=cursor
    )
