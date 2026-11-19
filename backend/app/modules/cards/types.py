"""The card type registry (LLD, Card type registry). The portal reads it through GET /v1/card-types.

Teams, severities, SLAs and the other texts match the portal's registry (frontend mock-data CARD_TYPES).
`recommend_mode`: the card waits in ASSEMBLING until its evidence and an AI recommendation are ready.
UC4 and UC5 workflows ask for theirs (POST /recommend with this mode); for UC1, UC2 and UC3 cards the API itself
queues the evidence review (`review-evidence`) when it creates the card, as their workflows never call /recommend.
Return-to-AI runs the type's mode again with the officer's instruction. A type without a mode would go straight to
AWAITING_DECISION (LLD, Transitions, actors and guards).
`writes_back`: an Approve hands the outcome to the write-back worker (frontend mock WRITES_BACK).
"""
from dataclasses import dataclass
from typing import Literal

from app.shared.business_time import BUSINESS_DAY_HOURS

Severity = Literal["low", "medium", "high", "critical"]
RecommendMode = Literal["assemble-and-recommend", "propose-correction", "review-evidence"]
REVIEW_EVIDENCE: RecommendMode = "review-evidence"
SEVERITY_ORDER: tuple[Severity, ...] = ("low", "medium", "high", "critical")

# The business calendar each owning team works to (ref.calendar); SLAs count its hours.
TEAM_CALENDAR: dict[str, Literal["HK", "EU"]] = {
    "Operations": "HK", "Compliance": "HK", "MLRO office": "HK", "Fund accounting": "EU", "Data team": "HK",
}

USE_CASE_PREFIX = {"UC1": "uc1.", "UC2": "aml.", "UC3": "nav.", "UC4": "uc4.", "UC5": "uc5."}


@dataclass(frozen=True)
class CardTypeDef:
    type: str
    version: int
    use_case: str
    subject_type: str
    team: str
    severity: Severity | Literal["by policy"]
    sla: str
    sla_business_hours: float
    escalation_role: str
    on_approval: str
    decided_by: Literal["Checker", "MLRO"]
    title: str  # "{subject}" is replaced with the card's subject
    description: str
    recommend_mode: RecommendMode | None = None
    writes_back: bool = False

    @property
    def recommends(self) -> bool:
        return self.recommend_mode is not None

    @property
    def default_severity(self) -> Severity:
        return "medium" if self.severity == "by policy" else self.severity

    @property
    def calendar(self) -> Literal["HK", "EU"]:
        return TEAM_CALENDAR.get(self.team, "HK")


def _days(n: int) -> float:
    return n * BUSINESS_DAY_HOURS


CARD_TYPES: dict[str, CardTypeDef] = {d.type: d for d in (
    CardTypeDef(
        "uc1.statement-validation", 2, "UC1", "document", "Operations", "medium", "2 business days", _days(2),
        "Operations Lead",
        "Output files for the core systems, status write-back, post-facto lines to transaction monitoring",
        "Checker", "Bank statement {subject}",
        "A Maker reviews the extracted lines, corrects flagged fields and submits the statement; a Checker "
        "approves it.", recommend_mode=REVIEW_EVIDENCE, writes_back=True),
    CardTypeDef(
        "uc1.extraction-exception", 1, "UC1", "document", "Operations", "medium", "1 business day", _days(1),
        "Operations Lead", "Reprocess or manual capture", "Checker", "Extraction failed for statement {subject}",
        "The statement could not be extracted. Decide whether to reprocess it or capture it by hand.",
        recommend_mode=REVIEW_EVIDENCE),
    CardTypeDef(
        "aml.compliance-decision", 3, "UC2", "transaction", "Compliance", "high", "4 business hours", 4, "MLRO",
        "Release the payment hold; CARE audit stamp", "Checker", "Compliance decision on payment {subject}",
        "Gate 1 put this payment under monitoring and screening found no strong match. Review the gate results "
        "and decide whether to release it.", recommend_mode=REVIEW_EVIDENCE, writes_back=True),
    CardTypeDef(
        "aml.mlro-escalation", 2, "UC2", "transaction", "MLRO office", "critical", "4 business hours", 4,
        "Deputy MLRO", "Incident, STR pack, freeze or return of funds", "MLRO", "MLRO escalation: payment {subject}",
        "A screening match needs the MLRO's decision.", recommend_mode=REVIEW_EVIDENCE, writes_back=True),
    CardTypeDef(
        "aml.profile-update", 1, "UC2", "transaction", "Compliance", "high", "1 business day", _days(1), "MLRO",
        "Profile write-back; re-validate from gate 2", "Checker", "Client profile update for payment {subject}",
        "The payment does not fit the client profile. Update the profile, then the payment is re-validated.",
        recommend_mode=REVIEW_EVIDENCE, writes_back=True),
    CardTypeDef(
        "aml.gate-exception", 1, "UC2", "transaction", "Compliance", "high", "2 business hours", 2, "MLRO",
        "Manual gate decision or re-run", "Checker", "Payment {subject} held: gate exception",
        "A gate could not decide, so the payment is held. Decide manually or re-run the gate.",
        recommend_mode=REVIEW_EVIDENCE),
    CardTypeDef(
        "nav.approval", 1, "UC3", "document", "Fund accounting", "medium", "1 business day", _days(1),
        "Head of Fund Accounting", "Publish the NAV to Valuefy", "Checker", "NAV statement {subject}",
        "The NAV checks passed. Approve to publish the NAV.", recommend_mode=REVIEW_EVIDENCE, writes_back=True),
    CardTypeDef(
        "nav.exception", 1, "UC3", "document", "Fund accounting", "high", "1 business day", _days(1),
        "Head of Fund Accounting", "Correct, or accept with rationale", "Checker", "NAV exception on {subject}",
        "A NAV check failed. Correct the NAV or accept it with a rationale.", recommend_mode=REVIEW_EVIDENCE),
    CardTypeDef(
        "nav.extraction-exception", 1, "UC3", "document", "Fund accounting", "medium", "1 business day", _days(1),
        "Head of Fund Accounting", "Reprocess or manual capture", "Checker",
        "Extraction failed for NAV statement {subject}",
        "The NAV statement could not be extracted. Decide whether to reprocess it or capture it by hand.",
        recommend_mode=REVIEW_EVIDENCE),
    CardTypeDef(
        "uc4.discrepancy", 2, "UC4", "record", "Data team", "low", "5 business days", _days(5), "Head of Data",
        "Correction written back where approved", "Checker", "Data discrepancy on {subject}",
        "Two systems of record disagree. Review the evidence and the proposed correction.",
        recommend_mode="assemble-and-recommend", writes_back=True),
    CardTypeDef(
        "uc5.violation", 1, "UC5", "record", "Data team", "by policy", "by policy", _days(3), "Head of Data",
        "Approved correction written to CARE or 5 Series", "Checker", "Policy violation on {subject}",
        "A record breaches a data policy. Review the proposed correction.",
        recommend_mode="propose-correction", writes_back=True),
)}
