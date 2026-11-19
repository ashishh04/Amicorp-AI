"""What scans need from outside: candidate findings from the data lake (Bronze for UC4, Gold for UC5)."""
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class Candidate:
    rule_id: str
    subject_id: str
    title: str
    detail: dict[str, Any]
    policy_id: str | None = None

    def dedupe_key(self, ruleset: str) -> str:
        """The same problem on the same subject always has the same key, scan after scan."""
        return f"{ruleset}:{self.rule_id}:{self.subject_id}"


class ScanSource(Protocol):
    async def candidates(
        self, ruleset: str, layer: str, batch_date: date | None, scan_window: str | None
    ) -> list[Candidate]: ...
