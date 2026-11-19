"""HTTP layer for cards: n8n creates them, officers read and decide them in the portal.

The statement lookups are composed here, so the cards service never imports the statements module.
"""
import uuid
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.config import get_settings
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.integrations import maas
from app.modules.cards import service
from app.modules.cards.ports import Assistant, SubjectInfo
from app.modules.cards.schemas import (
    AssistantAnswer,
    AssistantQuestion,
    CardCounts,
    CardCreate,
    CardCreated,
    CardDetail,
    CardPage,
    CardTypePage,
    DecisionRequest,
    PersonPage,
    RecommendAccepted,
    RecommendRequest,
)
from app.modules.cards.types import Severity
from app.modules.statements import service as statements
from app.modules.transaction_monitoring import service as transactions
from app.shared.idempotency import IdempotentCommand, idempotent, idempotent_optional

router = APIRouter(tags=["cards"])

View = Literal["mine", "team", "due-soon", "overdue", "escalated", "closed"]
UseCase = Literal["UC1", "UC2", "UC3", "UC4", "UC5"]  # the keys of types.USE_CASE_PREFIX


@router.post(
    "/cards",
    status_code=201,
    response_model=CardCreated,
    summary="Create a Work Card (all workflows)",
    responses={200: {"model": CardCreated, "description": "A card with this Idempotency-Key already exists"}},
)
async def create_card(
    body: Annotated[CardCreate, Body(discriminator="type")],
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    # The Idempotency-Key is the card's business identity (README: cards are keyed by business identity).
    return await cmd.run(
        lambda uow: service.create_card(uow, body, cmd.key, describe=describe_subject),
        status_for=lambda result: 201 if result.created else 200,
        mode="business-key",
    )


async def describe_subject(uow: UnitOfWork, card_type: str, subject_id: str) -> SubjectInfo | None:
    """The module that owns the subject names it: statements for UC1 and UC3, payments for UC2."""
    if card_type.startswith("aml."):
        return await transactions.describe(uow, card_type, subject_id)
    return await statements.describe_subject(uow, card_type, subject_id)


@lru_cache(maxsize=1)
def card_assistant() -> Assistant:
    return maas.assistant(get_settings())


@router.post(
    "/cards/{card_id}/recommend",
    status_code=202,
    response_model=RecommendAccepted,
    summary="Assemble evidence and an AI recommendation (UC4, UC5)",
)
async def recommend(
    card_id: uuid.UUID,
    body: RecommendRequest,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.request_recommendation(uow, card_id, body), status_for=lambda _: 202)


@router.get("/cards", response_model=CardPage, summary="Inbox: the cards in the caller's scope")
async def list_cards(
    view: View | None = None,
    q: str | None = Query(default=None, max_length=100),
    use_case: Annotated[UseCase | None, Query(alias="useCase")] = None,
    card_type: str | None = Query(default=None, alias="type", max_length=64),
    severity: Severity | None = None,
    sort: Literal["dueAt", "-updatedAt"] | None = None,
    limit: int | None = Query(default=None, ge=1, le=500),
    cursor: str | None = Query(default=None, max_length=512),
    principal: Principal = Depends(permit(Perm.CARD_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> CardPage:
    return await service.list_cards(
        uow, principal, view=view, q=q, use_case=use_case, card_type=card_type, severity=severity, sort=sort,
        limit=limit, cursor=cursor,
    )


@router.get("/cards/counts", response_model=CardCounts, summary="One number per inbox view")
async def counts(
    principal: Principal = Depends(permit(Perm.CARD_READ)), uow: UnitOfWork = Depends(get_uow)
) -> CardCounts:
    return await service.counts(uow, principal)


@router.get("/cards/{card_id}", response_model=CardDetail, summary="A card with evidence, history and hints")
async def get_card(
    card_id: uuid.UUID, principal: Principal = Depends(permit(Perm.CARD_READ)), uow: UnitOfWork = Depends(get_uow)
) -> CardDetail:
    return await service.get_detail(uow, principal, card_id, statements.card_facts)


@router.post("/cards/{card_id}/decisions", response_model=CardDetail, summary="Approve, reject, return or delegate")
async def decide(
    card_id: uuid.UUID,
    body: DecisionRequest,
    principal: Principal = Depends(permit(Perm.CARD_DECIDE)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> JSONResponse:
    return await cmd.run(
        lambda uow: service.decide(uow, principal, card_id, body, statements.card_facts), status_for=lambda _: 200
    )


@router.post("/cards/{card_id}/assistant", response_model=AssistantAnswer, summary="Ask about this card's evidence")
async def ask_assistant(
    card_id: uuid.UUID,
    body: AssistantQuestion,
    principal: Principal = Depends(permit(Perm.CARD_READ)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> AssistantAnswer:
    # Changes no card: a repeated question is simply asked again, so the key is accepted and not stored.
    return await service.ask(cmd.uow, principal, card_id, body, statements.card_facts, card_assistant())


@router.get("/cards/{card_id}/delegates", response_model=PersonPage, summary="Who may take this card")
async def delegates(
    card_id: uuid.UUID,
    principal: Principal = Depends(permit(Perm.CARD_DELEGATES)),
    uow: UnitOfWork = Depends(get_uow),
) -> PersonPage:
    return await service.delegates(uow, principal, card_id)


@router.get("/card-types", response_model=CardTypePage, summary="The card type registry")
async def card_types(_: Principal = Depends(permit(Perm.CARD_TYPES_READ))) -> CardTypePage:
    return service.card_types()
