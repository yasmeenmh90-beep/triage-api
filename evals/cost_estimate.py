"""Average the cost log and project it to N requests a day.

    python -m evals.cost_estimate --per-day 10000 --in-price 0.10 --out-price 0.40

Prices are USD per 1M tokens (defaults: LLM_PRICE_IN_PER_M / LLM_PRICE_OUT_PER_M, i.e. 0 for Ollama).
Repairs are included, because a repair is a real second call you pay for.
"""
import argparse
import json
import os
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "logs" / "llm_calls.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-day", type=int, default=10_000)
    ap.add_argument("--in-price", type=float, default=float(os.getenv("LLM_PRICE_IN_PER_M", "0")))
    ap.add_argument("--out-price", type=float, default=float(os.getenv("LLM_PRICE_OUT_PER_M", "0")))
    args = ap.parse_args()

    lines = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()] if LOG.exists() else []
    calls = [l for l in lines if l["outcome"] != "provider_error"]
    if not calls:
        print("No successful calls in logs/llm_calls.jsonl yet — run some requests first.")
        return
    first_calls = [c for c in calls if not c["repair"]]
    repairs = len(calls) - len(first_calls)
    calls_per_request = len(calls) / max(len(first_calls), 1)
    avg_in = sum(c["input_tokens"] for c in calls) / len(calls)
    avg_out = sum(c["output_tokens"] for c in calls) / len(calls)
    avg_ms = sum(c["duration_ms"] or 0 for c in calls) / len(calls)
    per_call = avg_in / 1e6 * args.in_price + avg_out / 1e6 * args.out_price
    per_day = per_call * calls_per_request * args.per_day

    print(f"logged calls: {len(calls)} (repairs: {repairs}) -> {calls_per_request:.2f} calls per request")
    print(f"avg tokens per call: {avg_in:.0f} in / {avg_out:.0f} out, avg latency {avg_ms:.0f} ms")
    print(f"{args.per_day:,} requests/day ≈ {args.per_day * calls_per_request * (avg_in + avg_out) / 1e6:.1f}M tokens/day "
          f"≈ ${per_day:,.2f}/day at ${args.in_price}/M in, ${args.out_price}/M out")


if __name__ == "__main__":
    main()
