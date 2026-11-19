"""A synthetic data lake for local work. All entities and values are invented; DEV uses synthetic data only.

The same candidates come back on every scan, which shows the dedupe at work: the first scan creates the
cards, and later scans find nothing new until a card is closed and the problem is gone.
"""
from datetime import date

from app.modules.scans.ports import Candidate

_UC4_DISCREPANCIES = [
    Candidate("D-01", "ENT-10017", "Registered address differs between CARE and 5 Series", {
        "field": "registeredAddress", "care": "12 Harbour Road, Wan Chai", "fiveSeries": "12 Harbor Rd, Wanchai",
    }),
    Candidate("D-04", "ENT-10342", "Director listed in CARE is missing in 5 Series", {
        "field": "directors", "care": ["K. Lam", "R. Osei"], "fiveSeries": ["K. Lam"],
    }),
    Candidate("D-07", "CLT-20456", "KYC review date is in the past", {
        "field": "kycReviewDue", "care": "2026-08-31", "today": "2026-10-28",
    }),
]

_UC5_VIOLATIONS = [
    Candidate("P-12", "ENT-11008", "Beneficial owner's passport has expired", {
        "document": "passport", "expiredOn": "2026-09-30",
    }, policy_id="POL-AML-007"),
    Candidate("P-03", "FND-30021", "NAV not published for 3 business days", {
        "lastPublished": "2026-10-23", "businessDaysLate": 3,
    }, policy_id="POL-FND-002"),
]


class FakeScanSource:
    async def candidates(
        self, ruleset: str, layer: str, batch_date: date | None, scan_window: str | None
    ) -> list[Candidate]:
        if ruleset == "uc4.discrepancy-catalogue":
            return list(_UC4_DISCREPANCIES)
        if ruleset == "uc5.violation-catalogue":
            return list(_UC5_VIOLATIONS)
        return []
