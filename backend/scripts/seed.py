"""Load the local reference data: the sample officers, today's EN numbers, the bank BICs, the AML lists and
country risk, the NAV fund templates, and the rulesets of UC1, UC2 and UC3.

    python -m scripts.seed

Local and test only, and it refuses anything else: DEV, NPR and PRD read people from Entra ID and lookups
from 5 Series, and rulesets reach them through change control. Safe to run again: rows are upserted, and a
ruleset version that exists is never rewritten (approved versions are immutable).
"""
import hashlib
import sys
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.core.config import LOCAL_ENVIRONMENTS, get_settings
from app.modules.identity.personas import PERSONAS, persona_id
from app.shared.audit import canonical_json

# The daily EN-number lookup table (frontend mock-data EN_NUMBERS).
EN_NUMBERS = [
    ("EN-20415", "Lumen Capital SPC"),
    ("EN-20416", "Lumen Capital SPC - Segregated Portfolio 1"),
    ("EN-20417", "Lumen Capital SPC - Segregated Portfolio 2"),
    ("EN-20418", "Lumen Capital SPC - Segregated Portfolio 3"),
    ("EN-31002", "Harbour Trust Ltd"),
    ("EN-31007", "Harbour Trust Ltd - Unit 12A"),
    ("EN-40188", "Seabright Holdings BV"),
    ("EN-55120", "Meridian Growth Fund"),
    ("EN-55121", "Meridian Income Fund"),
    ("EN-61002", "Ardent Fund SPC"),
]
BANKS = [("HSBC Hong Kong", "HSBCHKHHHKH"), ("DBS Bank (Hong Kong)", "DHBKHKHHXXX")]
# What the AML rules read (the portal mock's mock-rules.ts lists): the exclusion list, and country risk.
NAMED_LISTS = [
    ("exclusion", "CP-00001-INTERNAL", "Internal transfers"),
    ("exclusion", "CP-00002-INTERNAL", "Internal transfers (second account)"),
    ("exclusion", "CP-00017-PAYROLL", "Payroll"),
]
COUNTRY_RISK = [(c, "high") for c in ("IR", "KP", "MM", "SY", "YE", "AF")] + \
               [(c, "medium") for c in ("AE", "PA", "TR", "NG")]
FUND_TEMPLATES = [  # (fund code, share class, fund, tolerated NAV move in %)
    ("MGF", "A", "Meridian Growth Fund", "3.000"),
    ("MIF", "A", "Meridian Income Fund", "2.000"),
    ("AFS", "A", "Ardent Fund SPC", "5.000"),
]


def field_validation_rules(red_band: str) -> list[dict[str, Any]]:
    """uc1.field-validation as the portal mock defines it; versions differ only in the red band."""
    return [
        {"id": "F-01", "desc": "No pages extracted", "when": {"<": [{"var": "pages"}, 1]}, "then": "reject"},
        {"id": "F-02", "desc": f"A field below {red_band} confidence",
         "when": {"<": [{"var": "minConfidence"}, float(red_band)]}, "then": "needs-review"},
        {"id": "F-03", "desc": "Running balance breaks", "when": {">": [{"var": "balanceBreaks"}, 0]},
         "then": "needs-review"},
        {"id": "F-04", "desc": "Value date outside the statement period",
         "when": {">": [{"var": "datesOutsidePeriod"}, 0]}, "then": "needs-review"},
        {"id": "F-99", "desc": "All field checks pass", "when": True, "then": "pass"},
    ]


def _v(version: int, status: str, rules: list[dict[str, Any]], effective: str | None, drafter: str, drafted: str,
       approver: str | None, approved: str | None, note: str) -> dict[str, Any]:
    return {"version": version, "status": status, "rules": rules, "effective": effective, "drafter": drafter,
            "drafted": drafted, "approver": approver, "approved": approved, "note": note}


def _rule(rule_id: str, desc: str, when: Any, then: str) -> dict[str, Any]:
    return {"id": rule_id, "desc": desc, "when": when, "then": then}


FIELD_VALIDATION: dict[str, Any] = {
    "key": "uc1.field-validation",
    "name": "Bank statement field validation",
    "owner_team": "Operations",
    "use_case": "UC1",
    "description": "Runs after extraction. Low confidence becomes a human-reviewed exception, never a silent error.",
    "outcomes": ["pass", "needs-review", "reject"],
    "default_outcome": "needs-review",  # fail closed: a person reviews the statement
    "sample_inputs": {"pages": 2, "minConfidence": 0.58, "balanceBreaks": 1, "datesOutsidePeriod": 1},
    "regression_cases": [
        {"name": "Clean extraction", "expected": "pass",
         "inputs": {"pages": 2, "minConfidence": 0.96, "balanceBreaks": 0, "datesOutsidePeriod": 0}},
        {"name": "Low confidence field", "expected": "needs-review",
         "inputs": {"pages": 2, "minConfidence": 0.61, "balanceBreaks": 0, "datesOutsidePeriod": 0}},
        {"name": "Empty document", "expected": "reject",
         "inputs": {"pages": 0, "minConfidence": 0, "balanceBreaks": 0, "datesOutsidePeriod": 0}},
    ],
    "versions": [
        _v(2, "approved", field_validation_rules("0.70"), "2026-09-10T00:00:00+00:00", "u-grace",
           "2026-09-04T03:00:00+00:00", "u-priya", "2026-09-09T02:00:00+00:00", "Red band lowered to 0.70."),
        _v(3, "draft", field_validation_rules("0.75"), None, "u-grace", "2026-10-27T03:00:00+00:00", None, None,
           "Raises the red band to 0.75 for scanned statements (Operations request CR-121)."),
    ],
}

_G1 = [
    _rule("G1-01", "Unusual-transaction flag always monitored", {"==": [{"var": "unusualFlag"}, True]}, "monitor"),
    _rule("G1-02", "Exclusion list (e.g. internal transfers)", {"inList": ["exclusion", {"var": "counterpartyId"}]},
          "below-threshold"),
    _rule("G1-03", "Single payment at or above USD 10,000", {">=": [{"var": "amountUsd"}, 10000]}, "monitor"),
    _rule("G1-04", "Related payments aggregate to USD 10,000 within 7 days",
          {">=": [{"sumWindow": ["amountUsd", 7, "entityKey"]}, 10000]}, "monitor"),
]
_G1_COUNTRY = _rule("G1-05", "Local country requirement: high-risk beneficiary country",
                    {"==": [{"countryRisk": [{"var": "beneficiaryCtry"}]}, "high"]}, "monitor")
_G1_STRUCTURING = _rule("G1-06", "Structuring: 3 or more payments of USD 9,000-9,999 within 7 days",
                        {">=": [{"var": "nearThresholdCount7d"}, 3]}, "monitor")
_G1_LAST = _rule("G1-99", "Below every threshold", True, "below-threshold")
_G1_BASE = {"unusualFlag": False, "counterpartyId": "CP-88120", "amountUsd": 7200, "amountUsdSum7d": 7200,
            "beneficiaryCtry": "SG", "nearThresholdCount7d": 0}

GATE1: dict[str, Any] = {
    "key": "aml.gate1-entry", "name": "AML gate 1: entry thresholds", "owner_team": "Compliance", "use_case": "UC2",
    "description": "Decides whether a payment enters AML monitoring at all. Payments below every threshold are "
                   "filed without a card.",
    "outcomes": ["monitor", "below-threshold"], "default_outcome": "monitor",
    "sample_inputs": {**_G1_BASE, "amountUsdSum7d": 12850},
    "regression_cases": [
        {"name": "Large single payment", "expected": "monitor",
         "inputs": {**_G1_BASE, "amountUsd": 25000, "amountUsdSum7d": 25000}},
        {"name": "Internal transfer is excluded", "expected": "below-threshold",
         "inputs": {**_G1_BASE, "counterpartyId": "CP-00001-INTERNAL", "amountUsd": 50000, "amountUsdSum7d": 50000}},
        {"name": "Split payments over 7 days", "expected": "monitor",
         "inputs": {**_G1_BASE, "amountUsd": 4000, "amountUsdSum7d": 12500}},
        {"name": "High-risk country, small amount", "expected": "monitor",
         "inputs": {**_G1_BASE, "amountUsd": 900, "amountUsdSum7d": 900, "beneficiaryCtry": "IR"}},
        {"name": "Ordinary small payment", "expected": "below-threshold", "inputs": dict(_G1_BASE)},
        {"name": "Structuring pattern (needs v4)", "expected": "monitor",
         "inputs": {**_G1_BASE, "amountUsd": 9500, "amountUsdSum7d": 9500, "nearThresholdCount7d": 3}},
    ],
    "versions": [
        _v(4, "draft", [*_G1, _G1_COUNTRY, _G1_STRUCTURING, _G1_LAST], None, "u-grace", "2026-10-27T05:00:00+00:00",
           None, None, "Adds G1-06 for structuring just below the threshold (Compliance request CR-118)."),
        _v(3, "approved", [*_G1, _G1_COUNTRY, _G1_LAST], "2026-09-01T00:00:00+00:00", "u-grace",
           "2026-08-25T03:00:00+00:00", "u-daniel", "2026-08-29T02:00:00+00:00",
           "Adds the local-country requirement G1-05."),
        _v(2, "superseded", [*_G1, _G1_LAST], "2026-06-15T00:00:00+00:00", "u-grace", "2026-06-08T03:00:00+00:00",
           "u-daniel", "2026-06-12T02:00:00+00:00", "Adds the 7-day aggregation rule."),
    ],
}

_G2_BASE = {"profileVerdict": "match", "amountUsd": 48000, "profileMaxAmountUsd": 60000, "countryInProfile": True}
GATE2: dict[str, Any] = {
    "key": "aml.gate2-profile", "name": "AML gate 2: client profile", "owner_team": "Compliance", "use_case": "UC2",
    "description": "The model reads the payment against the client's CARE profile. An uncertain reading counts as "
                   "a mismatch, so a doubt always reaches Compliance.",
    "outcomes": ["match", "mismatch"], "default_outcome": "mismatch",
    "sample_inputs": dict(_G2_BASE),
    "regression_cases": [
        {"name": "Fits the profile", "expected": "match", "inputs": dict(_G2_BASE)},
        {"name": "The model is not sure", "expected": "mismatch",
         "inputs": {**_G2_BASE, "profileVerdict": "uncertain"}},
        {"name": "The model sees a mismatch", "expected": "mismatch",
         "inputs": {**_G2_BASE, "profileVerdict": "mismatch"}},
        {"name": "Above the profile's largest payment", "expected": "mismatch",
         "inputs": {**_G2_BASE, "amountUsd": 75000}},
        {"name": "Country not in the profile", "expected": "mismatch",
         "inputs": {**_G2_BASE, "countryInProfile": False}},
    ],
    "versions": [
        _v(1, "approved", [
            _rule("G2-01", "The model could not tell: treated as a mismatch",
                  {"==": [{"var": "profileVerdict"}, "uncertain"]}, "mismatch"),
            _rule("G2-02", "The model found the payment outside the profile",
                  {"==": [{"var": "profileVerdict"}, "mismatch"]}, "mismatch"),
            _rule("G2-03", "Amount above the largest payment the profile expects",
                  {">": [{"var": "amountUsd"}, {"var": "profileMaxAmountUsd"}]}, "mismatch"),
            _rule("G2-04", "Beneficiary country not in the client's profile",
                  {"==": [{"var": "countryInProfile"}, False]}, "mismatch"),
            _rule("G2-99", "The payment fits the client's profile", True, "match"),
        ], "2026-09-01T00:00:00+00:00", "u-grace", "2026-08-25T04:00:00+00:00", "u-daniel",
           "2026-08-29T03:00:00+00:00", "First version: the model reads, the rules decide."),
    ],
}

_G3_BASE = {"screeningHit": False, "screeningScore": 0, "riskScore": 35, "pepFlag": False}
GATE3: dict[str, Any] = {
    "key": "aml.gate3-risk", "name": "AML gate 3: risk score and live screening", "owner_team": "Compliance",
    "use_case": "UC2",
    "description": "Screens the counterparty live. A strong screening hit goes to the MLRO (alert); every other "
                   "monitored payment goes to a Compliance decision (clear).",
    "outcomes": ["clear", "alert"], "default_outcome": "alert",
    "sample_inputs": {**_G3_BASE, "riskScore": 64},
    "regression_cases": [
        {"name": "Sanctions hit goes to the MLRO", "expected": "alert",
         "inputs": {**_G3_BASE, "screeningHit": True, "screeningScore": 92}},
        {"name": "A weak hit stays with Compliance", "expected": "clear",
         "inputs": {**_G3_BASE, "screeningHit": True, "screeningScore": 60}},
        {"name": "A PEP stays with Compliance", "expected": "clear", "inputs": {**_G3_BASE, "pepFlag": True}},
        {"name": "No hit", "expected": "clear", "inputs": dict(_G3_BASE)},
    ],
    "versions": [
        _v(1, "approved", [
            _rule("G3-01", "Screening hit with score 85 or more: the MLRO decides",
                  {"and": [{"==": [{"var": "screeningHit"}, True]}, {">=": [{"var": "screeningScore"}, 85]}]},
                  "alert"),
            _rule("G3-99", "No strong screening hit: Compliance decides", True, "clear"),
        ], "2026-09-01T00:00:00+00:00", "u-grace", "2026-08-25T05:00:00+00:00", "u-daniel",
           "2026-08-29T04:00:00+00:00", "Outcomes as in the LLD: clear (Compliance card) or alert (MLRO card)."),
    ],
}

_NAV_BASE = {"valuationAgeBusinessDays": 0, "navMovePctAbs": 1.2, "tolerancePct": 3, "sharesReconciled": True}
NAV_CHECKS: dict[str, Any] = {
    "key": "nav.checks", "name": "NAV statement checks", "owner_team": "Fund accounting", "use_case": "UC3",
    "description": "Runs after extraction: valuation date, NAV movement against the fund's tolerance, and the share "
                   "register. Any failure is an exception card.",
    "outcomes": ["pass", "exception"], "default_outcome": "exception",
    "sample_inputs": {**_NAV_BASE, "navMovePctAbs": 4.8},
    "regression_cases": [
        {"name": "Within tolerance", "expected": "pass", "inputs": dict(_NAV_BASE)},
        {"name": "Stale valuation date", "expected": "exception",
         "inputs": {**_NAV_BASE, "valuationAgeBusinessDays": 3}},
        {"name": "Move beyond tolerance", "expected": "exception", "inputs": {**_NAV_BASE, "navMovePctAbs": 4.8}},
        {"name": "Register does not reconcile", "expected": "exception",
         "inputs": {**_NAV_BASE, "sharesReconciled": False}},
    ],
    "versions": [
        _v(1, "approved", [
            _rule("N-01", "Valuation date more than 1 business day old",
                  {">": [{"var": "valuationAgeBusinessDays"}, 1]}, "exception"),
            _rule("N-02", "NAV per share moved more than the fund tolerance",
                  {">": [{"var": "navMovePctAbs"}, {"var": "tolerancePct"}]}, "exception"),
            _rule("N-03", "Shares in issue do not reconcile to the register",
                  {"==": [{"var": "sharesReconciled"}, False]}, "exception"),
            _rule("N-99", "All NAV checks pass", True, "pass"),
        ], "2026-09-15T00:00:00+00:00", "u-grace", "2026-09-10T03:00:00+00:00", "u-lars",
           "2026-09-12T02:00:00+00:00", "First version; tolerances per fund template."),
    ],
}

RULESETS = [FIELD_VALIDATION, GATE1, GATE2, GATE3, NAV_CHECKS]


def _at(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def seed_rulesets(cur: psycopg.Cursor[Any], now: datetime) -> None:
    for rs in RULESETS:
        cur.execute(
            """INSERT INTO rules.ruleset (ruleset_key, name, owner_team, use_case, description, outcomes,
                                          default_outcome, sample_inputs, regression_cases, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (ruleset_key) DO UPDATE SET name = EXCLUDED.name, owner_team = EXCLUDED.owner_team,
                   description = EXCLUDED.description, outcomes = EXCLUDED.outcomes,
                   default_outcome = EXCLUDED.default_outcome, sample_inputs = EXCLUDED.sample_inputs,
                   regression_cases = EXCLUDED.regression_cases""",
            (rs["key"], rs["name"], rs["owner_team"], rs["use_case"], rs["description"], rs["outcomes"],
             rs["default_outcome"], Jsonb(rs["sample_inputs"]), Jsonb(rs["regression_cases"]), now),
        )
        for v in rs["versions"]:
            cur.execute(
                """INSERT INTO rules.ruleset_version (ruleset_key, version, status, rules, body_sha256, effective_from,
                                                      drafted_by, drafted_at, approved_by, approved_at, note)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (ruleset_key, version) DO NOTHING""",
                (rs["key"], v["version"], v["status"], Jsonb(v["rules"]),
                 hashlib.sha256(canonical_json(v["rules"]).encode()).digest(), _at(v["effective"]),
                 persona_id(v["drafter"]), _at(v["drafted"]), persona_id(v["approver"]) if v["approver"] else None,
                 _at(v["approved"]), v["note"]),
            )


def reset_rulesets(conninfo: str) -> None:
    """Back to the seeded rulesets, for tests that draft and approve versions."""
    with psycopg.connect(conninfo) as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute("TRUNCATE rules.gate_run, rules.ruleset_version, rules.ruleset")
        seed_rulesets(cur, datetime.now(UTC))


def seed(conninfo: str) -> dict[str, int]:
    now = datetime.now(UTC)
    with psycopg.connect(conninfo) as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO ref.app_user (user_id, display_name, email, calendar, roles, teams, data_scope, active,
                                         updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s)
               ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name, email = EXCLUDED.email,
                   calendar = EXCLUDED.calendar, roles = EXCLUDED.roles, teams = EXCLUDED.teams,
                   data_scope = EXCLUDED.data_scope, active = true, updated_at = EXCLUDED.updated_at""",
            [(p.user_id, p.display_name, p.email, p.calendar, list(p.roles), list(p.teams), list(p.data_scope), now)
             for p in PERSONAS],
        )
        cur.executemany(
            """INSERT INTO ref.en_number (code, name, updated_at) VALUES (%s, %s, %s)
               ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, updated_at = EXCLUDED.updated_at""",
            [(code, name, now) for code, name in EN_NUMBERS],
        )
        cur.executemany(
            "INSERT INTO ref.bank (name, bic) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET bic = EXCLUDED.bic",
            BANKS,
        )
        cur.executemany(
            """INSERT INTO ref.named_list (list_name, value, label) VALUES (%s, %s, %s)
               ON CONFLICT (list_name, value) DO UPDATE SET label = EXCLUDED.label""", NAMED_LISTS,
        )
        cur.executemany(
            """INSERT INTO ref.country_risk (country, risk) VALUES (%s, %s)
               ON CONFLICT (country) DO UPDATE SET risk = EXCLUDED.risk""", COUNTRY_RISK,
        )
        cur.executemany(
            """INSERT INTO ref.fund_template (fund_code, share_class, fund_name, tolerance_pct) VALUES (%s, %s, %s, %s)
               ON CONFLICT (fund_code, share_class) DO UPDATE SET fund_name = EXCLUDED.fund_name,
                   tolerance_pct = EXCLUDED.tolerance_pct""", FUND_TEMPLATES,
        )
        seed_rulesets(cur, now)
    return {"users": len(PERSONAS), "enNumbers": len(EN_NUMBERS), "banks": len(BANKS), "rulesets": len(RULESETS)}


def main() -> None:
    settings = get_settings()
    if settings.environment not in LOCAL_ENVIRONMENTS:
        sys.exit(f"scripts.seed runs only when ENVIRONMENT is local or test, not {settings.environment}.")
    url = settings.database_url.get_secret_value().replace("postgresql+psycopg://", "postgresql://", 1)
    counts = seed(url)
    print("Seeded " + ", ".join(f"{n} {what}" for what, n in counts.items()))  # noqa: T201 - a CLI


if __name__ == "__main__":
    main()
