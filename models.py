"""Blackbox.ai model discovery and testing.

The chat completions endpoint is the OpenAI-compatible
https://api.blackbox.ai/v1/chat/completions, authorized with the API key
created by the farm.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from config import Config

_CHAT_API = "https://api.blackbox.ai/v1/chat/completions"
_MODELS_API = "https://api.blackbox.ai/v1/models"


# 38 text models verified to work on a free account.
WORKING_MODELS: list[str] = [
    "blackboxai/blackbox-pro",
    "blackboxai/openai/gpt-5.4",
    "blackboxai/openai/gpt-5.4-pro",
    "blackboxai/openai/gpt-5.4-nano",
    "blackboxai/openai/gpt-5.3-codex",
    "blackboxai/openai/gpt-oss-120b",
    "blackboxai/openai/gpt-nemotron",
    "z-ai/glm-5.2",
    "blackboxai/deepseek/deepseek-v4-pro",
    "blackboxai/moonshotai/kimi-k3",
    "blackboxai/moonshotai/kimi-k2.7-code",
    "blackboxai/x-ai/grok-4.3",
    "blackboxai/x-ai/grok-4.1-fast-non-reasoning",
    "blackboxai/google/gemini-3.5-flash",
    "blackboxai/google/gemini-3.1-flash-lite",
    "blackboxai/mistral/devstral-2",
    "blackboxai/mistral/codestral",
    "blackboxai/mistral/mistral-small",
    "blackboxai/mistral/mistral-nemo",
    "blackboxai/mistral/pixtral-12b",
    "blackboxai/mistral/ministral-3b",
    "blackboxai/mistral/ministral-8b",
    "blackboxai/nvidia/nemotron-3-ultra",
    "blackboxai/nvidia/nemotron-3-super-120b-a12b:free",
    "blackboxai/nvidia/nemotron-3-nano-30b-a3b",
    "blackboxai/nvidia/nemotron-nano-12b-v2-vl",
    "blackboxai/google/gemma-4-31b-it",
    "blackboxai/google/gemma-4-26b-a4b-it",
    "blackboxai/amazon/nova-2-lite",
    "blackboxai/amazon/nova-micro",
    "blackboxai/meta/llama-3.1-8b",
    "blackboxai/meta/llama-3.1-70b",
    "blackboxai/morph/morph-v3-fast",
    "blackboxai/morph/morph-v3-large",
    "blackboxai/arcee-ai/trinity-large-thinking",
    "blackboxai/anthropic/claude-nemotron",
    "nvidia/nemotron-3.5-nano-blackbox",
]


@dataclass(slots=True)
class ModelTest:
    """Result of probing a single model."""

    model: str
    ok: bool
    detail: str
    elapsed: float = 0.0


async def fetch_all_models(cfg: Config) -> list[str]:
    """Pull the upstream model list from /api/v1/models (empty on error)."""
    async with httpx.AsyncClient(timeout=cfg.request_timeout) as client:
        resp = await client.get(_MODELS_API)
        if resp.status_code >= 400:
            return []
        data = resp.json()
        return [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]


async def test_model(api_key: str, model: str, *, timeout: int = 20) -> ModelTest:
    """Probe one model with a tiny completion. Network errors count as failures."""
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                _CHAT_API,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say hi in 3 words"}],
                    "max_tokens": 20,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        elapsed = time.monotonic() - started
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return ModelTest(model=model, ok=True, detail=content[:60], elapsed=elapsed)
        detail = _extract_error(resp)
        return ModelTest(model=model, ok=False, detail=detail, elapsed=elapsed)
    except httpx.HTTPError as exc:
        elapsed = time.monotonic() - started
        return ModelTest(model=model, ok=False, detail=f"network: {exc.__class__.__name__}", elapsed=elapsed)


async def test_all(api_key: str, models: list[str] | None = None, *, delay: float = 0.4) -> list[ModelTest]:
    """Test every model in sequence with a small delay between calls."""
    targets = models or WORKING_MODELS
    results: list[ModelTest] = []
    for model in targets:
        results.append(await test_model(api_key, model))
        if delay > 0:
            await _sleep(delay)
    return results


def _extract_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message", resp.text))[:80]
        if isinstance(error, str):
            return error[:80]
    except ValueError:
        pass
    return f"HTTP {resp.status_code}"


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
