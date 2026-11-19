"""ModelArts Studio MaaS (DeepSeek-V4-Flash), reached only through app/ai/llm_client.py in DEV/NPR/PRD.

Locally, MAAS_INTEGRATION=real calls the real model while INTEGRATIONS=fake keeps every other system synthetic.
"""
from app.core.config import Settings
from app.modules.cards.ports import Assistant, EvidenceReviewer, Recommender
from app.modules.transaction_monitoring.ports import ProfileInterpreter


def recommender(settings: Settings) -> Recommender:
    if settings.maas_mode == "fake":
        from app.integrations.maas.fake import FakeRecommender

        return FakeRecommender()
    from app.ai.llm_client import LlmClient
    from app.integrations.maas.real import MaasRecommender

    return MaasRecommender(LlmClient.from_settings(settings))


def evidence_reviewer(settings: Settings) -> EvidenceReviewer:
    """The evidence review of UC1, UC2 and UC3 cards (prompt cards.review-evidence)."""
    if settings.maas_mode == "fake":
        from app.integrations.maas.fake import FakeEvidenceReviewer

        return FakeEvidenceReviewer()
    from app.ai.llm_client import LlmClient
    from app.integrations.maas.review import MaasEvidenceReviewer

    return MaasEvidenceReviewer(LlmClient.from_settings(settings))


def profile_interpreter(settings: Settings) -> ProfileInterpreter:
    """Gate 2 (aml.gate2-profile): the model reads the payment against the client's profile."""
    if settings.maas_mode == "fake":
        from app.integrations.maas.fake import FakeProfileInterpreter

        return FakeProfileInterpreter()
    from app.ai.llm_client import LlmClient
    from app.integrations.maas.profile import MaasProfileInterpreter

    return MaasProfileInterpreter(LlmClient.from_settings(settings))


def assistant(settings: Settings) -> Assistant:
    if settings.maas_mode == "fake":
        from app.integrations.maas.fake import FakeAssistant

        return FakeAssistant()
    from app.ai.llm_client import LlmClient
    from app.integrations.maas.assistant import MaasAssistant

    return MaasAssistant(LlmClient.from_settings(settings))
