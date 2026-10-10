from __future__ import annotations

import os
from typing import Any

from crewai import LLM
from dotenv import load_dotenv

TARGET_URL = "http://3.69.250.207:8080/v1/chat/completions"
TARGET_MODEL = "ethos-6"

load_dotenv()


def get_default_llm() -> Any:
    """Return the instructor-configured OpenAI-compatible LLM."""
    target_url = os.getenv("TARGET_URL", TARGET_URL).strip()
    target_model = os.getenv("TARGET_MODEL", TARGET_MODEL).strip()
    base_url = target_url.removesuffix("/chat/completions").rstrip("/")
    return LLM(
        model=f"openai/{target_model}",
        provider="openai",
        base_url=base_url,
        api_key="not-needed",
        is_litellm=True,
    )


def get_llm(model: str | None = None) -> Any:
    """Create a provider-specific LLM instance for explicit opt-in use."""
    if model is None:
        return get_default_llm()
    return LLM(model=model)
