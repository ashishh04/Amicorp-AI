"""Single entry point for LLM calls (retries, timeouts, tracing).

The model is DeepSeek-V4-Flash on ModelArts Studio MaaS, CN-Hong Kong, called on its OpenAI-compatible chat
API: POST {MAAS_BASE_URL}/chat/completions with "Authorization: Bearer <API key>". It is plain httpx rather
than the openai SDK: the call is one POST, and the SDK's compiled dependency (jiter) is one more file for
Windows Smart App Control to block on developer laptops.

Every call names a registered prompt and returns the task's Pydantic model. Anything else (a timeout, an HTTP
error, an answer that does not parse or fails the output guard) raises LlmError, and the caller fails closed:
a gate takes its blocking outcome, a card reaches a person without a summary.
"""
import asyncio
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, SecretStr, ValidationError

from app.ai.errors import LlmError
from app.ai.guards import output_guard
from app.ai.prompts.registry import Prompt
from app.core.config import Settings
from app.observability import cost_tracker

log = structlog.get_logger()

ATTEMPTS = 2  # one quick retry for a dropped connection, a 429 or a 5xx; the jobs worker retries longer outages
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_DELAY_SECONDS = 1.0
MAX_RETRY_AFTER_SECONDS = 10.0
_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass(frozen=True)
class Completion[T: BaseModel]:
    value: T
    model_id: str
    prompt: Prompt
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int

    def trace(self) -> dict[str, Any]:
        """Stored with the result (card evidence, gate run), so it can be traced to its prompt, model and cost."""
        return {
            "modelId": self.model_id, "promptKey": self.prompt.key, "promptSha": self.prompt.sha,
            "inputTokens": self.input_tokens, "outputTokens": self.output_tokens, "costUsd": str(self.cost_usd),
            "latencyMs": self.latency_ms,
        }


class LlmClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        timeout_s: float,
        thinking: str,
        prices: cost_tracker.Prices,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = chat_url(base_url)
        self.model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._thinking = thinking
        self._prices = prices
        self._transport = transport  # tests pass an httpx.MockTransport

    @classmethod
    def from_settings(cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> "LlmClient":
        if settings.maas_api_key is None:
            raise RuntimeError(
                "MAAS_API_KEY is not set. Create one on the API Keys page of the MaaS console (CN-Hong Kong), "
                "or set MAAS_INTEGRATION=fake locally."
            )
        return cls(
            base_url=settings.maas_base_url, api_key=settings.maas_api_key, model=settings.maas_model,
            timeout_s=settings.maas_timeout_seconds, thinking=settings.maas_thinking,
            prices=cost_tracker.Prices(settings.maas_usd_per_m_input, settings.maas_usd_per_m_output),
            transport=transport,
        )

    async def complete_structured[T: BaseModel](
        self,
        prompt: Prompt,
        variables: Mapping[str, str],
        schema: type[T],
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        timeout_s: float | None = None,
    ) -> Completion[T]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.render(variables)},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if self._thinking != "default":
            body["thinking"] = {"type": self._thinking}
        started = time.perf_counter()
        try:
            data = await self._post(body, timeout_s or self._timeout_s)
            latency_ms = round((time.perf_counter() - started) * 1000)
            model_id = str(data.get("model") or self.model)
            usage = data.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
            # The tokens are paid for whether or not the answer is usable, so count them first.
            cost = cost_tracker.record(model_id, prompt.key, input_tokens, output_tokens, self._prices)
            value = parse_answer(_content(data), schema)
            output_guard.check_strings(value)
        except LlmError as exc:
            log.warning("llm.failed", prompt=prompt.key, reason=exc.reason, status=exc.status, detail=exc.detail)
            raise
        log.info("llm.completed", model_id=model_id, prompt=prompt.key, latency_ms=latency_ms)
        return Completion(value, model_id, prompt, input_tokens, output_tokens, cost, latency_ms)

    async def _post(self, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        error, delay = LlmError("unavailable", "MaaS was not called"), 0.0
        async with httpx.AsyncClient(timeout=timeout_s, transport=self._transport, follow_redirects=False) as client:
            for attempt in range(ATTEMPTS):
                if attempt:
                    await asyncio.sleep(delay)
                try:
                    response = await client.post(self.url, json=body, headers=headers)
                except httpx.TimeoutException:
                    error = LlmError("timeout", f"MaaS did not answer within {timeout_s:g} s")
                    delay = RETRY_DELAY_SECONDS
                    continue
                except httpx.TransportError as exc:
                    error = LlmError("unavailable", f"MaaS could not be reached ({type(exc).__name__})")
                    delay = RETRY_DELAY_SECONDS
                    continue
                if response.status_code in RETRY_STATUSES:
                    error = LlmError("unavailable", _http_detail(response), response.status_code)
                    delay = _retry_after(response)
                    continue
                if not response.is_success:
                    raise LlmError("refused", _http_detail(response), response.status_code)
                try:
                    data = response.json()
                except ValueError:
                    raise LlmError("parse", "MaaS answered with something that is not JSON") from None
                if not isinstance(data, dict):
                    raise LlmError("parse", "MaaS answered with JSON that is not an object")
                return data
        raise error


def chat_url(base_url: str) -> str:
    """MAAS_BASE_URL with /chat/completions, whether or not it was pasted with it."""
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def parse_answer[T: BaseModel](content: str, schema: type[T]) -> T:
    """The JSON object in the model's answer, as the task's model. Prose or a ```json fence around the object,
    and an inline <think> block, are tolerated; nothing else."""
    text = _THINKING.sub("", content)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise LlmError("parse", "the answer holds no JSON object")
    try:
        return schema.model_validate_json(text[start : end + 1])
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'answer'}: {e['type']}" for e in exc.errors()[:3])
        raise LlmError("parse", f"the answer does not fit {schema.__name__} ({problems})") from None


def _content(data: Mapping[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LlmError("parse", "MaaS answered without a choice")
    if choices[0].get("finish_reason") == "length":
        raise LlmError("parse", "the answer was cut off at max_tokens")
    return str((choices[0].get("message") or {}).get("content") or "")


def _http_detail(response: httpx.Response) -> str:
    return f"MaaS answered HTTP {response.status_code}: {' '.join(response.text.split())[:300]}"


def _retry_after(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", RETRY_DELAY_SECONDS))
    except ValueError:  # an HTTP date: not worth parsing for one retry
        seconds = RETRY_DELAY_SECONDS
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
