"""The UC1 workspace rules on the local extractor's statement: what fails, and what fixes it."""
import asyncio
import dataclasses
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.principal import Role
from app.integrations.extractor.fake import FakeExtractor
from app.modules.extraction.ports import ExtractedStatement, ExtractionRequest
from app.modules.statements import domain

KNOWN_EN = {"EN-20415", "EN-20416", "EN-20417", "EN-20418"}


def extracted() -> ExtractedStatement:
    request = ExtractionRequest(uuid.uuid4(), "raw-docs/uc1/hsbc.pdf", "bank-statement",
                                datetime(2026, 10, 28, 3, 0, tzinfo=UTC))
    return asyncio.run(FakeExtractor().extract(request))


def facts(statement: ExtractedStatement, **changes: dict) -> list[domain.LineFacts]:
    lines = []
    for x in statement.lines:
        fact = domain.LineFacts(x.line_no, x.value_date, x.debit, x.credit, x.balance, x.en_number, approved=False)
        lines.append(dataclasses.replace(fact, **changes.get(str(x.line_no), {})))
    return lines


def run_checks(statement: ExtractedStatement, lines: list[domain.LineFacts]) -> dict[str, domain.Check]:
    refs = domain.references(statement.references, bank=statement.bank, account_no=statement.account_no,
                             bic_on_file="HSBCHKHHHKH", entity_name="Lumen Capital SPC - Segregated Portfolio 2")
    checks = domain.checks(period_from=statement.period_from, period_to=statement.period_to,
                           opening=statement.opening_balance, closing=statement.closing_balance, lines=lines,
                           refs=refs, known_en_numbers=KNOWN_EN)
    return {c.id: c for c in checks}


def test_the_extracted_statement_fails_where_the_mock_says_it_should():
    statement = extracted()
    assert (statement.period_from, statement.period_to) == (date(2026, 9, 1), date(2026, 9, 30))
    checks = run_checks(statement, facts(statement))
    assert [f.line_no for f in checks["S1"].failures] == [9]
    assert checks["S2"].passed
    assert [f.line_no for f in checks["S3"].failures] == [6]  # one misread debit is reported once
    assert checks["S3"].failures[0].message == (
        "Line 6: 172,405.55 + credit - debit = 170,555.55, but the balance reads 171,155.55")
    assert not checks["S4"].passed
    assert [f.line_no for f in checks["S5"].failures] == [5, 8]
    assert len(checks["S6"].failures) == 12


def test_the_maker_s_corrections_make_every_gate_pass():
    statement = extracted()
    fixed = {"5": {"en_number": "EN-20417"}, "6": {"debit": Decimal("1250.00")},
             "8": {"en_number": "EN-20417"}, "9": {"value_date": date(2026, 9, 23)}}
    lines = [dataclasses.replace(f, approved=True) for f in facts(statement, **fixed)]
    assert all(c.passed for c in run_checks(statement, lines).values())


def test_flagged_fields_are_the_red_ones_until_corrected():
    lines = {x.line_no: x for x in extracted().lines}
    threshold = Decimal("0.70")
    assert domain.flagged(lines[6].confidence, [], threshold) == ["debit"]
    assert domain.flagged(lines[4].confidence, [], threshold) == []  # amber (0.88) is not flagged
    assert domain.flagged(lines[6].confidence, ["debit"], threshold) == []
    assert domain.flagged(lines[5].confidence, [], threshold) == ["enNumber"]


def test_references_follow_the_lookup_tables():
    refs = domain.references({"bankId": "HSBCHKHHHKX", "accountNo": "1", "entity": "EN-9"}, bank="HSBC Hong Kong",
                             account_no="848", bic_on_file="HSBCHKHHHKH", entity_name=None)
    assert [(r.key, r.valid) for r in refs] == [("bankId", False), ("accountNo", False), ("entity", False)]
    assert refs[0].message == "Expected HSBCHKHHHKH for HSBC Hong Kong"


def test_only_a_maker_of_the_owning_team_edits_while_in_review():
    maker = frozenset({Role.MAKER})
    assert domain.edit_gate("IN_REVIEW", maker, ("Operations",), "Operations").allowed
    assert domain.edit_gate("SUBMITTED", maker, ("Operations",), "Operations").status == 409
    assert domain.edit_gate("IN_REVIEW", frozenset({Role.CHECKER}), ("Operations",), "Operations").status == 403
    assert domain.edit_gate("IN_REVIEW", maker, ("Fund accounting",), "Operations").reason == (
        "Only Makers in the Operations team can edit it.")


def test_the_approve_hint_explains_why_not():
    allowed = domain.edit_gate("IN_REVIEW", frozenset({Role.MAKER}), ("Operations",), "Operations")
    assert domain.approve_gate(allowed, True, []).reason == "Already approved."
    assert domain.approve_gate(allowed, False, ["debit"]).reason == "Correct the flagged field first: debit."
    assert domain.approve_gate(allowed, False, []).allowed
