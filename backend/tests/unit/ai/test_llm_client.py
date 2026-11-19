from decimal import Decimal

import httpx
import pytest
from pydantic import BaseModel

from app.ai.errors import LlmError
from app.ai.llm_client import chat_url, parse_answer
from app.ai.prompts.registry import PROMPTS
from tests.unit.ai.fake_maas import FakeMaas, answer, client

pytestmark = pytest.mark.anyio

PING = PROMPTS["platform.connectivity-check@1"]


class Pong(BaseModel):
    ok: bool


class Note(BaseModel):
    text: str


async def test_a_call_sends_the_registered_prompt_and_returns_the_parsed_answer():
    server = FakeMaas(answer('{"ok": true}'))
    result = await client(server).complete_structured(PING, {}, Pong)

    assert result.value.ok is True
    request = server.requests[0]
    assert str(request.url) == "https://maas.test/openai/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = server.body()
    assert (body["model"], body["temperature"], body["stream"]) == ("deepseek-v4-flash", 0.0, False)
    assert body["thinking"] == {"type": "disabled"}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert result.cost_usd == Decimal("0.00027")  # 1,000 x 0.135/M + 500 x 0.27/M
    assert result.trace()["promptKey"] == "platform.connectivity-check@1"
    assert result.trace()["promptSha"] == PING.sha


async def test_thinking_left_to_the_model_sends_no_thinking_field():
    server = FakeMaas(answer('{"ok": true}'))
    await client(server, thinking="default").complete_structured(PING, {}, Pong)
    assert "thinking" not in server.body()


def test_the_base_url_may_be_pasted_with_or_without_the_path():
    assert chat_url("https://h/openai/v1/") == "https://h/openai/v1/chat/completions"
    assert chat_url("https://h/v2/chat/completions") == "https://h/v2/chat/completions"


def test_fences_prose_and_think_blocks_around_the_json_are_tolerated():
    content = 'Here it is.\n<think>{"ok": false}</think>\n```json\n{"ok": true}\n```'
    assert parse_answer(content, Pong).ok is True


def test_an_answer_without_json_or_of_the_wrong_shape_is_a_parse_error():
    with pytest.raises(LlmError) as no_json:
        parse_answer("I cannot help with that.", Pong)
    assert no_json.value.reason == "parse"
    with pytest.raises(LlmError, match="ok: bool_parsing"):
        parse_answer('{"ok": "maybe"}', Pong)


async def test_a_429_is_retried_once():
    server = FakeMaas(httpx.Response(429, headers={"Retry-After": "0"}, text="busy"), answer('{"ok": true}'))
    result = await client(server).complete_structured(PING, {}, Pong)
    assert result.value.ok is True
    assert len(server.requests) == 2


async def test_a_refusal_is_not_retried():
    server = FakeMaas(httpx.Response(401, json={"error_msg": "Incorrect API key"}))
    with pytest.raises(LlmError) as refused:
        await client(server).complete_structured(PING, {}, Pong)
    assert (refused.value.reason, refused.value.status) == ("refused", 401)
    assert "Incorrect API key" in refused.value.detail
    assert len(server.requests) == 1


async def test_no_answer_on_either_attempt_is_a_timeout(monkeypatch):
    monkeypatch.setattr("app.ai.llm_client.RETRY_DELAY_SECONDS", 0.0)
    server = FakeMaas(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"))
    with pytest.raises(LlmError) as timeout:
        await client(server).complete_structured(PING, {}, Pong)
    assert timeout.value.reason == "timeout"
    assert len(server.requests) == 2


async def test_an_answer_cut_off_at_max_tokens_is_refused():
    server = FakeMaas(answer('{"ok": tr', finish="length"))
    with pytest.raises(LlmError, match="cut off at max_tokens"):
        await client(server).complete_structured(PING, {}, Pong)


async def test_a_link_in_the_answer_fails_the_output_guard():
    server = FakeMaas(answer('{"text": "Details at https://example.org/x"}'))
    with pytest.raises(LlmError) as guard:
        await client(server).complete_structured(PING, {}, Note)
    assert guard.value.reason == "guard"
