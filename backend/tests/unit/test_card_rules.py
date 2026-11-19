import re
from pathlib import Path

import pytest

from app.modules.cards.domain import IllegalTransition, check_transition, effective_severity
from app.modules.cards.types import CARD_TYPES, REVIEW_EVIDENCE

WORKFLOWS = Path(__file__).resolve().parents[3] / "n8n-workflows"


def test_every_card_type_the_workflows_create_is_registered():
    created = set()
    for file in WORKFLOWS.glob("*/*.json"):
        created |= set(re.findall(r"type: '([a-z0-9.-]+)'", file.read_text(encoding="utf-8")))
    assert created, "no card types found in the workflow files"
    assert created <= set(CARD_TYPES), f"unregistered: {created - set(CARD_TYPES)}"


def test_owning_teams_match_the_portal():
    assert {d.team for d in CARD_TYPES.values()} == {
        "Operations", "Compliance", "MLRO office", "Fund accounting", "Data team",
    }


def test_uc4_and_uc5_ask_for_a_recommendation_and_every_other_card_is_reviewed():
    modes = {t: d.recommend_mode for t, d in CARD_TYPES.items()}
    assert {t for t, m in modes.items() if m != REVIEW_EVIDENCE} == {"uc4.discrepancy", "uc5.violation"}
    assert None not in modes.values()  # every card waits in ASSEMBLING for its AI step


def test_allowed_and_forbidden_moves():
    check_transition("NEW", "ASSEMBLING")
    check_transition("AWAITING_DECISION", "APPROVED")
    for from_state, to_state in [("NEW", "APPROVED"), ("CLOSED", "ASSEMBLING"), ("REJECTED", "APPROVED")]:
        with pytest.raises(IllegalTransition):
            check_transition(from_state, to_state)


def test_severity_can_rise_but_never_fall_below_the_default():
    assert effective_severity("critical", "high") == "critical"
    assert effective_severity("low", "high") == "high"
    assert effective_severity("medium", None) == "medium"
