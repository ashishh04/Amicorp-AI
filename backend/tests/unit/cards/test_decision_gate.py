"""The decision rules (portal contract, Decisions), in the order the contract lists them."""
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.core.principal import Role
from app.modules.cards.domain import CardFacts, Who, can_see, decision_gate, in_view

PRIYA, AHMED, CHAN, DANIEL, MARTIN = (uuid.uuid4() for _ in range(5))

CARD = CardFacts(type="uc1.statement-validation", state="AWAITING_DECISION", team="Operations", owner_id=PRIYA,
                 owner_name="Priya Lam", maker_id=CHAN, delegations=0)
priya = Who(PRIYA, frozenset({Role.CHECKER}), ("Operations",))
ahmed = Who(AHMED, frozenset({Role.CHECKER}), ("Operations",))
chan = Who(CHAN, frozenset({Role.MAKER}), ("Operations",))
daniel = Who(DANIEL, frozenset({Role.MLRO}), ("MLRO office",))
martin = Who(MARTIN, frozenset({Role.AUDITOR}), ("Internal audit",))


def test_the_owner_may_decide():
    assert decision_gate(CARD, priya, "APPROVE", delegate_count=1).allowed


@pytest.mark.parametrize("who, decision, status, reason", [
    (martin, "APPROVE", 403, "Auditors have read-only access."),
    (ahmed, "APPROVE", 403, "Only the owner (Priya Lam) or their delegate can decide this card."),
    (chan, "APPROVE", 403, "Approve and Reject need the Checker role in the Operations team."),
    (chan, "DELEGATE", 403, "Delegate needs the Checker role in the Operations team."),
])
def test_who_is_refused_and_why(who, decision, status, reason):
    gate = decision_gate(CARD, who, decision, delegate_count=1)
    assert (gate.allowed, gate.status, gate.reason) == (False, status, reason)


def test_decisions_need_a_card_awaiting_one():
    gate = decision_gate(replace(CARD, state="ASSEMBLING"), priya, "APPROVE", 1)
    assert gate.status == 409
    assert gate.reason == "The card is assembling; decisions are taken while it awaits a decision."


def test_a_maker_returns_to_the_ai_but_never_approves():
    assert decision_gate(CARD, chan, "RETURN_TO_AI", 1).allowed


def test_maker_checker_stops_the_maker_even_when_they_own_the_card():
    gate = decision_gate(replace(CARD, owner_id=CHAN, maker_id=CHAN), Who(CHAN, frozenset({Role.MAKER, Role.CHECKER}),
                                                                              ("Operations",)), "APPROVE", 1)
    assert gate.status == 403 and gate.reason.startswith("You prepared this card")


def test_approve_waits_for_the_mandatory_checks():
    gate = decision_gate(replace(CARD, unmet_checks=("Statement submitted",)), priya, "APPROVE", 1)
    assert (gate.status, gate.reason) == (422, "Approve once every mandatory check is met. Still open: "
                                               "Statement submitted.")
    assert decision_gate(replace(CARD, unmet_checks=("Statement submitted",)), priya, "REJECT", 1).allowed


def test_delegation_limits():
    assert decision_gate(replace(CARD, delegations=2), priya, "DELEGATE", 1).status == 409
    assert decision_gate(CARD, priya, "DELEGATE", 0).reason == "Nobody else in the Operations team can take this card."


def test_only_the_mlro_decides_an_mlro_escalation():
    card = replace(CARD, type="aml.mlro-escalation", team="MLRO office", owner_id=DANIEL, owner_name="Daniel Wong")
    assert decision_gate(card, daniel, "APPROVE", 0).allowed
    kenneth = Who(uuid.uuid4(), frozenset({Role.CHECKER}), ("MLRO office",))
    assert decision_gate(card, kenneth, "APPROVE", 0).reason == "Only the MLRO decides MLRO escalations."


def test_who_sees_what():
    assert can_see("uc1.statement-validation", "Operations", None, chan)
    assert not can_see("uc1.statement-validation", "Operations", None, daniel)
    assert can_see("aml.compliance-decision", "Compliance", None, daniel)
    assert can_see("uc4.discrepancy", "Data team", None, martin)
    admin = Who(uuid.uuid4(), frozenset({Role.ADMIN}), ("Platform",))
    assert not can_see("uc1.statement-validation", "Operations", None, admin)


def test_inbox_views():
    now = datetime(2026, 10, 28, 4, tzinfo=UTC)
    assert in_view("due-soon", "AWAITING_DECISION", now + timedelta(hours=3), None, priya, now)
    assert not in_view("due-soon", "AWAITING_DECISION", now + timedelta(hours=5), None, priya, now)
    assert in_view("overdue", "ESCALATED", now - timedelta(minutes=1), None, priya, now)
    assert not in_view("overdue", "WRITING_BACK", now - timedelta(minutes=1), None, priya, now)
    assert in_view("mine", "AWAITING_DECISION", now, PRIYA, priya, now)
    assert in_view("closed", "REJECTED", now, None, priya, now)
