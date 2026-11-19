"""HTTP layer for the KPI dashboard."""
from fastapi import APIRouter, Depends, Query

from app.core.authz import Perm, permit
from app.core.config import Settings, get_settings
from app.core.errors import Unprocessable
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.modules.dashboard import service
from app.modules.dashboard.schemas import KpiSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RANGES = (7, 14, 30, 90)


@router.get("/summary", response_model=KpiSummary, summary="Operational KPIs over 7, 14, 30 or 90 days")
async def summary(
    days: int = Query(default=14, description="7, 14, 30 or 90"),
    settings: Settings = Depends(get_settings),
    _: Principal = Depends(permit(Perm.KPI_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> KpiSummary:
    if days not in RANGES:
        raise Unprocessable("The range is 7, 14, 30 or 90 days.")
    budget = (settings.maas_monthly_input_tokens, settings.maas_monthly_output_tokens)
    return await service.summary(uow, days, budget)
