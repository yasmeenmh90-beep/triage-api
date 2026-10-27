"""One model call, with a real timeout and a deliberate retry policy.

Retry policy (ours, not the SDK's — the SDK is set to max_retries=0):
  retry   : timeouts, connection errors, 429, 5xx
  never   : 400, 401, 403, 404 and any other 4xx — retrying cannot fix them
  backoff : retry_base * 2**n + random jitter (1s, 2s, 4s ...); a 429 Retry-After wins
"""
import random
import time
from dataclasses import dataclass

import openai
from openai import OpenAI

from src.config import Settings, get_settings

MAX_RETRY_AFTER_S = 30.0


class LLMTimeout(Exception):
    """The provider did not answer within the timeout (after retries)."""

    attempts = 1


class LLMUnavailable(Exception):
    """The provider failed in a way retries could not fix."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
        self.attempts = 1


@dataclass
class ChatResult:
    content: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    attempts: int
    reasoning_tokens: int = 0
    finish_reason: str | None = None


def build_client(settings: Settings) -> OpenAI:
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_s,
        max_retries=0,  # explicit: all retries are ours, so one request == the calls we log
    )


def request_kwargs(settings: Settings, messages: list[dict]) -> dict:
    """The exact request body. max_tokens caps cost and latency; reasoning is opt-in per provider."""
    kwargs = {
        "model": settings.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": settings.max_tokens,
    }
    if settings.reasoning_effort:
        # OpenRouter: {"effort": "none"} turns hidden reasoning off. A ~40-token JSON answer
        # does not need 1,000+ tokens of thinking, and those tokens are billed and slow.
        kwargs["extra_body"] = {"reasoning": {"effort": settings.reasoning_effort}}
    return kwargs


def _retry_after_seconds(exc: openai.APIStatusError) -> float | None:
    value = exc.response.headers.get("retry-after") if exc.response is not None else None
    try:
        return min(float(value), MAX_RETRY_AFTER_S) if value is not None else None
    except ValueError:
        return None


def _backoff(settings: Settings, retry_number: int) -> float:
    return settings.retry_base_s * (2**retry_number) + random.uniform(0, settings.retry_base_s / 2)


def chat(messages: list[dict]) -> ChatResult:
    settings = get_settings()
    client = build_client(settings)
    started = time.perf_counter()
    attempt = 0

    while True:
        attempt += 1
        retry_in: float | None = None
        try:
            res = client.chat.completions.create(**request_kwargs(settings, messages))
            usage = res.usage
            details = getattr(usage, "completion_tokens_details", None)
            return ChatResult(
                content=res.choices[0].message.content or "",
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                duration_ms=int((time.perf_counter() - started) * 1000),
                attempts=attempt,
                reasoning_tokens=getattr(details, "reasoning_tokens", 0) or 0,
                finish_reason=res.choices[0].finish_reason,
            )
        except openai.APITimeoutError as exc:
            final: Exception = LLMTimeout(f"No answer from the model within {settings.timeout_s:.0f}s.")
            final.__cause__ = exc
        except openai.APIConnectionError as exc:
            final = LLMUnavailable(f"Could not reach the model provider at {settings.base_url}.")
            final.__cause__ = exc
        except openai.RateLimitError as exc:
            final = LLMUnavailable("The model provider is rate-limiting us (429).", status=429)
            retry_in = _retry_after_seconds(exc)
        except openai.InternalServerError as exc:
            final = LLMUnavailable(f"The model provider returned {exc.status_code}.", status=exc.status_code)
        except openai.APIStatusError as exc:
            # 400/401/403/404...: a bad key is still a bad key in four seconds. Fail fast.
            hint = {401: "check LLM_API_KEY", 403: "key lacks access", 404: "check LLM_MODEL / base URL"}
            rejected = LLMUnavailable(
                f"The model provider rejected the request ({exc.status_code}"
                f"{': ' + hint[exc.status_code] if exc.status_code in hint else ''}). Not retried.",
                status=exc.status_code,
            )
            rejected.attempts = attempt
            raise rejected from exc

        if attempt > settings.max_retries:
            final.attempts = attempt
            raise final
        time.sleep(retry_in if retry_in is not None else _backoff(settings, attempt - 1))
