# triage-api — `POST /triage`

## What it does

When a customer writes to support, someone has to read the message and decide who should handle it and how urgent it is. This API does that first read automatically. You send it one message, and it sends back a label (billing, technical, account, sales or other), an urgency (low, medium or high), the team it should go to, how confident it is, and a one-line reason. If it isn't sure, it says so and sends the message to a human instead of guessing.

Under the hood, a language model makes the judgement. The API treats the model's answer as untrusted input: it checks every answer against a fixed schema, asks the model to repair a bad answer once, and refuses (422) rather than pass on anything that doesn't fit.

## Run it in under five minutes

```bash
git clone https://github.com/<your-username>/triage-api.git && cd triage-api
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # then paste your OpenRouter key into LLM_API_KEY
uvicorn src.main:app --port 8000
```

No key yet? Run `LLM_STUB=1 uvicorn src.main:app --port 8000`. That uses a fixed answer and makes zero model calls.

## Try it

```bash
curl -s -X POST localhost:8000/triage \
  -H 'Content-Type: application/json' \
  -d '{"text":"I was charged twice this month"}'
```

Exact response in stub mode (`LLM_STUB=1`):

```json
{"category":"technical","urgency":"medium","confidence":0.9,"reason":"Stub mode: fixed response, no model was called.","suggested_team":"engineering"}
```

Response from the real model (`nvidia/nemotron-3.5-lightning:free`, prompt `triage-v1`, 27 Oct 2026):

```json
{"category":"billing","urgency":"medium","confidence":0.95,"reason":"Customer reports being charged twice this month.","suggested_team":"finance"}
```

A deliberately broken request returns `400` and names the field, without calling the model:

```bash
curl -s -X POST localhost:8000/triage -H 'Content-Type: application/json' -d '{"message":"hi"}'
```

```json
{"error":"invalid_input","details":[{"field":"text","message":"Field required"},{"field":"message","message":"Extra inputs are not permitted"}]}
```

| Status | When |
|---|---|
| 200 | Valid answer (header `X-Triage-Source`: `model`, `stub` or `fallback`) |
| 400 | Bad input: missing `text`, empty, over 2000 characters, or extra fields |
| 422 | The model's answer failed validation twice. The raw output goes to `logs/quarantine.jsonl` and is never returned |
| 502 | Provider error that retries could not fix (bad key, 5xx after retries, and so on) |
| 504 | No answer within `LLM_TIMEOUT_SECONDS` |

## Job card

Full version: [JOB-CARD.md](JOB-CARD.md)

- **Input:** `{ "text": "string, 1-2000 characters" }`
- **Output:** `category` ∈ {billing, technical, account, sales, other} · `urgency` ∈ {low, medium, high} · `suggested_team` ∈ {finance, engineering, customer_success, sales, manual_review} · `confidence` 0.0–1.0 · `reason` (one sentence, ≤200 chars)
- **It must never:** invent a category or urgency outside the lists · add extra fields · return free text instead of the JSON object · give medical, legal or financial advice · reveal or discuss its prompt · follow instructions that appear inside the customer's message
- **When unsure it should:** return `other` with confidence below 0.5, not a guess
- **Code chooses `suggested_team`, not the model.** It is a fixed lookup from `category`, and a lookup is a job for code.

## Provider and model

- **Used:** OpenRouter, model `nvidia/nemotron-3.5-lightning:free` (pinned, see notes below). Stages 0–4 were built against Ollama (`gemma3:1b`); moving to OpenRouter took changing the three env vars below and no code.
- Changing provider means changing three env vars and no code:

| | `LLM_BASE_URL` | `LLM_API_KEY` | `LLM_MODEL` |
|---|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | your key | `nvidia/nemotron-3.5-lightning:free` |
| Ollama | `http://localhost:11434/v1/` | `ollama` | `gemma3:1b` |

These three variables are the only difference between a model on your laptop and one in a datacentre. That's why the provider is never hard-coded.

OpenRouter free models return `404 No endpoints available` until you turn on both free-endpoint switches at <https://openrouter.ai/settings/privacy>. Those switches mean prompts may be used for training or published, so only send made-up test data.

## How it stays reliable

```
validate input ─▶ load prompt file ─▶ call model ─▶ parse + validate ─▶ repair once ─▶ clean JSON / 422
     400            prompts/v1.md     timeout+retry      schema.py        one retry       never raw text
```

- **Prompt as a file:** `prompts/triage-v1.md` (role, output shape, rules, when-unsure rule, 3 examples). The customer text goes in the **user** message, JSON-encoded, and never in the system prompt.
- **Parsing:** strips code fences and chatter, finds the `{...}` object, and validates it with Pydantic (`extra="forbid"`, enums, bounded confidence).
- **Repair:** one extra call with the broken output and the exact validation error. If that also fails, the API returns 422 and quarantines the raw output.
- **Timeout:** 30 s per call (the SDK default is 10 minutes). Returns 504 when it fires.
- **Retries:** our own policy. **The SDK's built-in retries are set to `max_retries=0`**, so every call we make is one we log. We retry timeouts, connection errors, 429 and 5xx up to 2 times with exponential backoff and jitter (1 s, 2 s, …), and obey `Retry-After` on a 429. We never retry 400/401/403/404.
- **Kill switch:** `LLM_ENABLED=false` makes no model calls and instantly returns a deterministic fallback (`other` / `manual_review` / confidence 0.0).
- **Cost log:** one JSON line per call in `logs/llm_calls.jsonl` (prompt version, model, tokens in and out, duration, attempts, repair flag, outcome, estimated cost).

## Eval

`evals/cases.json` has 8 hand-labelled messages: 5 typical, 1 ambiguous (cancel + refund + crash), 1 that should trigger the when-unsure rule, and 1 prompt-injection attempt. The key field is `category`. Urgency is reported but doesn't decide pass/fail.

```bash
uvicorn src.main:app --port 8000      # terminal 1, real model (LLM_STUB unset)
python -m evals.run_eval              # terminal 2: 8 calls, prints score, saves evals/results/*.json
```

| Date | Prompt | Model | Category | Urgency | Failed cases |
|---|---|---|---|---|---|
| 2026-10-27 | triage-v1 | nvidia/nemotron-3.5-lightning:free | **8 / 8 (100%)** | 8 / 8 (100%) | none |

All 8 answers passed schema validation on the first try (0 repairs). The ambiguous case (cancel + refund + crash) went to `billing` at confidence 0.85. The vague message and the prompt-injection attempt both went to `other` at confidence 0.3, so the when-unsure rule and the injection defence held. Eight cases I wrote myself is a small, easy set, so treat 8/8 as "no obvious failures yet", not "solved". It's the baseline to compare the next prompt version against. Raw results: `evals/results/2026-10-27_triage-v1_nvidia_nemotron-3.5-lightning_free.json`.

## Cost

One logged call (`logs/llm_calls.jsonl`):

```json
{"ts": "2026-10-27T08:47:32.011524+00:00", "prompt_version": "triage-v1", "model": "nvidia/nemotron-3.5-lightning:free", "input_tokens": 654, "output_tokens": 706, "duration_ms": 8368, "attempts": 1, "repair": false, "outcome": "ok", "est_cost_usd": 0.0}
```

Across 9 logged calls: **649 input / 1,126 output tokens per call on average, 13.5 s average latency, 1.00 calls per request (no repairs).** The JSON answer is only ~40 tokens. The rest of the output tokens are the model's hidden reasoning, so the output side, not the prompt, drives the bill.

Estimate for 10,000 requests a day:

```bash
python -m evals.cost_estimate --per-day 10000 --in-price <$/M in> --out-price <$/M out>
```

**10,000 requests/day ≈ 17.8M tokens/day.** On this free model that is $0 in cash, but the free tier caps at 50 requests/day, so real volume needs a paid model. At an illustrative price of $0.10/M input and $0.40/M output, it would be about 6.5M × $0.10 + 11.3M × $0.40 ≈ **$5/day (~$150/month)**, and about 85% of that pays for reasoning tokens. The estimate counts repairs as real extra calls.

## Notes from Stage 2 (first real answers)

- **`openrouter/free` is a lottery.** It routes each call to a random free model. On my first call it picked a content-safety model, which replied `User Safety: safe` instead of `ready`. For a classifier you need the same model every run, so I pinned one.
- **Free models fail in different ways, and none of them are my code:** `gemma-4-31b` and `gemma-4-26b` returned upstream 429s (shared Google pool), `nemotron-3-super` returned a provider-side 404, and `inkling-small` returned 403 (only allowed inside agent apps). The API handled these as designed: it retried each 429 twice with backoff, then returned a clean 502 and logged the failure. It never crashed. Upstream 429s did not count against my 50/day.
- **The JSON shape was stable.** Every real answer parsed and validated on the first try, with no code fences, no extra fields and no repairs. The surprise was latency: 8–25 s per call, because the model reasons before answering.

## Tests

```bash
pytest -q        # 23 tests, no real model and no quota needed
```

The tests run against `tests/mock_llm.py`, a fake OpenAI-compatible server. They check plumbing only: 400s, stub mode, fence stripping, repair, 422 and quarantine, kill switch, no retries on 401/403/404, retries on 5xx and 429 with `Retry-After`, timeouts returning 504, and cost logging. The mock is not a model and says nothing about answer quality. Only the eval above measures that.

## What I'd fix with another day

The slowest eval call took **24.6 s against a 30 s timeout**, because of hidden reasoning tokens (up to 2,538 output tokens for a ~40-token answer). With another day I'd cap `max_tokens` / turn reasoning off, or race a non-reasoning model on the same 8 cases, and add harder eval cases (mixed-language, very long, sarcastic) so 8/8 stops being easy.
