"""Authorisation: the only place app roles meet permissions (blueprint section 9).

Every route declares one permission with `permit(Perm.X)`. A route without one fails the route-walk
test, so nothing is reachable by accident. Data scope and duty rules (maker-checker, owner, four eyes)
are checked after this, in the services and the domain code.
"""
from collections.abc import Awaitable, Callable
from enum import StrEnum

import structlog
from fastapi import Depends

from app.core.errors import Forbidden
from app.core.principal import Principal, Role
from app.core.security import current_principal

log = structlog.get_logger()

M, C, ML, AD, AU = Role.MAKER, Role.CHECKER, Role.MLRO, Role.ADMIN, Role.AUDITOR


class Perm(StrEnum):
    WORKFLOW_CALL = "workflow:call"  # endpoints the n8n workflows call
    INCIDENT_READ = "incident:read"
    SCAN_READ = "scan:read"  # n8n polls scans; Admins and Auditors read the history
    ME = "me:read"
    CARD_READ = "card:read"
    CARD_DECIDE = "card:decide"  # Makers may Return-to-AI; the decision gate checks the rest
    CARD_DELEGATES = "card:delegates"
    CARD_TYPES_READ = "card-types:read"
    SETTINGS_READ = "settings:read"
    STATEMENT_READ = "statement:read"
    STATEMENT_EDIT = "statement:edit"
    LOOKUP_READ = "lookup:read"
    AUDIT_READ = "audit:read"  # the MLRO sees only the AML part (filtered in the audit module)
    EVENTS_READ = "events:read"  # the stream then sends only the cards the person may see
    RULESET_READ = "ruleset:read"  # list and test (no side effects)
    RULESET_DRAFT = "ruleset:draft"  # Admins draft under change control
    RULESET_APPROVE = "ruleset:approve"  # who may approve which ruleset is checked in the gates module
    KPI_READ = "kpi:read"


POLICY: dict[Perm, frozenset[Role]] = {
    Perm.WORKFLOW_CALL: frozenset({Role.AUTOMATION}),
    Perm.INCIDENT_READ: frozenset({AD, AU, ML}),
    Perm.SCAN_READ: frozenset({Role.AUTOMATION, AD, AU}),
    Perm.ME: frozenset({M, C, ML, AD, AU}),
    Perm.CARD_READ: frozenset({M, C, ML, AU}),  # Admins configure; they see no cards
    Perm.CARD_DECIDE: frozenset({M, C, ML}),
    Perm.CARD_DELEGATES: frozenset({C, ML}),
    Perm.CARD_TYPES_READ: frozenset({AD}),
    Perm.SETTINGS_READ: frozenset({AD}),
    Perm.STATEMENT_READ: frozenset({M, C, AU}),
    Perm.STATEMENT_EDIT: frozenset({M}),
    Perm.LOOKUP_READ: frozenset({M, C, AU}),
    Perm.AUDIT_READ: frozenset({AU, ML}),
    Perm.EVENTS_READ: frozenset({M, C, ML, AD, AU}),
    Perm.RULESET_READ: frozenset({AD, C, ML}),
    Perm.RULESET_DRAFT: frozenset({AD}),
    Perm.RULESET_APPROVE: frozenset({C, ML}),
    Perm.KPI_READ: frozenset({C, ML, AD}),
}

PERM_MARKER = "__amc_permission__"


def permit(perm: Perm) -> Callable[..., Awaitable[Principal]]:
    allowed = POLICY[perm]
    needed = " or ".join(sorted(r.value for r in allowed))

    async def check(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.roles & allowed:
            log.warning("authz.denied", permission=perm.value)
            raise Forbidden(f"This needs the {needed} role.")
        return principal

    setattr(check, PERM_MARKER, perm)
    return check
