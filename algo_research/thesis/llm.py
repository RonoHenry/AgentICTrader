"""The thesis developer's model client (market-narrative Requirement 16.4-16.5).

An OpenAI-compatible chat call, OpenRouter by default. The settings come from the environment, then `.env`:

    OPENROUTER_API_KEY    the key (also read as LLM_API_KEY); nothing is sent without one
    LLM_BASE_URL          default https://openrouter.ai/api/v1 (LM Studio or Ollama serve the same API locally)
    LLM_MODEL             default nvidia/nemotron-3-ultra-550b-a55b:free

Every answer is cached on disk by model and request, so a rerun pays nothing and reproduces a thesis exactly. A
client stops at its call budget, retries rate limits, server errors and timeouts with a growing pause, and keeps
the tokens and the cost OpenRouter reports for each call.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import httpx

from algo_backtester.config import REPO_ROOT

__all__ = ["BudgetExhausted", "DEFAULT_MODEL", "LLMClient", "LLMConfig", "MissingKey", "Reply", "config_from_env"]

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
CACHE_DIR = REPO_ROOT / "data" / "research" / "theses" / "cache"
_RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class MissingKey(RuntimeError):
    """No API key: nothing is sent."""


class BudgetExhausted(RuntimeError):
    """The run's call budget is spent."""


@dataclass
class LLMConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: Optional[str] = field(default=None, repr=False)      # never in a log line
    timeout: float = 600.0                                         # reasoning models can think for minutes
    retries: int = 4
    max_calls: int = 50
    cache_dir: Path = CACHE_DIR


@dataclass
class Reply:
    text: str
    model: str
    usage: dict
    cost: float
    seconds: float
    cached: bool


def _dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def config_from_env(env_file: Optional[Path] = None, **overrides) -> LLMConfig:
    """The settings from the environment first, then `.env` (the repository's by default)."""
    file = _dotenv(Path(env_file) if env_file else REPO_ROOT / ".env")
    get = lambda k: os.environ.get(k) or file.get(k)  # noqa: E731
    cfg = LLMConfig(base_url=get("LLM_BASE_URL") or DEFAULT_BASE_URL, model=get("LLM_MODEL") or DEFAULT_MODEL,
                    api_key=get("OPENROUTER_API_KEY") or get("LLM_API_KEY") or None)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


class LLMClient:
    def __init__(self, cfg: LLMConfig, transport: Optional[httpx.BaseTransport] = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.cfg, self._sleep = cfg, sleep
        self._http = httpx.Client(transport=transport, timeout=cfg.timeout)
        self.calls, self.cost = 0, 0.0

    def _key(self, body: dict) -> str:
        return hashlib.sha256(json.dumps({"base": self.cfg.base_url, **body}, sort_keys=True).encode()).hexdigest()

    def complete(self, messages: list[dict], *, temperature: float = 0.0, max_tokens: Optional[int] = None,
                 reasoning: Optional[dict] = None) -> Reply:
        """The model's answer to ``messages``, from the cache when this exact request was made before."""
        body: dict = {"model": self.cfg.model, "messages": messages, "temperature": temperature}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if reasoning is not None:
            body["reasoning"] = reasoning
        path = Path(self.cfg.cache_dir) / f"{self._key(body)}.json"
        if path.is_file():
            kept = json.loads(path.read_text(encoding="utf-8"))
            return Reply(kept["text"], kept["model"], kept["usage"], kept["cost"], kept["seconds"], True)
        if not self.cfg.api_key:
            raise MissingKey("no OPENROUTER_API_KEY: add it to .env")
        if self.calls >= self.cfg.max_calls:
            raise BudgetExhausted(f"the run's budget of {self.cfg.max_calls} calls is spent")
        headers = {"Authorization": f"Bearer {self.cfg.api_key}", "X-Title": "AgentICTrader research"}
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        started, last = time.monotonic(), None
        for attempt in range(self.cfg.retries + 1):
            try:
                r = self._http.post(url, json={**body, "usage": {"include": True}}, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if r.status_code == 200:
                    data = r.json()
                    if data.get("choices"):
                        break
                    last = f"200 without choices: {str(data)[:300]}"
                elif r.status_code in _RETRY_STATUS:
                    last = f"{r.status_code}: {r.text[:300]}"
                else:
                    raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
            if attempt < self.cfg.retries:
                self._sleep(min(120.0, 5.0 * 2 ** attempt))
        else:
            raise RuntimeError(f"the model kept failing after {self.cfg.retries + 1} tries; last: {last}")
        message = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        reply = Reply(text=(message.get("content") or "").strip(), model=data.get("model") or self.cfg.model,
                      usage=usage, cost=float(usage.get("cost") or 0.0), seconds=round(time.monotonic() - started, 1),
                      cached=False)
        self.calls += 1
        self.cost += reply.cost
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"request": body, "text": reply.text, "model": reply.model, "usage": usage,
                                    "cost": reply.cost, "seconds": reply.seconds,
                                    "reasoning": message.get("reasoning")}, indent=1), encoding="utf-8")
        return reply
