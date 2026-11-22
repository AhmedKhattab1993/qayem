#!/usr/bin/env python3
"""Monthly 20-question AI-assistant citation benchmark (docs/STRATEGY.md, section 9 & 13).

    .venv/bin/python scripts/geo-benchmark.py list
    .venv/bin/python scripts/geo-benchmark.py record --month 2026-11 --assistant chatgpt --id 1 --cited
    .venv/bin/python scripts/geo-benchmark.py score --month 2026-11

Results are stored under `.artifacts/geo-benchmark/<month>.json` to track the ≥3/20 target.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "src" / "qayem" / "data" / "geo_questions.json"
OUT = ROOT / ".artifacts" / "geo-benchmark"
ASSISTANTS = ("chatgpt", "perplexity", "gemini", "copilot")


def load_questions() -> list[dict]:
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))


def path_for(month: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / f"{month}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="Print the 20 monthly buyer questions")
    rec = sub.add_parser("record", help="Record whether an assistant cited Qayem for one question")
    rec.add_argument("--month", default=date.today().strftime("%Y-%m"))
    rec.add_argument("--assistant", choices=ASSISTANTS, required=True)
    rec.add_argument("--id", type=int, required=True)
    rec.add_argument("--cited", action="store_true")
    rec.add_argument("--url", default="")
    rec.add_argument("--note", default="")
    sc = sub.add_parser("score", help="Score citation rate for a month")
    sc.add_argument("--month", default=date.today().strftime("%Y-%m"))
    args = parser.parse_args()

    questions = load_questions()
    if args.cmd == "list":
        for q in questions:
            print(f"{q['id']:2d}. [{q['lang']}/{q['buyer']}] {q['question']}")
        return
    file = path_for(args.month)
    data = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {"month": args.month, "results": {}}
    if args.cmd == "record":
        entry = data["results"].setdefault(str(args.id), {})
        entry[args.assistant] = {"cited": bool(args.cited), "url": args.url, "note": args.note}
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {args.month} #{args.id} ({args.assistant}): cited={args.cited}")
        return
    cited_any = sum(1 for q in questions if any(v.get("cited") for v in data["results"].get(str(q["id"]), {}).values()))
    by_assistant = {
        a: sum(1 for q in questions if data["results"].get(str(q["id"]), {}).get(a, {}).get("cited"))
        for a in ASSISTANTS
    }
    print(json.dumps({"month": args.month, "questions": len(questions), "cited_in_any": cited_any,
                      "target": 3, "by_assistant": by_assistant}, indent=2))


if __name__ == "__main__":
    main()
