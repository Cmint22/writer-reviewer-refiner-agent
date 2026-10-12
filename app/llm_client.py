"""
LLM client abstraction.

Both agents talk to an LLM only through the `LLMClient` protocol's
`chat(system, user)` method. This lets us swap in any OpenAI-compatible
endpoint (OpenAI, Azure OpenAI, Groq, Together, OpenRouter, a local
Ollama server, etc.) by changing only LLM_BASE_URL / LLM_MODEL in
`.env` — no code changes required.

There is no mock/offline client: `get_llm_client()` always builds a
real `OpenAICompatibleClient` and requires `LLM_API_KEY` to be set.
"""
from __future__ import annotations

from typing import Protocol

from app.config import Settings, settings


class LLMClient(Protocol):
    """Minimal interface both agents depend on."""

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a single-turn chat completion request and return the text reply."""
        ...


class OpenAICompatibleClient:
    """
    Thin wrapper around the `openai` Python SDK, pointed at any
    OpenAI-compatible `/chat/completions` endpoint via `base_url`.
    """

    def __init__(self, cfg: Settings):
        from openai import OpenAI

        self._model = cfg.llm_model
        self._temperature = cfg.llm_temperature
        self._client = OpenAI(
            api_key=cfg.llm_api_key,
            base_url=cfg.llm_base_url,
            timeout=cfg.llm_request_timeout,
        )

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()


def get_llm_client(cfg: Settings | None = None) -> LLMClient:
    """Factory: always builds the real OpenAI-compatible client.

    Raises a clear error if no API key is configured instead of
    silently falling back to any kind of mock/offline behavior.
    """
    cfg = cfg or settings
    if not cfg.llm_api_key:
        raise RuntimeError(
            "LLM_API_KEY is not set. Configure it in your environment or .env file "
            f"(LLM_BASE_URL={cfg.llm_base_url}, LLM_MODEL={cfg.llm_model})."
        )
    return OpenAICompatibleClient(cfg)
