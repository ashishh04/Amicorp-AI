"""Application settings, read from environment variables and backend/.env.

In Kubernetes, External Secrets mounts each secret as a file in SECRETS_DIR, and pydantic-settings
reads it by field name (for example SECRETS_DIR/database_url). Nothing here has a credential default.
"""
import os
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "dev", "npr", "prd"]

# The only environments where the static n8n dev token may exist.
LOCAL_ENVIRONMENTS: frozenset[str] = frozenset({"local", "test"})
MIN_DEV_TOKEN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    app_name: str = "Amicorp Platform API"
    environment: Environment = "local"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: SecretStr
    db_pool_size: int = 10
    db_max_overflow: int = 10
    redis_url: str = "redis://127.0.0.1:6379/1"
    db_connect_timeout_seconds: int = 5

    # Local only: n8n sends it as "Authorization: Bearer <token>" and gets the Automation role.
    automation_dev_token: SecretStr | None = None

    # Entra ID. With accessTokenAcceptedVersion 2 the token's `aud` is the API's client ID (a GUID),
    # not its api:// URI (blueprint finding F1).
    entra_tenant_id: str | None = None
    entra_api_client_id: str | None = None
    entra_allowed_client_ids: list[str] = []

    max_body_bytes: int = 1_048_576
    docs_enabled: bool | None = None

    # Where the extraction service calls n8n back. Callback URLs must start with this base (finding F2).
    n8n_webhook_base: str = "http://127.0.0.1:5678"
    # Sent as X-Webhook-Token on extraction callbacks; n8n's extraction webhooks check it.
    n8n_extraction_webhook_token: SecretStr | None = None

    # "fake": synthetic data lake, extractor, recommender and Teams, for a laptop without the real systems.
    integrations: Literal["fake", "real"] = "real"
    # Run the jobs worker inside the API process, so one command runs everything locally.
    embedded_worker: bool = False

    # ModelArts Studio MaaS, CN-Hong Kong. Unset, the model follows INTEGRATIONS; locally MAAS_INTEGRATION=real
    # calls the real model while the other systems stay fake.
    maas_integration: Literal["fake", "real"] | None = None
    # The OpenAI-compatible endpoint and the model name, as "API Calling" on the Real-Time Inference page shows
    # them. DEV, NPR and PRD point MAAS_BASE_URL at the MaaS VPC endpoint.
    maas_base_url: str = "https://api-ap-southeast-1.modelarts-maas.com/openai/v1"
    maas_model: str = "deepseek-v4-flash"
    maas_api_key: SecretStr | None = None
    maas_timeout_seconds: float = 60.0  # per attempt; the jobs worker holds a job for 300 s
    # DeepSeek-V4-Flash reasons before it answers unless told not to; "default" leaves the model's own setting.
    maas_thinking: Literal["enabled", "disabled", "default"] = "disabled"
    # USD per million tokens, for the cost tracker (DeepSeek-V4-Flash in CN-Hong Kong, huawei-pricing-notes.md).
    maas_usd_per_m_input: Decimal = Decimal("0.135")
    maas_usd_per_m_output: Decimal = Decimal("0.27")
    # The monthly token budget the KPI dashboard measures use against (llmTokens).
    maas_monthly_input_tokens: int = 30_000_000
    maas_monthly_output_tokens: int = 20_000_000

    @model_validator(mode="after")
    def _check_environment(self) -> "Settings":
        if self.environment not in LOCAL_ENVIRONMENTS:
            if self.integrations == "fake":
                raise ValueError("INTEGRATIONS=fake is allowed only when ENVIRONMENT is local or test")
            if self.maas_integration == "fake":
                raise ValueError("MAAS_INTEGRATION=fake is allowed only when ENVIRONMENT is local or test")
            if self.embedded_worker:
                raise ValueError("EMBEDDED_WORKER is allowed only when ENVIRONMENT is local or test")
        if self.automation_dev_token is not None:
            if self.environment not in LOCAL_ENVIRONMENTS:
                raise ValueError("AUTOMATION_DEV_TOKEN is allowed only when ENVIRONMENT is local or test")
            if len(self.automation_dev_token.get_secret_value()) < MIN_DEV_TOKEN_LENGTH:
                raise ValueError(f"AUTOMATION_DEV_TOKEN must be at least {MIN_DEV_TOKEN_LENGTH} characters")
        if self.environment not in LOCAL_ENVIRONMENTS and not (
            self.entra_tenant_id and self.entra_api_client_id
        ):
            raise ValueError("ENTRA_TENANT_ID and ENTRA_API_CLIENT_ID are required outside local and test")
        return self

    @property
    def maas_mode(self) -> Literal["fake", "real"]:
        return self.maas_integration or self.integrations

    @property
    def show_docs(self) -> bool:
        """Interactive docs and /openapi.json: on in local, test and DEV only, unless set explicitly."""
        if self.docs_enabled is not None:
            return self.docs_enabled
        return self.environment in {"local", "test", "dev"}


@lru_cache
def get_settings() -> Settings:
    secrets_dir = os.environ.get("SECRETS_DIR")
    if secrets_dir:
        return Settings(_secrets_dir=secrets_dir)  # type: ignore[call-arg]
    return Settings()  # type: ignore[call-arg]
