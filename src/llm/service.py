"""validate -> prompt -> call -> parse+validate -> repair once -> clean JSON or 422."""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_settings
from src.llm.client import chat
from src.llm.parse import OutputError, parse_verdict
from src.llm.prompt import build_messages, prompt_version
from src.llm.schema import TriageResponse

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

REPAIR_INSTRUCTION = (
    "Your previous answer was rejected for this reason: {error}\n"
    "Return only corrected JSON matching the schema. No markdown, no other text."
)


class TriageFailed(Exception):
    """Both the first answer and the repair were invalid."""


def _quarantine(text: str, raw: str, error: str, version: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "prompt_version": version,
        "model": get_settings().model,
        "input": text,
        "raw_output": raw,
        "error": error,
    }
    with (LOG_DIR / "quarantine.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def triage_text(text: str) -> TriageResponse:
    version = prompt_version()
    messages = build_messages(text, version)

    raw = chat(messages)
    try:
        return TriageResponse.from_verdict(parse_verdict(raw))
    except OutputError as first_error:
        error = str(first_error)

    # Repair once — and only once: same prompt + its broken output + the exact error.
    repair_messages = messages + [
        {"role": "assistant", "content": raw},
        {"role": "user", "content": REPAIR_INSTRUCTION.format(error=error)},
    ]
    raw = chat(repair_messages)
    try:
        return TriageResponse.from_verdict(parse_verdict(raw))
    except OutputError as second_error:
        _quarantine(text, raw, str(second_error), version)
        raise TriageFailed(str(second_error)) from second_error
