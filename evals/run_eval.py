"""Run evals/cases.json through the RUNNING endpoint and score it.

    uvicorn src.main:app --port 8000          # in one terminal, with the real model
    python -m evals.run_eval                  # in another

Key field = category. Urgency is reported too but does not decide pass/fail.
Results are saved to evals/results/<date>_<prompt_version>_<model>.json.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/triage")
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    rows, cat_ok, urg_ok = [], 0, 0

    with httpx.Client(timeout=120) as http:
        for case in cases:
            r = http.post(args.url, json={"text": case["text"]})
            try:
                body = r.json()
            except ValueError:
                body = {"raw": r.text[:200]}
            got_cat, got_urg = body.get("category"), body.get("urgency")
            c_pass = r.status_code == 200 and got_cat == case["expected"]["category"]
            u_pass = r.status_code == 200 and got_urg == case["expected"]["urgency"]
            cat_ok += c_pass
            urg_ok += u_pass
            rows.append({"id": case["id"], "status": r.status_code,
                         "source": r.headers.get("X-Triage-Source"),
                         "expected": case["expected"], "got": body,
                         "category_pass": c_pass, "urgency_pass": u_pass})
            mark = "PASS" if c_pass else "FAIL"
            print(f"[{mark}] {case['id']:<28} expected={case['expected']['category']:<9} "
                  f"got={got_cat!s:<9} conf={body.get('confidence')} status={r.status_code}")

    n = len(cases)
    version = os.getenv("PROMPT_VERSION", "triage-v1")
    model = os.getenv("LLM_MODEL", "unknown")
    sources = {row["source"] for row in rows}
    print(f"\ncategory: {cat_ok}/{n} ({cat_ok / n:.0%})   urgency: {urg_ok}/{n} ({urg_ok / n:.0%})")
    print(f"prompt={version} model={model} date={datetime.now():%Y-%m-%d}")
    failed = [row["id"] for row in rows if not row["category_pass"]]
    if failed:
        print("failed:", ", ".join(failed))
    if sources - {"model"}:
        print(f"WARNING: some answers came from {sources - {'model'}}, not the model — this is not a real score.")

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "_", model)
    out = out_dir / f"{datetime.now():%Y-%m-%d}_{version}_{safe_model}.json"
    out.write_text(json.dumps({"prompt_version": version, "model": model,
                               "category_correct": cat_ok, "urgency_correct": urg_ok,
                               "total": n, "rows": rows}, indent=2), encoding="utf-8")
    print(f"saved {out.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
