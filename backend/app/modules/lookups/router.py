"""HTTP layer for lookups."""
from fastapi import APIRouter, Depends, Query

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.modules.lookups import service
from app.modules.lookups.schemas import LookupPage

router = APIRouter(prefix="/lookups", tags=["lookups"])


@router.get("/en-numbers", response_model=LookupPage, summary="Search today's EN-number lookup table")
async def en_numbers(
    q: str | None = Query(default=None, max_length=64),
    _: Principal = Depends(permit(Perm.LOOKUP_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> LookupPage:
    return LookupPage(items=await service.search_en_numbers(uow, q))
