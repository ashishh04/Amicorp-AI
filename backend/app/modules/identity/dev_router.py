"""Local sign-in: mounted only when ENVIRONMENT is local or test (see app/main.py).

The portal (and the tests) pick a local user and receive a signed token, standing in for Microsoft's
account picker. These routes have no permit() on purpose: nobody is signed in yet, and they do not exist
anywhere else.
"""
from fastapi import APIRouter, Request

from app.db.session import UnitOfWork
from app.modules.identity import service
from app.modules.identity.models import AppUser
from app.modules.identity.schemas import CurrentUser, LocalUserPage, SignInRequest, SignInResponse

router = APIRouter(prefix="/dev", tags=["local sign-in"])

_SYSTEM = "svc:local-sign-in"


def _uow(request: Request) -> UnitOfWork:
    return UnitOfWork(request.app.state.session_factory, actor=_SYSTEM, correlation_id=None)


@router.get("/users", response_model=LocalUserPage, summary="Local users to sign in as (local only)")
async def users(request: Request) -> LocalUserPage:
    return LocalUserPage(items=await service.local_users(_uow(request)))


@router.post("/sign-in", response_model=SignInResponse, summary="Sign in as a local user (local only)")
async def sign_in(body: SignInRequest, request: Request) -> SignInResponse:
    user: AppUser = await service.local_user(_uow(request), body.user_id)
    token = request.app.state.dev_signer.issue(str(user.user_id), list(user.roles))
    return SignInResponse(
        access_token=token, token_type="Bearer", expires_in=8 * 3600,  # noqa: S106 - the scheme name, not a secret
        user=CurrentUser(
            id=str(user.user_id), display_name=user.display_name, email=user.email, roles=list(user.roles),
            data_scope=list(user.data_scope), teams=list(user.teams), calendar="EU" if user.calendar == "EU" else "HK",
        ),
    )
