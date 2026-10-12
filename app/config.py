"""
Application configuration, loaded from environment variables (.env).

The app always talks to a real, OpenAI-compatible LLM endpoint (see
app/llm_client.py) — there is no offline/mock fallback. `LLM_API_KEY`
must be set (via the environment or a local `.env` file) or the app
will refuse to build an LLM client.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load variables from a local .env file if present. Never overrides
# variables that are already set in the real environment.
load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    # --- LLM connection (OpenAI-compatible) ---
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    llm_model: str = os.getenv("LLM_MODEL", "liquid/lfm-2.5-2.6b:free")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_request_timeout: float = float(os.getenv("LLM_REQUEST_TIMEOUT", "60"))

    # --- FastAPI server ---
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))


settings = Settings()
