"""n8n webhooks the API calls back (the extraction callbacks). Real in every environment, local included:
n8n runs on the laptop too."""
from typing import Any

import httpx
import structlog
from pydantic import SecretStr

log = structlog.get_logger()

WEBHOOK_HEADER = "X-Webhook-Token"
TIMEOUT_SECONDS = 10.0


class WebhookCallbacks:
    def __init__(self, token: SecretStr | None, timeout: float = TIMEOUT_SECONDS) -> None:
        self._token = token
        self._timeout = timeout

    async def send(self, url: str, body: dict[str, Any]) -> None:
        if self._token is None:
            raise RuntimeError("N8N_EXTRACTION_WEBHOOK_TOKEN is not set, so n8n would refuse the callback")
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            response = await client.post(url, json=body, headers={WEBHOOK_HEADER: self._token.get_secret_value()})
        if response.status_code >= 300:
            raise RuntimeError(f"n8n answered the callback with HTTP {response.status_code}")
        log.info("n8n.callback_sent", status=response.status_code)
