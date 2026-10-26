"""All runtime settings come from environment variables, read at call time.

Reading at call time (not import time) means flipping LLM_STUB or LLM_ENABLED in
.env and restarting is enough, and tests can change them with monkeypatch.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    stub: bool


def get_settings() -> Settings:
    return Settings(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1/"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        model=os.getenv("LLM_MODEL", "gemma3:1b"),
        stub=_flag("LLM_STUB", "0"),
    )
