"""The rule interpreter: a small JsonLogic subset, evaluated in order, first match wins (LLD, Rule engine).

Pure: no I/O. Numbers compare as Decimal, so 0.7 in a rule and 0.70 from a NUMERIC column are equal.
Anything the interpreter cannot decide raises RuleError, and the gate service then applies the ruleset's
fail-closed outcome. It never guesses: a missing input is an error, never a zero.

The AML operators read reference data the gate service loads before evaluating (Env): `inList` checks a
named list (for example the exclusion list), `countryRisk` reads the country-risk table, and `sumWindow` reads
the window total the input resolver has already summed from the lake (`amountUsdSum7d`).
"""
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

Inputs = Mapping[str, Any]

RULE_ID = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,15}$")
# Operator -> (minimum, maximum) number of arguments; None means no maximum.
ARITY: dict[str, tuple[int, int | None]] = {
    "var": (1, 1), "and": (1, None), "or": (1, None), "!": (1, 1), "not": (1, 1),
    "==": (2, 2), "!=": (2, 2), ">": (2, 2), ">=": (2, 2), "<": (2, 2), "<=": (2, 2), "in": (2, 2),
    "inList": (2, 2), "countryRisk": (1, 1), "sumWindow": (2, 3),
}


class RuleError(ValueError):
    """The rules cannot be evaluated: an unknown operator, a missing input, a value of the wrong type."""


@dataclass(frozen=True)
class Env:
    """Reference data for the AML operators: named lists, and the risk of each country (ISO alpha-2)."""

    lists: Mapping[str, frozenset[str]] = field(default_factory=dict)
    country_risk: Mapping[str, str] = field(default_factory=dict)


NO_REFERENCE_DATA = Env()


@dataclass(frozen=True)
class Trace:
    id: str
    desc: str
    matched: bool


@dataclass(frozen=True)
class Result:
    outcome: str
    rule_id: str
    rule_desc: str
    trace: tuple[Trace, ...]


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RuleError(f"Expected a number, got {value!r}")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float | str):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise RuleError(f"Expected a number, got {value!r}") from exc
    raise RuleError(f"Expected a number, got {type(value).__name__}")


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _equal(a: Any, b: Any) -> bool:
    if _is_number(a) and _is_number(b):
        return _number(a) == _number(b)
    return bool(a == b and type(a) is type(b))


_COMPARE: dict[str, Callable[[Decimal, Decimal], bool]] = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


def _operator(expr: dict[str, Any]) -> tuple[str, list[Any]]:
    if len(expr) != 1:
        raise RuleError("An expression has exactly one operator")
    op, raw = next(iter(expr.items()))
    if op not in ARITY:
        raise RuleError(f'Unknown operator "{op}"')
    args: list[Any] = raw if isinstance(raw, list) else [raw]
    low, high = ARITY[op]
    if len(args) < low or (high is not None and len(args) > high):
        raise RuleError(f'"{op}" takes {low if low == high else f"{low} or more"} argument(s)')
    return op, args


def evaluate(expr: Any, inputs: Inputs, env: Env = NO_REFERENCE_DATA) -> Any:
    if isinstance(expr, list):
        return [evaluate(item, inputs, env) for item in expr]
    if not isinstance(expr, dict):
        return expr
    op, args = _operator(expr)

    def value(i: int) -> Any:
        return evaluate(args[i], inputs, env)

    if op == "var":
        name = str(args[0])
        if name not in inputs:
            raise RuleError(f"Input {name!r} was not provided")
        return inputs[name]
    if op == "and":
        return all(bool(evaluate(a, inputs, env)) for a in args)
    if op == "or":
        return any(bool(evaluate(a, inputs, env)) for a in args)
    if op in ("!", "not"):
        return not bool(value(0))
    if op in ("==", "!="):
        same = _equal(value(0), value(1))
        return same if op == "==" else not same
    if op in _COMPARE:
        return _COMPARE[op](_number(value(0)), _number(value(1)))
    if op == "in":
        haystack = value(1)
        if not isinstance(haystack, list):
            raise RuleError('"in" needs a list')
        needle = value(0)
        return any(_equal(needle, item) for item in haystack)
    if op == "inList":
        name = args[0]
        if not isinstance(name, str) or name not in env.lists:
            raise RuleError(f"Unknown list {name!r}")
        return str(value(1)) in env.lists[name]
    if op == "countryRisk":
        country = value(0)
        if not isinstance(country, str) or not country.strip():
            raise RuleError("countryRisk needs a country code")
        return env.country_risk.get(country.strip().upper(), "low")
    # sumWindow: the input resolver sums the window when it reads the subject; the rule reads the total.
    total = f"{args[0]}Sum{args[1]}d"
    if total not in inputs:
        raise RuleError(f"Input {total!r} was not provided")
    return inputs[total]


def run_rules(rules: Sequence[Mapping[str, Any]], inputs: Inputs, env: Env = NO_REFERENCE_DATA) -> Result:
    """Evaluate the rules in order; the first that matches decides. Every ruleset ends with a catch-all."""
    trace: list[Trace] = []
    for rule in rules:
        matched = bool(evaluate(rule["when"], inputs, env))
        trace.append(Trace(str(rule["id"]), str(rule["desc"]), matched))
        if matched:
            return Result(str(rule["then"]), str(rule["id"]), str(rule["desc"]), tuple(trace))
    raise RuleError("No rule matched; a ruleset must end with a catch-all rule")


def check_expression(expr: Any) -> None:
    """The expression's structure: known operators and argument counts. No inputs needed."""
    if isinstance(expr, list):
        for item in expr:
            check_expression(item)
        return
    if not isinstance(expr, dict):
        return
    op, args = _operator(expr)
    if op == "var":
        if not isinstance(args[0], str) or not args[0]:
            raise RuleError('"var" needs an input name')
        return
    if op == "inList":
        if not isinstance(args[0], str):
            raise RuleError('"inList" needs a list name first')
        check_expression(args[1])
        return
    if op == "sumWindow":
        if not isinstance(args[0], str) or not isinstance(args[1], int) or isinstance(args[1], bool):
            raise RuleError('"sumWindow" needs a field name and a number of days')
        return
    for arg in args:
        check_expression(arg)


def validate(rules: Any, outcomes: Sequence[str]) -> list[str]:
    """Why a draft cannot be saved, in officers' words (LLD, Version cut); empty when it can."""
    if not isinstance(rules, list) or not rules:
        return ["A ruleset needs at least one rule."]
    errors: list[str] = []
    seen: set[str] = set()
    for i, rule in enumerate(rules, start=1):
        rule = rule if isinstance(rule, dict) else {}
        n, rule_id = f"Rule {i}", rule.get("id")
        if not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id):
            errors.append(f"{n}: the ID must be 2 to 16 capital letters, digits or hyphens.")
        elif rule_id in seen:
            errors.append(f"{n}: the ID {rule_id} is used twice.")
        if isinstance(rule_id, str):
            seen.add(rule_id)
        desc = rule.get("desc")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"{n}: add a description.")
        if rule.get("then") not in outcomes:
            errors.append(f'{n}: the outcome "{rule.get("then") or ""}" is not one of {", ".join(outcomes)}.')
        try:
            check_expression(rule.get("when"))
        except RuleError as exc:
            errors.append(f"{n}: {exc}.")
    last = rules[-1]
    if not isinstance(last, dict) or last.get("when") is not True:
        errors.append("The last rule must be a catch-all (condition true), so every input gets an outcome.")
    return errors
