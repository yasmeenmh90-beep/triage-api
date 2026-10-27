"""validate -> prompt -> call -> parse+validate -> repair once -> clean JSON or 422."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_settings
from src.llm.client import ChatResult, LLMTimeout, LLMUnavailable, chat
from src.llm.parse import OutputError, parse_verdict
from src.llm.prompt import build_messages, prompt_version
from src.llm.schema import Category, ModelVerdict, TriageResponse, Urgency

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
log = logging.getLogger("triage.llm")

REPAIR_INSTRUCTION = (
    "Your previous answer was rejected for this reason: {error}\n"
    "Return only corrected JSON matching the schema. No markdown, no other text."
)

# Kill-switch fallback: deterministic, safe, and routes everything to a human.
FALLBACK_VERDICT = ModelVerdict(
    category=Category.other,
    urgency=Urgency.medium,
    confidence=0.0,
    reason="Automatic triage is switched off; routed to manual review.",
)


class TriageFailed(Exception):
    """Both the first answer and the repair were invalid."""


def _append(filename: str, record: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / filename).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_call(version: str, repair: bool, outcome: str, result: ChatResult | None = None,
              attempts: int | None = None, error: str | None = None) -> None:
    """One structured line per model call: what it cost and how it went."""
    s = get_settings()
    in_tok = result.input_tokens if result else 0
    out_tok = result.output_tokens if result else 0
    record = {
        "ts": _now(),
        "prompt_version": version,
        "model": s.model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "duration_ms": result.duration_ms if result else None,
        "attempts": result.attempts if result else attempts,
        "repair": repair,
        "outcome": outcome,
        "reasoning_tokens": result.reasoning_tokens if result else 0,
        "finish_reason": result.finish_reason if result else None,
        "max_tokens": s.max_tokens,
        "reasoning_effort": s.reasoning_effort,
        "est_cost_usd": round(in_tok / 1e6 * s.price_in_per_m + out_tok / 1e6 * s.price_out_per_m, 8),
    }
    if error:
        record["error"] = error
    log.info(json.dumps(record))
    _append("llm_calls.jsonl", record)


def _call(messages: list[dict], version: str, repair: bool) -> ChatResult:
    try:
        return chat(messages)
    except (LLMTimeout, LLMUnavailable) as exc:
        _log_call(version, repair, "provider_error", attempts=exc.attempts, error=str(exc))
        raise


def _quarantine(text: str, raw: str, error: str, version: str) -> None:
    _append("quarantine.jsonl", {
        "ts": _now(),
        "prompt_version": version,
        "model": get_settings().model,
        "input": text,
        "raw_output": raw,
        "error": error,
    })


def _explain(exc: OutputError, result: ChatResult) -> str:
    if result.finish_reason == "length":
        return f"{exc} The answer was cut off at max_tokens (finish_reason=length)."
    return str(exc)


def triage_text(text: str) -> TriageResponse:
    version = prompt_version()
    messages = build_messages(text, version)

    first = _call(messages, version, repair=False)
    try:
        verdict = parse_verdict(first.content)
        _log_call(version, False, "ok", first)
        return TriageResponse.from_verdict(verdict)
    except OutputError as exc:
        error = _explain(exc, first)
        _log_call(version, False, "invalid_output", first, error=error)

    # Repair once — and only once: same prompt + its broken output + the exact error.
    repair_messages = messages + [
        {"role": "assistant", "content": first.content},
        {"role": "user", "content": REPAIR_INSTRUCTION.format(error=error)},
    ]
    second = _call(repair_messages, version, repair=True)
    try:
        verdict = parse_verdict(second.content)
        _log_call(version, True, "ok", second)
        return TriageResponse.from_verdict(verdict)
    except OutputError as exc:
        error = _explain(exc, second)
        _log_call(version, True, "invalid_output", second, error=error)
        _quarantine(text, second.content, error, version)
        raise TriageFailed(error) from exc
