"""A fake OpenAI-compatible server for testing the plumbing WITHOUT a real model.

It is NOT a model and its answers say nothing about prompt quality. It exists so the
parse / repair / retry / timeout / kill-switch paths can be exercised deterministically.

    uvicorn tests.mock_llm:app --port 9999
    LLM_BASE_URL=http://localhost:9999/v1 ...

Behaviour is chosen by a keyword in the customer message:
  MOCK_FENCE    -> valid JSON wrapped in a ```json fence with chatter
  MOCK_BADENUM  -> category "refund" (not in enum) every time      -> 422 + quarantine
  MOCK_REPAIR   -> bad first answer, valid answer on the repair call
  MOCK_GARBAGE  -> not JSON at all, every time
  MOCK_SLOW     -> sleeps longer than the client timeout
  MOCK_500      -> HTTP 500
  MOCK_429      -> HTTP 429 with Retry-After: 1
otherwise a simple keyword rule picks a category. API key "bad" -> HTTP 401.
"""
import asyncio
import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
CALLS: list[dict] = []


def _completion(content: str) -> dict:
    return {
        "id": "mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "mock-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 412, "completion_tokens": 38, "total_tokens": 450},
    }


def _verdict(category: str, urgency: str = "medium", confidence: float = 0.9) -> str:
    return json.dumps({"category": category, "urgency": urgency, "confidence": confidence, "reason": "Mock answer."})


@app.get("/calls")
def calls():
    return {"count": len(CALLS)}


@app.post("/calls/reset")
def reset():
    CALLS.clear()
    return {"count": 0}


@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.json()
    CALLS.append(body)
    if request.headers.get("authorization", "") == "Bearer bad":
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API key", "code": 401}})

    msgs = body["messages"]
    user = msgs[1]["content"] if len(msgs) > 1 else ""
    is_repair = len(msgs) > 2

    if "MOCK_SLOW" in user:
        await asyncio.sleep(5)
        return _completion(_verdict("technical"))
    if "MOCK_500" in user:
        return JSONResponse(status_code=500, content={"error": {"message": "upstream exploded"}})
    if "MOCK_429" in user:
        return JSONResponse(status_code=429, headers={"Retry-After": "1"}, content={"error": {"message": "slow down"}})
    if "MOCK_FENCE" in user:
        return _completion("Sure! Here's the JSON:\n```json\n" + _verdict("billing") + "\n```")
    if "MOCK_BADENUM" in user:
        return _completion(_verdict("refund"))
    if "MOCK_GARBAGE" in user:
        return _completion("I think this is probably about billing, maybe?")
    if "MOCK_REPAIR" in user:
        return _completion(_verdict("account", "high") if is_repair else '{"category": "account", "urgency": "urgent"}')

    text = user.lower()
    for words, cat in [
        (("charge", "invoice", "refund", "billing", "card"), "billing"),
        (("error", "crash", "bug", "down", "500", "broken"), "technical"),
        (("password", "login", "2fa", "account", "delete"), "account"),
        (("demo", "upgrade", "pricing", "seats", "quote"), "sales"),
    ]:
        if any(w in text for w in words):
            return _completion(_verdict(cat))
    return _completion(_verdict("other", "low", 0.3))
