"""The Work Card state machine and decision rules (LLD, Work Card Model; portal contract, Rules).

Pure: no I/O and no frameworks. `decision_gate` is the one place the decision rules live: the card
detail uses it for the portal's action hints, and the decision endpoint uses it to enforce, so the
buttons and the API can never disagree. It follows the portal mock's gate() rule for rule.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.principal import Role
from app.modules.cards.types import SEVERITY_ORDER, Severity
from app.shared.action_gate import ALLOW, Gate

STATES = (
    "NEW", "ASSEMBLING", "AWAITING_DECISION", "ESCALATED", "APPROVED", "REJECTED",
    "WRITING_BACK", "WRITEBACK_FAILED", "REVERSED", "CLOSED",
)
OPEN_STATES = ("NEW", "ASSEMBLING", "AWAITING_DECISION", "ESCALATED", "WRITING_BACK", "WRITEBACK_FAILED")
WAITING_STATES = ("NEW", "ASSEMBLING", "AWAITING_DECISION", "ESCALATED")  # the SLA still runs
CLOSED_STATES = ("CLOSED", "REJECTED", "REVERSED", "APPROVED")
DECISIONS = ("APPROVE", "REJECT", "RETURN_TO_AI", "DELEGATE")
RETURN_LIMIT = 3
DELEGATION_LIMIT = 2
DUE_SOON = timedelta(hours=4)

# Every allowed move. One function applies them all, so an illegal move cannot be written.
TRANSITIONS: dict[str, frozenset[str]] = {
    "NEW": frozenset({"ASSEMBLING"}),
    "ASSEMBLING": frozenset({"AWAITING_DECISION", "ESCALATED"}),
    "AWAITING_DECISION": frozenset({"APPROVED", "REJECTED", "ASSEMBLING", "AWAITING_DECISION", "ESCALATED"}),
    "ESCALATED": frozenset({"ASSEMBLING"}),
    "APPROVED": frozenset({"WRITING_BACK", "CLOSED"}),
    "REJECTED": frozenset({"CLOSED"}),
    "WRITING_BACK": frozenset({"CLOSED", "WRITEBACK_FAILED"}),
    "WRITEBACK_FAILED": frozenset({"WRITING_BACK", "REVERSED"}),
    "REVERSED": frozenset({"CLOSED"}),
    "CLOSED": frozenset(),
}


class IllegalTransition(ValueError):
    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(f"A card cannot move from {from_state} to {to_state}")
        self.from_state, self.to_state = from_state, to_state


def check_transition(from_state: str, to_state: str) -> None:
    if to_state not in TRANSITIONS.get(from_state, frozenset()):
        raise IllegalTransition(from_state, to_state)


def effective_severity(default: Severity, requested: Severity | None) -> Severity:
    """A caller may raise a card's severity, never lower it below its type's default."""
    if requested is None:
        return default
    return max(default, requested, key=SEVERITY_ORDER.index)


@dataclass(frozen=True)
class Who:
    """The person asking: id, app roles (from the token) and teams (from the directory)."""

    user_id: uuid.UUID
    roles: frozenset[Role]
    teams: tuple[str, ...]

    def has(self, role: Role) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class CardFacts:
    type: str
    state: str
    team: str
    owner_id: uuid.UUID | None
    owner_name: str
    maker_id: uuid.UUID | None
    delegations: int
    unmet_checks: tuple[str, ...] = field(default=())


def can_see(card_type: str, team: str, owner_id: uuid.UUID | None, who: Who) -> bool:
    """The owning team decides who sees a card; the MLRO sees AML cards; Auditors see all; Admins none."""
    if who.has(Role.AUDITOR):
        return True
    if who.has(Role.MLRO) and card_type.startswith("aml."):
        return True
    if owner_id is not None and owner_id == who.user_id:
        return True
    return (who.has(Role.MAKER) or who.has(Role.CHECKER)) and team in who.teams


def decision_gate(card: CardFacts, who: Who, decision: str, delegate_count: int) -> Gate:
    if who.roles and who.roles <= {Role.AUDITOR}:
        return Gate(False, "Auditors have read-only access.", 403)
    if card.state != "AWAITING_DECISION":
        return Gate(False, f"The card is {_label(card.state)}; decisions are taken while it awaits a decision.", 409)

    is_aml = card.type.startswith("aml.")
    mlro_only = card.type == "aml.mlro-escalation"
    in_team = card.team in who.teams
    decider = who.has(Role.MLRO) if mlro_only else (
        (who.has(Role.CHECKER) and in_team) or (is_aml and who.has(Role.MLRO))
    )

    if decision == "RETURN_TO_AI":
        preparer = who.has(Role.MAKER) and in_team
        if decider or preparer:
            return ALLOW
        return Gate(False, f"Return-to-AI needs the Maker or Checker role in the {card.team} team.", 403)
    if not decider:
        if mlro_only:
            return Gate(False, "Only the MLRO decides MLRO escalations.", 403)
        action = "Delegate" if decision == "DELEGATE" else "Approve and Reject"
        verb = "needs" if decision == "DELEGATE" else "need"
        return Gate(False, f"{action} {verb} the Checker role in the {card.team} team.", 403)
    if card.owner_id != who.user_id:
        return Gate(False, f"Only the owner ({card.owner_name}) or their delegate can decide this card.", 403)
    if decision == "DELEGATE":
        if card.delegations >= DELEGATION_LIMIT:
            return Gate(False, f"A card can be delegated at most {DELEGATION_LIMIT} times.", 409)
        if delegate_count == 0:
            return Gate(False, f"Nobody else in the {card.team} team can take this card.", 409)
        return ALLOW
    if card.maker_id is not None and card.maker_id == who.user_id:
        return Gate(False, "You prepared this card, so maker-checker stops you deciding it. "
                           "Delegate it to another Checker.", 403)
    if decision == "APPROVE" and card.unmet_checks:
        return Gate(False, f"Approve once every mandatory check is met. Still open: {'; '.join(card.unmet_checks)}.",
                    422)
    return ALLOW


def in_view(view: str, state: str, due_at: datetime, owner_id: uuid.UUID | None, who: Who, now: datetime) -> bool:
    """Inbox views (portal contract, GET /v1/cards). The SQL in the repository applies the same rules."""
    match view:
        case "mine":
            return state in OPEN_STATES and owner_id == who.user_id
        case "team":
            return state in OPEN_STATES
        case "due-soon":
            return state in WAITING_STATES and now <= due_at <= now + DUE_SOON
        case "overdue":
            return state in WAITING_STATES and due_at < now
        case "escalated":
            return state == "ESCALATED"
        case "closed":
            return state in CLOSED_STATES
    return False


def _label(state: str) -> str:
    return state.replace("_", " ").lower()
