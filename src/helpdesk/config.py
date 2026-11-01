"""Runtime configuration: the fixed "current" time, data location and LLM settings."""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# The task fixes "now" so that answers are reproducible. Logic never calls datetime.now().
NOW = datetime.fromisoformat("2026-06-10T09:00:00+02:00")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_REQUIRED_ENV = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str


def load_llm_settings() -> LLMSettings:
    """Read LLM settings from the environment, failing fast with a readable message."""
    missing = [name for name in _REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing environment variables: {', '.join(missing)}. Copy .env.example to .env and fill them in."
        )
    return LLMSettings(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        model=os.environ["LLM_MODEL"],
    )
