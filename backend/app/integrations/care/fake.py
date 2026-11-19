"""Sample client profiles standing in for CARE, matching the fake 5 Series payments."""
from decimal import Decimal

from app.modules.transaction_monitoring.ports import ClientProfile

PROFILES = {
    p.client_id: p for p in (
        ClientProfile("CL-1001", "Lumen Capital SPC", ("SG", "HK", "GB"), Decimal("60000"),
                      ("Subscription to fund units", "Trade settlement", "Supplier invoice", "Advisory fee"),
                      35, False),
        ClientProfile("CL-2002", "Harbour Trust Ltd", ("HK", "SG"), Decimal("20000"),
                      ("Property expenses", "Supplier invoice"), 72, False),
        ClientProfile("CL-3003", "Seabright Holdings BV", ("NL", "DE", "GB"), Decimal("100000"),
                      ("Dividend", "Intercompany loan"), 55, True),
    )
}


class FakeProfiles:
    async def profile(self, client_id: str) -> ClientProfile | None:
        return PROFILES.get(client_id)
