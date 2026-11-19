from decimal import Decimal

import pytest

from app.modules.gates.jsonlogic import RuleError, evaluate, run_rules
from scripts.seed import FIELD_VALIDATION, field_validation_rules


def test_numbers_compare_as_decimals():
    assert evaluate({"==": [{"var": "x"}, 0.7]}, {"x": Decimal("0.70")}) is True
    assert evaluate({"<": [{"var": "x"}, 0.7]}, {"x": 0.58}) is True
    assert evaluate({">=": [{"var": "x"}, 1]}, {"x": Decimal("1.00")}) is True


def test_values_of_different_kinds_are_never_equal():
    assert evaluate({"==": [{"var": "x"}, "1"]}, {"x": 1}) is False
    assert evaluate({"!=": [{"var": "x"}, "1"]}, {"x": 1}) is True


def test_and_or_not():
    inputs = {"a": 1, "b": 0}
    assert evaluate({"and": [{">": [{"var": "a"}, 0]}, {"==": [{"var": "b"}, 0]}]}, inputs) is True
    assert evaluate({"or": [{">": [{"var": "a"}, 5]}, {"<": [{"var": "b"}, 1]}]}, inputs) is True
    assert evaluate({"!": {">": [{"var": "a"}, 5]}}, inputs) is True


@pytest.mark.parametrize("expr, inputs", [
    ({"<": [{"var": "missing"}, 1]}, {}),  # a missing input never reads as 0
    ({"<": [{"var": "x"}, 1]}, {"x": None}),
    ({"<": [{"var": "x"}, 1]}, {"x": True}),  # a boolean is not a number
    ({"geoRisk": ["IR"]}, {}),  # an operator the engine does not know
    ({"<": [1]}, {}),
])
def test_what_it_cannot_decide_raises(expr, inputs):
    with pytest.raises(RuleError):
        evaluate(expr, inputs)


def test_the_first_matching_rule_decides():
    rules = [
        {"id": "R1", "desc": "big", "when": {">": [{"var": "n"}, 10]}, "then": "alert"},
        {"id": "R2", "desc": "any", "when": True, "then": "clear"},
    ]
    result = run_rules(rules, {"n": 11})
    assert (result.outcome, result.rule_id) == ("alert", "R1")
    assert [t.matched for t in result.trace] == [True]
    assert run_rules(rules, {"n": 3}).rule_id == "R2"


def test_a_ruleset_without_a_catch_all_raises_when_nothing_matches():
    with pytest.raises(RuleError):
        run_rules([{"id": "R1", "desc": "big", "when": {">": [{"var": "n"}, 10]}, "then": "alert"}], {"n": 1})


@pytest.mark.parametrize("band", ["0.70", "0.75"])
def test_the_seeded_field_validation_rules_pass_their_regression_cases(band):
    for case in FIELD_VALIDATION["regression_cases"]:
        assert run_rules(field_validation_rules(band), case["inputs"]).outcome == case["expected"], case["name"]
