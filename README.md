# triage-api

`POST /triage` — an LLM-backed support-message classifier (work in progress).

Three environment variables (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) are the only difference between a model on your laptop (Ollama) and one in a datacentre (OpenRouter) — so the provider is never hard-coded.
