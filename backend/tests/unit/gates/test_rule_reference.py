"""The AML operators, draft validation, and every seeded ruleset against its own regression cases."""
import pytest

from app.modules.gates.jsonlogic import Env, RuleError, evaluate, run_rules, validate
from scripts.seed import COUNTRY_RISK, NAMED_LISTS, RULESETS

ENV = Env(lists={"exclusion": frozenset(v for name, v, _ in NAMED_LISTS if name == "exclusion")},
          country_risk=dict(COUNTRY_RISK))


def test_in_list_checks_a_named_list():
    assert evaluate({"inList": ["exclusion", {"var": "cp"}]}, {"cp": "CP-00001-INTERNAL"}, ENV) is True
    assert evaluate({"inList": ["exclusion", {"var": "cp"}]}, {"cp": "CP-88120"}, ENV) is False
    with pytest.raises(RuleError):
        evaluate({"inList": ["no-such-list", "x"]}, {}, ENV)


def test_country_risk_defaults_to_low():
    assert evaluate({"countryRisk": [{"var": "c"}]}, {"c": "ir"}, ENV) == "high"
    assert evaluate({"countryRisk": [{"var": "c"}]}, {"c": "AE"}, ENV) == "medium"
    assert evaluate({"countryRisk": [{"var": "c"}]}, {"c": "SG"}, ENV) == "low"


def test_sum_window_reads_the_total_the_resolver_summed():
    assert evaluate({"sumWindow": ["amountUsd", 7, "entityKey"]}, {"amountUsdSum7d": 12500}, ENV) == 12500
    with pytest.raises(RuleError):
        evaluate({"sumWindow": ["amountUsd", 7]}, {"amountUsd": 1}, ENV)  # a missing total is never zero


def test_in_takes_a_literal_list():
    assert evaluate({"in": [{"var": "x"}, ["a", "b"]]}, {"x": "b"}) is True


def test_validation_explains_every_problem():
    errors = validate([
        {"id": "x1", "desc": "", "when": {"nope": [1]}, "then": "maybe"},
        {"id": "R-2", "desc": "fine", "when": {"==": [{"var": "a"}, 1]}, "then": "pass"},
        {"id": "R-2", "desc": "twice", "when": {"<": [1]}, "then": "pass"},
    ], ["pass", "fail"])
    assert errors == [
        "Rule 1: the ID must be 2 to 16 capital letters, digits or hyphens.",
        "Rule 1: add a description.",
        'Rule 1: the outcome "maybe" is not one of pass, fail.',
        'Rule 1: Unknown operator "nope".',
        "Rule 3: the ID R-2 is used twice.",
        'Rule 3: "<" takes 2 argument(s).',
        "The last rule must be a catch-all (condition true), so every input gets an outcome.",
    ]
    assert validate([], ["pass"]) == ["A ruleset needs at least one rule."]


@pytest.mark.parametrize("ruleset", RULESETS, ids=[r["key"] for r in RULESETS])
def test_each_seeded_ruleset_is_valid_and_its_newest_version_passes_every_case(ruleset):
    newest = max(ruleset["versions"], key=lambda v: v["version"])
    for version in ruleset["versions"]:
        assert validate(version["rules"], ruleset["outcomes"]) == [], (ruleset["key"], version["version"])
    for case in ruleset["regression_cases"]:
        assert run_rules(newest["rules"], case["inputs"], ENV).outcome == case["expected"], case["name"]


def test_gate1_v3_misses_only_the_structuring_case_that_v4_adds():
    gate1 = next(r for r in RULESETS if r["key"] == "aml.gate1-entry")
    v3 = next(v for v in gate1["versions"] if v["version"] == 3)
    failing = [c["name"] for c in gate1["regression_cases"]
               if run_rules(v3["rules"], c["inputs"], ENV).outcome != c["expected"]]
    assert failing == ["Structuring pattern (needs v4)"]
