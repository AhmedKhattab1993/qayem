"""Benchmark description extraction across Codex models, prompts and batch sizes.

  python bench.py sample                       # sample.jsonl (fixed seed)
  python bench.py run MODEL EFFORT SPEC BATCH [--evidence] [--tag T]
  python bench.py score RUNDIR [RUNDIR ...]    # against gold.json
"""

from __future__ import annotations

import argparse
import os
import json
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parents[1] / "qayem.db"
SET = os.environ.get("BENCH_SET", "dev")  # dev: tuning set; test: held-out confirmation set
SAMPLE_FILE = HERE / ("sample.jsonl" if SET == "dev" else f"sample_{SET}.jsonl")
GOLD_FILE = HERE / ("gold.json" if SET == "dev" else f"gold_{SET}.json")
RUNS = HERE / ("runs" if SET == "dev" else f"runs_{SET}")

PROPERTY_TYPES = ["apartment", "villa", "townhouse", "twinhouse", "penthouse", "duplex",
                  "studio", "chalet", "roof", "land", "building", "office", "shop", "clinic",
                  "warehouse", "farm", "factory", "house", "cabin", "loft", "pharmacy"]
FIELDS = {
    "purpose": {"enum": ["sale", "rent"]},
    "property_type": {"enum": PROPERTY_TYPES},
    "is_multi_unit": {"type": "boolean"},
    "is_resale": {"type": "boolean"},
    "price": {"type": "number"},
    "is_installment": {"type": "boolean"},
    "down_payment": {"type": "number"},
    "installment_months": {"type": "integer"},
    "area_m2": {"type": "number"},
    "bedrooms": {"type": "integer"},
    "bathrooms": {"type": "integer"},
    "finishing": {"enum": ["finished", "semi_finished", "core_shell", "lux", "super_lux",
                           "extra_super_lux", "flexi_finished"]},
    "delivery_status": {"enum": ["ready_to_move", "under_construction"]},
    "compound": {"type": "string"},
    "developer": {"type": "string"},
    "city": {"type": "string"},
    "seller_type": {"enum": ["owner", "broker", "developer"]},
}
CORE = ["property_type", "is_multi_unit", "is_resale", "price", "down_payment", "installment_months",
        "area_m2", "bedrooms", "bathrooms", "finishing", "delivery_status", "compound", "developer"]
FIELDSETS = {"all": list(FIELDS), "core": CORE}
NUMERIC = {"price", "down_payment", "installment_months", "area_m2", "bedrooms", "bathrooms"}
TEXTUAL = {"compound", "developer", "city"}
# Fields whose errors move the valuation or the headline number.
CRITICAL = ["property_type", "price", "down_payment", "installment_months", "area_m2",
            "finishing", "delivery_status", "compound", "is_resale", "is_multi_unit"]


def nullable(spec: dict) -> dict:
    if "enum" in spec:
        return {"type": ["string", "null"], "enum": [*spec["enum"], None]}
    return {"type": [spec["type"], "null"]}


def sparse_schema(evidence: bool, fields=None) -> dict:
    fact = {"field": {"type": "string", "enum": list(fields or FIELDS)}, "value": {"type": "string"}}
    if evidence:
        fact["evidence"] = {"type": "string"}
    fact_obj = {"type": "object", "properties": fact, "required": list(fact), "additionalProperties": False}
    item = {"type": "object", "properties": {"id": {"type": "integer"},
            "facts": {"type": "array", "items": fact_obj}},
            "required": ["id", "facts"], "additionalProperties": False}
    return {"type": "object", "properties": {"listings": {"type": "array", "items": item}},
            "required": ["listings"], "additionalProperties": False}


def parse_value(field: str, raw: str):
    raw = str(raw).strip()
    if raw.casefold() in {"", "null", "none"}:
        return None
    spec = FIELDS[field]
    try:
        if spec.get("type") == "boolean":
            return {"true": True, "false": False}.get(raw.casefold())
        if spec.get("type") == "integer":
            return int(float(raw.replace(",", "")))
        if spec.get("type") == "number":
            return float(raw.replace(",", ""))
    except ValueError:
        return None
    if "enum" in spec:
        return raw if raw in spec["enum"] else None
    return raw


def densify(item: dict, evidence: bool) -> dict:
    out = {"id": item.get("id")}
    for fact in item.get("facts", []):
        f = fact.get("field")
        if f in FIELDS and f not in out:
            v = parse_value(f, fact.get("value", ""))
            out[f] = {"value": v, "evidence": fact.get("evidence")} if evidence else v
    return out


def schema(evidence: bool, fields=None) -> dict:
    props: dict = {"id": {"type": "integer"}}
    for name in fields or FIELDS:
        spec = FIELDS[name]
        if evidence:
            props[name] = {
                "type": "object",
                "properties": {"value": nullable(spec), "evidence": {"type": ["string", "null"]}},
                "required": ["value", "evidence"], "additionalProperties": False,
            }
        else:
            props[name] = nullable(spec)
    item = {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}
    return {"type": "object", "properties": {"listings": {"type": "array", "items": item}},
            "required": ["listings"], "additionalProperties": False}


# ---------------------------------------------------------------- sampling

def sample(args) -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rng = random.Random(20260927)
    out = []
    for source, n in (("opensooq", 90), ("aqarexit", 40), ("semsar", 20)):
        rows = con.execute(
            "select id, source, title, description from properties where source=? "
            "and status='active' and trim(coalesce(description,''))<>'' order by id", (source,)
        ).fetchall()
        for pid, src, title, desc in rng.sample(rows, n):
            out.append({"id": pid, "source": src, "title": title or "", "description": desc})
    (HERE / "sample.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(f"sampled {len(out)} listings")


def load_sample() -> list[dict]:
    return [json.loads(l) for l in SAMPLE_FILE.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------- running

_DISABLE: list[str] | None = None


def lean_flags() -> list[str]:
    """Disable every optional Codex feature so the call carries minimal overhead."""
    global _DISABLE
    if _DISABLE is None:
        listing = subprocess.run(["codex", "features", "list"], capture_output=True, text=True).stdout
        _DISABLE = []
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[-1] == "true" and "removed" not in parts:
                _DISABLE += ["--disable", parts[0]]
    return _DISABLE


def call(model: str, effort: str, instructions: Path, schema_path: Path, listings: list[dict],
         timeout: int = 600, sparse: bool = False) -> dict:
    payload = [{"id": l["id"], "title": l["title"], "description": l["description"]} for l in listings]
    prompt = ("Extract the fields for each of these listings. Return exactly one entry per id"
              + (" and only the fields that are stated (omit null fields)" if sparse else "") + ".\n"
              + json.dumps(payload, ensure_ascii=False))
    with tempfile.TemporaryDirectory(prefix="qayem-bench-") as tmp:
        out = Path(tmp) / "answer.json"
        cmd = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
               "--skip-git-repo-check", "--sandbox", "read-only", "--model", model,
               "-c", f'model_reasoning_effort="{effort}"', "-c", 'approval_policy="never"',
               "-c", 'web_search="disabled"', "-c", f'model_instructions_file="{instructions}"',
               *lean_flags(), "--cd", tmp, "--output-schema", str(schema_path),
               "--output-last-message", str(out), "--json", "-"]
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"error": "timeout", "seconds": timeout, "usage": None, "listings": []}
        seconds = time.monotonic() - started
        usage = None
        for line in proc.stdout.splitlines():
            if '"turn.completed"' in line:
                usage = json.loads(line).get("usage")
        if proc.returncode != 0 or not out.is_file():
            return {"error": f"exit {proc.returncode}: {proc.stderr[-300:]}", "seconds": seconds,
                    "usage": usage, "listings": []}
        try:
            answer = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"error": "bad json", "seconds": seconds, "usage": usage, "listings": []}
        return {"error": None, "seconds": seconds, "usage": usage, "listings": answer.get("listings", [])}


def run(args) -> None:
    listings = load_sample()
    if args.limit:
        listings = listings[: args.limit]
    tag = args.tag or (f"{args.model}_{args.effort}_{args.spec}_b{args.batch}"
                       f"{'_ev' if args.evidence else ''}{'_sp' if args.sparse else ''}"
                       f"{'' if args.fieldset == 'all' else '_' + args.fieldset}")
    rundir = RUNS / tag
    rundir.mkdir(parents=True, exist_ok=True)
    schema_path = rundir / "schema.json"
    fields = FIELDSETS[args.fieldset]
    schema_path.write_text(json.dumps(sparse_schema(args.evidence, fields) if args.sparse else schema(args.evidence, fields)),
                           encoding="utf-8")
    instructions = HERE / f"spec_{args.spec}.md"
    batches = [listings[i:i + args.batch] for i in range(0, len(listings), args.batch)]

    def one(batch):
        result = call(args.model, args.effort, instructions, schema_path, batch, sparse=args.sparse)
        wanted = {l["id"] for l in batch}
        got = {r.get("id") for r in result["listings"]}
        result["missing_ids"] = sorted(wanted - got)
        result["ids"] = sorted(wanted)
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, batches))
    preds = {}
    for r in results:
        for item in r["listings"]:
            if item.get("id") in set(r["ids"]):
                preds[item["id"]] = densify(item, args.evidence) if args.sparse else item
    (rundir / "preds.json").write_text(json.dumps(preds, ensure_ascii=False, indent=1), encoding="utf-8")
    calls = [{k: r[k] for k in ("error", "seconds", "usage", "missing_ids", "ids")} for r in results]
    meta = {"model": args.model, "effort": args.effort, "spec": args.spec, "batch": args.batch,
            "evidence": args.evidence, "sparse": args.sparse, "fieldset": args.fieldset, "n": len(listings)}
    (rundir / "calls.json").write_text(json.dumps({"meta": meta, "calls": calls}, indent=1), encoding="utf-8")
    errors = sum(1 for r in results if r["error"])
    print(f"{tag}: {len(preds)}/{len(listings)} listings, {errors} failed calls")


# ---------------------------------------------------------------- scoring

ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": None})
PREFIX = re.compile(r"^(كمبوند|كومباوند|كمباوند|كومبوند|compound|مشروع|مدينه|city of|شركه|مجموعه|group)\s+")
SUFFIX = re.compile(r"\s+(compound|كمبوند|group|جروب|للتطوير العقاري|developments?|بحري|قبلي|الشرقيه|الغربيه)$")


def norm_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).casefold().translate(ARABIC_FOLD)
    value = "".join(ch for ch in value if not unicodedata.category(ch).startswith("M"))
    value = re.sub(r"[#_()\[\]\"'«»,،.\-–—|/]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return SUFFIX.sub("", PREFIX.sub("", value).strip()).strip()


def text_match(pred: str, gold: str) -> bool:
    """Same place/name: equal after folding, one contains the other, or near-identical spelling."""
    from difflib import SequenceMatcher
    a, b = norm_text(pred), norm_text(gold)
    if not a or not b:
        return False
    if a == b or f" {b} " in f" {a} " or f" {a} " in f" {b} ":
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.85


def value_of(pred: dict, field: str, evidence: bool):
    v = pred.get(field)
    ev = None
    if isinstance(v, dict):
        v, ev = v.get("value"), v.get("evidence")
    if field == "is_multi_unit" and v is False:
        v = None  # only a positive multi-unit flag is used downstream
    return v, ev


def matches(field: str, pred, accepted: list) -> bool:
    for gold in accepted:
        if field in NUMERIC:
            try:
                if abs(float(pred) - float(gold)) <= max(0.5, 0.01 * abs(float(gold))):
                    return True
            except (TypeError, ValueError):
                pass
        elif field in TEXTUAL:
            if gold is not None and text_match(pred, gold):
                return True
        elif pred == gold:
            return True
    return False


def evidence_ok(ev, listing: dict) -> bool:
    if not ev:
        return False
    return norm_text(ev) in norm_text(listing["title"] + " " + listing["description"])


def missing_in_db() -> dict[int, set[str]]:
    """Fields each sampled listing lacks in the database: the only cells production would fill."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cols = [f for f in CORE if f != "is_multi_unit"]
    out = {}
    for l in load_sample():
        row = con.execute(f"select {', '.join(cols)} from properties where id=?", (l["id"],)).fetchone()
        out[l["id"]] = {"is_multi_unit"} | {
            f for f, v in zip(cols, row)
            if v is None or (isinstance(v, str) and v.strip().casefold() in {"", "-", "unknown", "n/a", "null"})}
    return out


def score_run(rundir: Path, gold: dict, listings: dict, validate: bool, fields, only=None) -> dict:
    preds = json.loads((rundir / "preds.json").read_text(encoding="utf-8"))
    meta = json.loads((rundir / "calls.json").read_text())
    evidence = meta["meta"]["evidence"]
    per = {f: {"tp": 0, "tp_req": 0, "wrong": 0, "halluc": 0, "fn": 0, "gold": 0} for f in fields}
    errors = []
    for sid, g in gold.items():
        p = preds.get(sid) or preds.get(str(sid)) or {}
        for f in fields:
            if only is not None and f not in only[int(sid)]:
                continue
            accepted = g.get(f)
            if f == "is_multi_unit" and accepted:
                accepted = [x for x in accepted if x is not False] or None
                if accepted == [None]:
                    accepted = None
            v, ev = value_of(p, f, evidence)
            if v is not None and validate and evidence and not evidence_ok(ev, listings[int(sid)]):
                v = None
            s = per[f]
            optional = bool(accepted) and None in accepted  # either null or a listed value is fine
            if accepted and not optional:
                s["gold"] += 1
            if v is None:
                if accepted and not optional:
                    s["fn"] += 1
            elif not accepted or accepted == [None]:
                s["halluc"] += 1
                errors.append((sid, f, v, None))
            elif matches(f, v, accepted):
                s["tp"] += 1
                s["tp_req"] += not optional
            else:
                s["wrong"] += 1
                errors.append((sid, f, v, accepted))
    return {"per": per, "errors": errors, "meta": meta}


def usage_stats(meta: dict) -> dict:
    calls = meta["calls"]
    n = meta["meta"]["n"]
    tot = {"input": 0, "cached": 0, "output": 0, "reasoning": 0}
    for c in calls:
        u = c.get("usage") or {}
        tot["input"] += u.get("input_tokens", 0)
        tot["cached"] += u.get("cached_input_tokens", 0)
        tot["output"] += u.get("output_tokens", 0)
        tot["reasoning"] += u.get("reasoning_output_tokens", 0)
    secs = sum(c["seconds"] for c in calls)
    failed = sum(1 for c in calls if c["error"])
    missing = sum(len(c["missing_ids"]) for c in calls)
    return {"per_listing": {k: v / n for k, v in tot.items()}, "calls": len(calls),
            "failed": failed, "missing": missing, "sec_per_call": secs / max(1, len(calls))}


def summarize(per: dict, fields) -> tuple[float, float, int]:
    tp = sum(per[f]["tp"] for f in fields)
    bad = sum(per[f]["wrong"] + per[f]["halluc"] for f in fields)
    gold = sum(per[f]["gold"] for f in fields)
    tp_req = sum(per[f]["tp_req"] for f in fields)
    return (tp / (tp + bad) if tp + bad else 1.0), (tp_req / gold if gold else 0.0), bad


def score(args) -> None:
    gold = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    listings = {l["id"]: l for l in load_sample()}
    for rd in args.rundirs:
        rundir = Path(rd)
        if not (rundir / "calls.json").exists():
            continue
        for validate in ((False, True) if json.loads((rundir / "calls.json").read_text())["meta"]["evidence"] else (False,)):
            res = score_run(rundir, gold, listings, validate, FIELDSETS[args.fieldset],
                            missing_in_db() if args.applied else None)
            u = usage_stats(res["meta"])
            p_all, r_all, bad_all = summarize(res["per"], list(res["per"]))
            p_c, r_c, bad_c = summarize(res["per"], [f for f in CRITICAL if f in res["per"]])
            pl = u["per_listing"]
            print(f"{rundir.name}{' +evcheck' if validate else ''}: "
                  f"P={p_all:.3f} R={r_all:.3f} errors={bad_all} | critical P={p_c:.3f} R={r_c:.3f} errors={bad_c} | "
                  f"tok/listing in={pl['input']:.0f} (uncached {pl['input']-pl['cached']:.0f}) "
                  f"out={pl['output']:.0f} reas={pl['reasoning']:.0f} | calls={u['calls']} "
                  f"failed={u['failed']} missing={u['missing']} {u['sec_per_call']:.0f}s/call")
            if args.fields:
                for f, s in res["per"].items():
                    tp, bad = s["tp"], s["wrong"] + s["halluc"]
                    print(f"   {f:18} gold={s['gold']:3} tp={tp:3} wrong={s['wrong']:2} halluc={s['halluc']:2} "
                          f"fn={s['fn']:3} P={tp/(tp+bad) if tp+bad else 1:.2f}")
            if args.errors:
                for e in res["errors"]:
                    print("   ERR", e)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)
    s = sub.add_parser("sample"); s.set_defaults(fn=sample)
    r = sub.add_parser("run")
    r.add_argument("model"); r.add_argument("effort"); r.add_argument("spec"); r.add_argument("batch", type=int)
    r.add_argument("--evidence", action="store_true"); r.add_argument("--tag")
    r.add_argument("--sparse", action="store_true")
    r.add_argument("--fieldset", default="all", choices=list(FIELDSETS))
    r.add_argument("--workers", type=int, default=6); r.add_argument("--limit", type=int)
    r.set_defaults(fn=run)
    sc = sub.add_parser("score"); sc.add_argument("rundirs", nargs="+")
    sc.add_argument("--fields", action="store_true"); sc.add_argument("--errors", action="store_true")
    sc.add_argument("--fieldset", default="core", choices=list(FIELDSETS))
    sc.add_argument("--applied", action="store_true", help="only cells missing in the DB")
    sc.set_defaults(fn=score)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
