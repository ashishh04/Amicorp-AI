"""Business rules for the user directory. No HTTP or SQL here."""
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.errors import NotFound, Unauthorized
from app.core.principal import Principal, Role
from app.db.session import UnitOfWork
from app.modules.identity.models import AppUser
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import CurrentUser, DataScopeGroup, LocalUser, PersonRef

SERVICE_NAMES = {
    "svc:automation-dev": "n8n (automation)",
    "svc:jobs-worker": "platform-api-worker",
}


@dataclass(frozen=True)
class Caller:
    """A signed-in person: app roles from the token, teams from the directory."""

    user_id: uuid.UUID
    name: str
    roles: frozenset[Role]
    teams: tuple[str, ...]

    def has(self, role: Role) -> bool:
        return role in self.roles

    @property
    def auditor_only(self) -> bool:
        return bool(self.roles) and self.roles <= {Role.AUDITOR}

    @property
    def ref(self) -> PersonRef:
        return PersonRef(id=str(self.user_id), name=self.name)


def user_id_of(principal: Principal) -> uuid.UUID:
    if principal.kind != "user":
        raise Unauthorized("This needs a signed-in person, not a service identity")
    try:
        return uuid.UUID(principal.subject)
    except ValueError as exc:
        raise Unauthorized("The token's object ID is not valid") from exc


async def caller(uow: UnitOfWork, principal: Principal) -> Caller:
    user_id = user_id_of(principal)
    user = await UserRepository(uow.session).get(user_id)
    active = user is not None and user.active
    return Caller(
        user_id=user_id,
        name=user.display_name if user else "Unknown user",
        roles=principal.roles,
        teams=tuple(user.teams) if active and user else (),
    )


async def current_user(uow: UnitOfWork, principal: Principal) -> CurrentUser:
    async with uow:
        user_id = user_id_of(principal)
        user = await UserRepository(uow.session).get(user_id)
        return CurrentUser(
            id=str(user_id),
            display_name=user.display_name if user else "Unknown user",
            email=user.email if user else "",
            roles=sorted(r.value for r in principal.roles),
            data_scope=list(user.data_scope) if user else [],
            teams=list(user.teams) if user and user.active else [],
            calendar="EU" if user and user.calendar == "EU" else "HK",
        )


async def display_names(uow: UnitOfWork, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    return {u.user_id: u.display_name for u in await UserRepository(uow.session).many(ids)}


def actor_name(actor: str, names: dict[uuid.UUID, str]) -> str:
    """'user:<oid>' -> the person's name; 'svc:...' -> the service's name."""
    if actor.startswith("user:"):
        try:
            return names.get(uuid.UUID(actor[5:]), "Unknown user")
        except ValueError:
            return "Unknown user"
    return SERVICE_NAMES.get(actor, actor)


async def actors_named(uow: UnitOfWork, text: str) -> list[str]:
    """The audit actors ('user:<oid>', 'svc:...') whose name contains `text`. Call inside a unit of work."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    people = await UserRepository(uow.session).named_like(f"%{escaped}%")
    services = [actor for actor, name in SERVICE_NAMES.items() if text.lower() in name.lower()]
    return [f"user:{p.user_id}" for p in people] + services


async def deciders(uow: UnitOfWork, team: str, mlro_only: bool) -> list[AppUser]:
    """Who may take a card: the MLRO for MLRO escalations, otherwise the Checkers of the owning team."""
    users = await UserRepository(uow.session).active()
    if mlro_only:
        return [u for u in users if Role.MLRO.value in u.roles]
    return [u for u in users if Role.CHECKER.value in u.roles and team in u.teams]


async def data_scope_groups(uow: UnitOfWork) -> list[DataScopeGroup]:
    async with uow:
        users = await UserRepository(uow.session).active()
    members: dict[tuple[str, str], list[AppUser]] = defaultdict(list)
    for user in users:
        for role in user.roles:
            for team in user.teams or ["-"]:
                members[(role, team)].append(user)
    groups = []
    for (role, team), people in sorted(members.items()):
        scope = sorted({s for p in people for s in p.data_scope})
        groups.append(DataScopeGroup(
            group=f"AMC-IPA-{role}-{_slug(team)}", team=team, role=role,
            calendar="EU" if all(p.calendar == "EU" for p in people) else "HK",
            members=len(people), scope=", ".join(scope) or "None",
        ))
    return groups


async def local_users(uow: UnitOfWork) -> list[LocalUser]:
    async with uow:
        users = await UserRepository(uow.session).active()
    return [LocalUser(id=str(u.user_id), display_name=u.display_name, roles=list(u.roles), teams=list(u.teams))
            for u in users]


async def local_user(uow: UnitOfWork, user_id: str) -> AppUser:
    try:
        wanted = uuid.UUID(user_id)
    except ValueError as exc:
        raise NotFound("No local user with this ID") from exc
    async with uow:
        user = await UserRepository(uow.session).get(wanted)
    if user is None or not user.active:
        raise NotFound("No local user with this ID")
    return user


def _slug(team: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", team.title())
