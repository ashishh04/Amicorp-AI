"""The UC1 validation rules (portal contract, Statements; LLD: POST /v1/statements/{id}/submit).

Pure: no I/O. The requirements-before-save gates S1-S6 run on every read of the header (the portal shows
them live) and again on submit, where any failure is a hard stop. They follow the portal mock's
statementChecks() rule for rule, including its wording.
"""
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from app.core.principal import Role
from app.shared.action_gate import ALLOW, Gate, deny

FIELDS = ("valueDate", "description", "debit", "credit", "balance", "enNumber")
FIELD_LABEL = {
    "valueDate": "value date", "description": "description", "debit": "debit", "credit": "credit",
    "balance": "balance", "enNumber": "EN number",
}
REVIEW_STATES = ("IN_REVIEW", "SUBMITTED")
TOLERANCE = Decimal("0.005")
DEFAULT_THRESHOLD = Decimal("0.70")  # the red band, as in uc1.field-validation v2 (rule F-02)


@dataclass(frozen=True)
class LineFacts:
    line_no: int
    value_date: date
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal | None
    en_number: str | None
    approved: bool


@dataclass(frozen=True)
class Failure:
    message: str
    line_no: int | None = None
    field: str | None = None


@dataclass(frozen=True)
class Check:
    id: str
    desc: str
    failures: tuple[Failure, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class Reference:
    key: Literal["bankId", "accountNo", "entity"]
    label: str
    value: str
    valid: bool
    message: str | None = None


def money(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def business_days_between(start: date, end: date) -> int:
    """Weekdays after `start` up to and including `end` (0 when end is not later): a NAV valued on Wednesday
    and received on Thursday is 1 business day old. Public holidays come with ref.calendar."""
    days, day = 0, start
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5:
            days += 1
    return days


def field_list(fields: Sequence[str]) -> str:
    return ", ".join(FIELD_LABEL[f] for f in fields)


def threshold_text(threshold: Decimal) -> str:
    return f"{float(threshold):g}"


def flagged(confidence: Mapping[str, float], corrected: Collection[str], threshold: Decimal) -> list[str]:
    """Fields below the extraction threshold that no Maker has corrected yet (corrections count as 1)."""
    return [f for f in FIELDS
            if f in confidence and Decimal(str(confidence[f])) < threshold and f not in corrected]


def references(
    refs: Mapping[str, str], *, bank: str, account_no: str, bic_on_file: str | None, entity_name: str | None
) -> list[Reference]:
    bank_id, account, entity = refs.get("bankId", ""), refs.get("accountNo", ""), refs.get("entity", "")
    bic_ok = bic_on_file is None or bic_on_file == bank_id
    return [
        Reference("bankId", "Bank ID (BIC)", bank_id, bic_ok, None if bic_ok else f"Expected {bic_on_file} for {bank}"),
        Reference("accountNo", "Account", account, account == account_no,
                  None if account == account_no else "Does not match the statement account"),
        Reference("entity", "Entity (EN number)", entity, entity_name is not None,
                  entity_name if entity_name is not None else "Not in today’s EN lookup table"),
    ]


def date_failures(period_from: date, period_to: date, lines: Sequence[LineFacts]) -> tuple[Failure, ...]:
    """S1, also the field-validation gate's datesOutsidePeriod input."""
    return tuple(
        Failure(f"Line {line.line_no}: {line.value_date.isoformat()} is outside {period_from.isoformat()} "
                f"to {period_to.isoformat()}", line.line_no, "valueDate")
        for line in lines if not period_from <= line.value_date <= period_to
    )


def balance_failures(opening: Decimal, lines: Sequence[LineFacts]) -> tuple[Failure, ...]:
    """S3, also the field-validation gate's balanceBreaks input. After a break the check carries on from the
    balance the line shows, so one misread amount is reported once, not on every later line."""
    breaks: list[Failure] = []
    previous = opening
    for line in lines:
        expected = previous + (line.credit or 0) - (line.debit or 0)
        if line.balance is None or abs(expected - line.balance) > TOLERANCE:
            reads = "empty" if line.balance is None else money(line.balance)
            breaks.append(Failure(
                f"Line {line.line_no}: {money(previous)} + credit - debit = {money(expected)}, "
                f"but the balance reads {reads}", line.line_no, "balance"))
        previous = line.balance if line.balance is not None else expected
    return tuple(breaks)


def checks(
    *,
    period_from: date,
    period_to: date,
    opening: Decimal,
    closing: Decimal,
    lines: Sequence[LineFacts],
    refs: Sequence[Reference],
    known_en_numbers: Collection[str],
) -> list[Check]:
    sides = tuple(
        Failure(f"Line {line.line_no}: needs exactly one of debit or credit", line.line_no, "debit")
        for line in lines if (line.debit is None) == (line.credit is None)
    )
    net = sum(((line.credit or Decimal(0)) - (line.debit or Decimal(0)) for line in lines), Decimal(0))
    computed = opening + net
    closing_failures = () if abs(computed - closing) <= TOLERANCE else (Failure(
        f"Opening {money(opening)} + movements {money(net)} = {money(computed)}, "
        f"but the closing balance is {money(closing)}"),)

    reference_failures = [Failure(f"{r.label} {r.value or '(empty)'}: {r.message or 'invalid'}")
                          for r in refs if not r.valid]
    for line in lines:
        if not line.en_number:
            reference_failures.append(Failure(f"Line {line.line_no}: EN number missing", line.line_no, "enNumber"))
        elif line.en_number not in known_en_numbers:
            reference_failures.append(Failure(
                f"Line {line.line_no}: {line.en_number} is not in today’s EN lookup table",
                line.line_no, "enNumber"))

    unapproved = tuple(Failure(f"Line {line.line_no} is not approved", line.line_no)
                       for line in lines if not line.approved)
    return [
        Check("S1", "Value dates inside the statement period", date_failures(period_from, period_to, lines)),
        Check("S2", "Each line is a debit or a credit, not both", sides),
        Check("S3", "Running balance: previous balance + credit - debit = balance", balance_failures(opening, lines)),
        Check("S4", "Opening balance + movements = closing balance", closing_failures),
        Check("S5", "Mandatory references valid against the lookup tables", tuple(reference_failures)),
        Check("S6", "Every line approved by a Maker", unapproved),
    ]


def edit_gate(state: str, roles: frozenset[Role], teams: Collection[str], team: str) -> Gate:
    """Only a Maker of the owning team edits, and only while the statement is in review."""
    if state != "IN_REVIEW":
        return deny(409, "The statement was submitted and is read only.")
    if Role.MAKER not in roles:
        return deny(403, "Only a Maker can correct, approve and submit lines.")
    if team not in teams:
        return deny(403, f"Only Makers in the {team} team can edit it.")
    return ALLOW


def approve_gate(edit: Gate, approved: bool, red: Sequence[str]) -> Gate:
    """The line's approve hint: the same rule approve_line enforces."""
    if approved:
        return deny(409, "Already approved.")
    if not edit.allowed:
        return edit
    if red:
        return deny(422, f"Correct the flagged field first: {field_list(red)}.")
    return ALLOW
