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
    enabled: bool              # kill switch: LLM_ENABLED=false skips the model entirely
    timeout_s: float           # hard per-call timeout (SDK default is 10 minutes)
    max_retries: int           # OUR retries; the SDK's own retries are set to 0
    retry_base_s: float        # backoff: base, 2*base, 4*base ... plus jitter
    price_in_per_m: float      # USD per 1M input tokens (0 for Ollama / free models)
    price_out_per_m: float     # USD per 1M output tokens
    max_tokens: int            # hard cap on output tokens per call (reasoning tokens count too)
    reasoning_effort: str | None  # OpenRouter `reasoning.effort` (none/minimal/low/...); None = don't send


def get_settings() -> Settings:
    return Settings(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1/"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        model=os.getenv("LLM_MODEL", "gemma3:1b"),
        stub=_flag("LLM_STUB", "0"),
        enabled=_flag("LLM_ENABLED", "true"),
        timeout_s=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        retry_base_s=float(os.getenv("LLM_RETRY_BASE_SECONDS", "1")),
        price_in_per_m=float(os.getenv("LLM_PRICE_IN_PER_M", "0")),
        price_out_per_m=float(os.getenv("LLM_PRICE_OUT_PER_M", "0")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "512")),
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "").strip().lower() or None,
    )
