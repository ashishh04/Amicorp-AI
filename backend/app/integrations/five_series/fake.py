"""A deterministic stand-in for 5 Series, for local work and the demo.

A keyword in the transaction ID picks the scenario, so each UC2 path can be shown on purpose:

| Keyword    | Payment                                         | Path through the gates                        |
|------------|-------------------------------------------------|-----------------------------------------------|
| LARGE      | USD 48,000 to Singapore, within the profile     | gate 1 monitor, gate 2 match, gate 3 clear    |
| PROFILE    | USD 15,000 to the UAE, outside the profile      | gate 2 mismatch: profile-update card          |
| SANCTION   | USD 12,000 to Kowloon Trading Ltd               | gate 3 screening hit: MLRO escalation         |
| SCREENDOWN | USD 20,000; the screening provider is down      | gate 3 fails closed: gate-exception card      |
| UNSURE     | USD 18,000, purpose unclear                     | gate 2 uncertain, so mismatch                 |
| PEP        | USD 30,000 for a client who is a PEP            | gate 3 clear, the PEP flag shows on the card  |
| HIGHRISK   | USD 3,000 to Iran                               | gate 1 monitor (high-risk country)            |
| UNUSUAL    | USD 2,500 flagged unusual by 5 Series           | gate 1 monitor (unusual flag)                 |
| INTERNAL   | USD 25,000 to an internal counterparty          | gate 1 below threshold (exclusion list)       |
| (none)     | USD 1,500 to 8,499 to a supplier                | gate 1 below threshold: filed                 |

No payment request ever arrives on its own (new_requests is empty): locally, UC2 starts from the webhook.
"""
import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import structlog

from app.modules.transaction_monitoring.ports import Payment

log = structlog.get_logger()

# keyword: (amount USD, beneficiary country, counterparty ID, counterparty, client, purpose, unusual flag)
SCENARIOS: dict[str, tuple[str, str, str, str, str, str, bool]] = {
    "SCREENDOWN": ("20000.00", "SG", "CP-30414", "Unscreenable Ltd", "CL-1001", "Supplier invoice", False),
    "SANCTION": ("12000.00", "HK", "CP-66120", "Kowloon Trading Ltd", "CL-1001", "Trade settlement", False),
    "PROFILE": ("15000.00", "AE", "CP-51772", "Gulf Logistics FZE", "CL-1001", "Freight services", False),
    "UNSURE": ("18000.00", "SG", "CP-30413", "Orchid Consulting Pte Ltd", "CL-1001", "Consultancy (unclear)", False),
    "LARGE": ("48000.00", "SG", "CP-30411", "Straits Asset Management Pte Ltd", "CL-1001",
              "Subscription to fund units", False),
    "PEP": ("30000.00", "NL", "CP-80211", "Rotterdam Holdings BV", "CL-3003", "Dividend", False),
    "HIGHRISK": ("3000.00", "IR", "CP-70315", "Tehran Supplies Co", "CL-1001", "Supplier invoice", False),
    "UNUSUAL": ("2500.00", "SG", "CP-30412", "Marina Advisory Pte Ltd", "CL-1001", "Advisory fee", True),
    "INTERNAL": ("25000.00", "HK", "CP-00001-INTERNAL", "Lumen Capital SPC (internal)", "CL-1001",
                 "Internal transfer", False),
}
CLIENT_NAMES = {"CL-1001": "Lumen Capital SPC", "CL-2002": "Harbour Trust Ltd", "CL-3003": "Seabright Holdings BV"}


def _digest(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


class FakePayments:
    async def payment(self, transaction_id: str) -> Payment | None:
        upper = transaction_id.upper()
        scenario = next((s for keyword, s in SCENARIOS.items() if keyword in upper), None)
        if scenario is None:
            h = _digest(transaction_id)
            scenario = (f"{1500 + h % 7000}.00", ("SG", "HK", "GB")[h % 3], f"CP-1{h % 10000:04d}",
                        f"Supplier {h % 1000} Ltd", "CL-1001", "Supplier invoice", False)
        amount, country, counterparty_id, counterparty, client, purpose, unusual = scenario
        return Payment(
            # Related payments: the same client paying the same counterparty (gate 1's 7-day window).
            transaction_id=transaction_id, client_id=client, client_name=CLIENT_NAMES[client],
            entity_key=f"{client}:{counterparty_id}",
            amount=Decimal(amount), currency="USD", amount_usd=Decimal(amount), counterparty_id=counterparty_id,
            counterparty_name=counterparty, beneficiary_ctry=country, purpose=purpose, unusual_flag=unusual,
            value_date=datetime.now(UTC).date(),
        )

    async def new_requests(self) -> list[tuple[str, str]]:
        return []

    async def hold(self, transaction_id: str) -> str:
        return self._logged("hold", transaction_id)

    async def release(self, transaction_id: str, hold_reference: str | None) -> str:
        return self._logged("release", transaction_id)

    async def freeze(self, transaction_id: str, hold_reference: str | None) -> str:
        return self._logged("freeze", transaction_id)

    @staticmethod
    def _logged(action: str, transaction_id: str) -> str:
        reference = f"5S-{action.upper()}-{_digest(action + transaction_id):08x}"
        log.info("five_series.logged_only", action=action, transaction_id=transaction_id, reference=reference)
        return reference
