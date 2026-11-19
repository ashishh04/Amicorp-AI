"""A deterministic stand-in for the extraction service, for local work.

Every bank statement "extracts" to the same 12-line statement for the month before it was received,
modelled on the portal mock's HSBC example, so the validation workspace has real work in it: three red
fields (below the 0.70 threshold), three amber ones, a debit misread as 1,850.00 instead of 1,250.00 (a
running-balance break and a closing-balance gap), a value date outside the period, a missing EN number
and one that is not in the lookup table. NAV statements: see NAV_FUNDS below.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.modules.extraction.ports import ExtractedLine, ExtractedNav, ExtractedStatement, ExtractionRequest

MODEL_ID = "fake-local-ocr"
THRESHOLD = Decimal("0.70")
OK = {"valueDate": 0.99, "description": 0.97, "debit": 0.98, "credit": 0.98, "balance": 0.97, "enNumber": 0.95}
ENTITY = "EN-20417"

# (day of month, description, debit, credit, balance, EN number, low-confidence fields)
_LINES: list[tuple[int, str, str | None, str | None, str, str | None, dict[str, float]]] = [
    (2, "Inward TT ACME Holdings Ltd INV-2209", None, "48000.00", "173430.55", ENTITY, {}),
    (3, "TT charges", "25.00", None, "173405.55", ENTITY, {}),
    (5, "Outward TT Blue Harbour Trading", "12500.00", None, "160905.55", ENTITY, {}),
    (8, "Management fee Amicorp HK Q3", "3750.00", None, "157155.55", ENTITY, {"description": 0.88}),
    (11, "Inward TT Lumen Capital SPC", None, "15250.00", "172405.55", None, {"enNumber": 0.0}),
    (15, "Outward TT Kowloon Logistics Ltd", "1850.00", None, "171155.55", ENTITY, {"debit": 0.58}),
    (18, "Credit interest", None, "112.40", "171267.95", ENTITY, {}),
    (21, "Outward TT Meridian Legal LLP", "8400.00", None, "162867.95", "EN-20471", {"enNumber": 0.74}),
    (-23, "FX conversion EUR to USD", None, "20000.00", "182867.95", ENTITY, {"valueDate": 0.64}),
    (26, "Outward TT Harbour Audit & Tax", "2975.00", None, "179892.95", ENTITY, {}),
    (29, "Card settlemnt VISA *4471", "318.60", None, "179574.35", ENTITY, {"description": 0.81}),
    (30, "Monthly account fee", "45.00", None, "179529.35", ENTITY, {}),
]


def _money(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _business_days_before(day: date, n: int) -> date:
    while n > 0:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day


# NAV statements: a fund from ref.fund_template (named in the object key, else picked by the key's length),
# valued the business day before it arrives. A keyword in the object key picks the exception: STALE (valued 5
# business days earlier), JUMP (NAV up 6.5 %, beyond every seeded fund's tolerance) or SHARES (the register
# differs from the shares in issue). Anything else passes nav.checks.
NAV_FUNDS = (
    ("MGF", "Meridian Growth Fund", "A"), ("MIF", "Meridian Income Fund", "A"), ("AFS", "Ardent Fund SPC", "A"),
)


def _nav(request: ExtractionRequest) -> ExtractedNav:
    key = request.object_key.upper()
    fund_code, fund_name, share_class = next((f for f in NAV_FUNDS if f[0] in key),
                                             NAV_FUNDS[len(key) % len(NAV_FUNDS)])
    received = request.received_at.date()
    valuation = _business_days_before(received, 5 if "STALE" in key else 1)
    previous = Decimal("101.340000")
    nav = (previous * (Decimal("1.065") if "JUMP" in key else Decimal("1.012"))).quantize(Decimal("0.000001"))
    shares = Decimal("1250000.0000")
    register = shares - Decimal("1500") if "SHARES" in key else shares
    return ExtractedNav(
        model_id=MODEL_ID, pages=1, fund_code=fund_code, fund_name=fund_name, share_class=share_class,
        currency="USD", valuation_date=valuation, nav_per_share=nav, previous_nav_per_share=previous,
        shares_in_issue=shares, register_shares=register, total_nav=(nav * shares).quantize(Decimal("0.01")),
    )


class FakeExtractor:
    async def extract(self, request: ExtractionRequest) -> ExtractedStatement | ExtractedNav:
        if request.profile == "nav-statement":
            return _nav(request)
        period_to = request.received_at.date().replace(day=1) - timedelta(days=1)
        period_from = period_to.replace(day=1)
        last_day = calendar.monthrange(period_to.year, period_to.month)[1]
        next_month = period_to + timedelta(days=1)

        lines = []
        for i, (day, description, debit, credit, balance, en_number, low) in enumerate(_LINES):
            # A negative day falls in the next month: the "misread" date outside the period.
            value_date = next_month.replace(day=-day) if day < 0 else date(period_to.year, period_to.month,
                                                                            min(day, last_day))
            if description == "Credit interest":
                description = f"Credit interest {period_to:%B}"
            lines.append(ExtractedLine(
                line_no=i + 1, value_date=value_date, description=description, debit=_money(debit),
                credit=_money(credit), balance=_money(balance), en_number=en_number, confidence={**OK, **low},
                box={"page": 1 if i < 7 else 2, "top": 30 + (i % 7) * 9, "height": 6},
            ))
        return ExtractedStatement(
            model_id=MODEL_ID, threshold=THRESHOLD, bank="HSBC Hong Kong", account_no="848-123456-838",
            account_name="Lumen Capital SPC - Segregated Portfolio 2", currency="USD", period_from=period_from,
            period_to=period_to, opening_balance=Decimal("125430.55"), closing_balance=Decimal("179529.35"),
            pages=2, references={"bankId": "HSBCHKHHHKH", "accountNo": "848-123456-838", "entity": ENTITY},
            lines=lines,
        )
