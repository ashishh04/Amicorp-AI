"""A stand-in for the MaaS chat API, served through httpx.MockTransport: no test calls the real model."""
import json
from decimal import Decimal
from typing import Any

import httpx
from pydantic import SecretStr

from app.ai.llm_client import LlmClient
from app.observability.cost_tracker import Prices

PRICES = Prices(Decimal("0.135"), Decimal("0.27"))


def answer(content: str, *, finish: str = "stop", tokens: tuple[int, int] = (1000, 500)) -> httpx.Response:
    return httpx.Response(200, json={
        "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1], "total_tokens": sum(tokens)},
    })


class FakeMaas:
    """Answers each request with the next queued response, or raises the next queued exception."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def body(self, index: int = -1) -> dict[str, Any]:
        return json.loads(self.requests[index].content)

    def user_message(self, index: int = -1) -> str:
        return self.body(index)["messages"][1]["content"]


def client(server: FakeMaas, thinking: str = "disabled") -> LlmClient:
    return LlmClient(
        base_url="https://maas.test/openai/v1", api_key=SecretStr("test-key"), model="deepseek-v4-flash",
        timeout_s=5, thinking=thinking, prices=PRICES, transport=httpx.MockTransport(server),
    )
