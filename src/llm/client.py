from openai import OpenAI

from src.config import get_settings


def build_client() -> OpenAI:
    s = get_settings()
    return OpenAI(base_url=s.base_url, api_key=s.api_key)


def chat(messages: list[dict]) -> str:
    s = get_settings()
    res = build_client().chat.completions.create(model=s.model, messages=messages, temperature=0)
    return res.choices[0].message.content or ""
