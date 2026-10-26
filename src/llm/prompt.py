"""Prompts live in files with a version number, so they can be reviewed and diffed."""
import json
import os
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def prompt_version() -> str:
    return os.getenv("PROMPT_VERSION", "triage-v1")


@lru_cache(maxsize=8)
def load_prompt(version: str) -> str:
    return (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


def build_messages(text: str, version: str) -> list[dict]:
    # Untrusted text goes in the user turn only, JSON-encoded so it cannot break out of its quotes.
    return [
        {"role": "system", "content": load_prompt(version)},
        {"role": "user", "content": json.dumps({"message": text}, ensure_ascii=False)},
    ]
