"""HTTP layer for identity: /v1/me and the data-scope settings."""
from fastapi import APIRouter, Depends

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.modules.identity import service
from app.modules.identity.schemas import CurrentUser, DataScopePage

router = APIRouter(tags=["identity"])


@router.get("/me", response_model=CurrentUser, summary="The signed-in person: roles, teams, data scope")
async def me(principal: Principal = Depends(permit(Perm.ME)), uow: UnitOfWork = Depends(get_uow)) -> CurrentUser:
    return await service.current_user(uow, principal)


@router.get("/settings/data-scope", response_model=DataScopePage, summary="Entra groups and their data scope")
async def data_scope(
    _: Principal = Depends(permit(Perm.SETTINGS_READ)), uow: UnitOfWork = Depends(get_uow)
) -> DataScopePage:
    return DataScopePage(items=await service.data_scope_groups(uow))
