"""Turn untrusted model text into a validated ModelVerdict — or a clear error."""
import json
import re

from pydantic import ValidationError

from src.llm.schema import ModelVerdict

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class OutputError(Exception):
    """The model's answer could not be parsed or did not match the schema."""


def extract_json_object(raw: str) -> str:
    """Strip code fences and chatter, return the outermost {...} block."""
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise OutputError("No JSON object found in the model output.")
    return text[start : end + 1]


def parse_verdict(raw: str) -> ModelVerdict:
    candidate = extract_json_object(raw)
    try:
        json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise OutputError(f"Output is not valid JSON: {exc.msg} (char {exc.pos}).") from exc
    try:
        return ModelVerdict.model_validate_json(candidate)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'object'}: {e['msg']}" for e in exc.errors()
        )
        raise OutputError(f"Output does not match the schema — {problems}.") from exc
