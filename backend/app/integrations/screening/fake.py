"""A deterministic screening stand-in: "Kowloon Trading" and anything with "Sanction" in its name are hits;
"Unscreenable" makes the provider unavailable, so the gate's fail-closed path can be shown."""
import hashlib

from app.modules.transaction_monitoring.ports import ScreeningResult, ScreeningUnavailable

HITS = ("kowloon trading", "sanction")


class FakeScreening:
    async def screen(self, name: str, country: str) -> ScreeningResult:
        lowered = name.lower()
        if "unscreenable" in lowered:
            raise ScreeningUnavailable("The screening provider did not answer (local stand-in)")
        reference = "WC-LOCAL-" + hashlib.sha256(f"{name}|{country}".encode()).hexdigest()[:8].upper()
        if any(term in lowered for term in HITS):
            return ScreeningResult(hit=True, score=92, reference=reference, matched_name=name)
        return ScreeningResult(hit=False, score=0, reference=reference)
