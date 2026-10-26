# triage-api

`POST /triage` — an LLM-backed support-message classifier (work in progress).

Three environment variables (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) are the only difference between a model on your laptop (Ollama) and one in a datacentre (OpenRouter) — so the provider is never hard-coded.

## Try it (stub mode, no model needed)
```bash
LLM_STUB=1 uvicorn src.main:app --port 8000

# valid -> 200
curl -s -X POST localhost:8000/triage -H 'Content-Type: application/json' -d '{"text":"I was charged twice this month"}'
# broken (wrong field) -> 400 naming the field
curl -s -X POST localhost:8000/triage -H 'Content-Type: application/json' -d '{"message":"hi"}'
```
