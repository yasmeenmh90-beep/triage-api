"""Stage 0 smoke test: prove a model answers from this machine.

Run from the repo root:  python -m src.llm.hello
"""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
res = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": "Reply with exactly the word: ready"}],
)
print(res.choices[0].message.content)
