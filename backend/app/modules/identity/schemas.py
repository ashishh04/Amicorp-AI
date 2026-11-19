"""Pydantic models for /v1/me, the data-scope settings and local sign-in (portal contract field names)."""
from typing import Literal

from app.shared.schemas import ApiModel


class PersonRef(ApiModel):
    id: str
    name: str


class CurrentUser(ApiModel):
    id: str
    display_name: str
    email: str
    roles: list[str]
    data_scope: list[str]
    teams: list[str]
    calendar: Literal["HK", "EU"]


class DataScopeGroup(ApiModel):
    group: str
    team: str
    role: str
    calendar: Literal["HK", "EU"]
    members: int
    scope: str


class DataScopePage(ApiModel):
    items: list[DataScopeGroup]


class LocalUser(ApiModel):
    id: str
    display_name: str
    roles: list[str]
    teams: list[str]


class LocalUserPage(ApiModel):
    items: list[LocalUser]


class SignInRequest(ApiModel):
    user_id: str


class SignInResponse(ApiModel):
    access_token: str
    token_type: Literal["Bearer"]
    expires_in: int
    user: CurrentUser
