"""
The thesis developer's model client (market-narrative Requirement 16.4-16.5, task 348).

An OpenAI-compatible chat call (OpenRouter by default), every answer cached by model and prompt, retried on rate
limits and timeouts, stopped by a call budget, and never sent without a key. A fake transport stands in for the
network: nothing here leaves the machine.
"""
from __future__ import annotations

import json

import httpx
import pytest

from algo_research.thesis.llm import BudgetExhausted, LLMClient, LLMConfig, MissingKey, config_from_env

MESSAGES = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "bias?"}]


def answer(text: str = '{"bias": "neutral"}', cost: float = 0.0) -> dict:
    return {"model": "vendor/model-x", "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost": cost}}


class Fake:
    """A transport that answers from a list and keeps every request it saw."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.responses.pop(0)
        return httpx.Response(status, json=body)


def client(tmp_path, fake, **kw) -> LLMClient:
    cfg = LLMConfig(api_key="test-key", model="vendor/model-x", cache_dir=tmp_path / "cache", **kw)
    return LLMClient(cfg, transport=httpx.MockTransport(fake), sleep=lambda s: None)


def test_a_call_is_an_openai_compatible_chat_request(tmp_path):
    fake = Fake((200, answer('{"bias": "bullish"}', cost=0.0012)))
    reply = client(tmp_path, fake).complete(MESSAGES)
    [req] = fake.requests
    assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer test-key"
    body = json.loads(req.content)
    assert body["model"] == "vendor/model-x" and body["messages"] == MESSAGES and body["temperature"] == 0
    assert reply.text == '{"bias": "bullish"}' and reply.cached is False and reply.cost == 0.0012
    assert reply.model == "vendor/model-x" and reply.usage["prompt_tokens"] == 120


def test_the_same_call_again_is_served_from_the_cache(tmp_path):
    fake = Fake((200, answer("first")))
    c = client(tmp_path, fake)
    one = c.complete(MESSAGES)
    again = client(tmp_path, Fake()).complete(MESSAGES)          # a new client: the cache is on disk
    assert (one.text, again.text) == ("first", "first") and again.cached is True
    assert len(fake.requests) == 1


def test_rate_limits_and_server_errors_are_retried(tmp_path):
    fake = Fake((429, {"error": {"message": "rate limited"}}), (502, {"error": "bad gateway"}), (200, answer("ok")))
    assert client(tmp_path, fake).complete(MESSAGES).text == "ok"
    assert len(fake.requests) == 3


def test_a_request_that_keeps_failing_raises_after_its_retries(tmp_path):
    fake = Fake(*[(429, {"error": "rate limited"})] * 3)
    with pytest.raises(RuntimeError, match="429"):
        client(tmp_path, fake, retries=2).complete(MESSAGES)


def test_the_budget_stops_new_calls_but_not_cached_ones(tmp_path):
    fake = Fake((200, answer("a")))
    c = client(tmp_path, fake, max_calls=1)
    c.complete(MESSAGES)
    assert c.complete(MESSAGES).cached                                # cached: no budget used
    with pytest.raises(BudgetExhausted):
        c.complete([{"role": "user", "content": "another"}])


def test_nothing_is_sent_without_a_key(tmp_path):
    fake = Fake((200, answer()))
    cfg = LLMConfig(api_key=None, cache_dir=tmp_path / "cache")
    with pytest.raises(MissingKey):
        LLMClient(cfg, transport=httpx.MockTransport(fake)).complete(MESSAGES)
    assert fake.requests == []


def test_the_settings_come_from_dotenv_and_the_environment_overrides(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# keys\nOPENROUTER_API_KEY=sk-or-from-file\nLLM_MODEL=vendor/from-file\nOTHER=1\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LLM_MODEL", "vendor/from-env")
    cfg = config_from_env(env)
    assert cfg.api_key == "sk-or-from-file" and cfg.model == "vendor/from-env"
    assert cfg.base_url == "https://openrouter.ai/api/v1"
    assert "sk-or" not in repr(cfg)                                   # the key never shows in a log line
