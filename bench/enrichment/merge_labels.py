"""Merge two independent labelers into gold.json; print disagreements to adjudicate.

Agreement (same normalized value, including both null) becomes gold. Each
disagreement is written to disagreements.json with both candidates; an
adjudication file (adjudicated.json: {"id|field": value-or-list-or-null}) is
applied on top.
"""

import json
from pathlib import Path

from bench import CORE, FIELDS, GOLD_FILE, HERE, RUNS, SET, load_sample, matches

listings = {l["id"]: l for l in load_sample()}
ref = json.loads((RUNS / "ref_astra_high/preds.json").read_text(encoding="utf-8"))
claude = {}
prefix, chunks = ("claude_chunk", 3) if SET == "dev" else (f"claude_{SET}_chunk", 4)
for i in range(chunks):
    claude.update(json.loads((HERE / f"label/{prefix}{i}.json").read_text(encoding="utf-8")))
fields = list(FIELDS) if SET == "dev" else CORE
suffix = "" if SET == "dev" else f"_{SET}"
adj_path = HERE / f"adjudicated{suffix}.json"
adjudicated = json.loads(adj_path.read_text(encoding="utf-8")) if adj_path.exists() else {}


def ref_value(pid, field):
    v = (ref.get(str(pid)) or {}).get(field)
    return v.get("value") if isinstance(v, dict) else v


gold, open_items = {}, []
for pid, listing in listings.items():
    g = {}
    for field in fields:
        a, b = ref_value(pid, field), (claude.get(str(pid)) or {}).get(field)
        if field == "is_multi_unit":  # only a positive flag is meaningful
            a, b = (a or None), (b or None)
        key = f"{pid}|{field}"
        if key in adjudicated:
            v = adjudicated[key]
            g[field] = None if v is None else (v if isinstance(v, list) else [v])
        elif a is None and b is None:
            g[field] = None
        elif a is not None and b is not None and matches(field, a, [b]):
            g[field] = [b] if a == b else [b, a]
        else:
            open_items.append({"key": key, "astra": a, "claude": b,
                               "title": listing["title"], "description": listing["description"],
                               "claude_note": (claude.get(str(pid)) or {}).get("_notes", "")})
            g[field] = "OPEN"
    gold[str(pid)] = g

(HERE / f"disagreements{suffix}.json").write_text(json.dumps(open_items, ensure_ascii=False, indent=1), encoding="utf-8")
if not open_items:
    GOLD_FILE.write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
cells = len(listings) * len(fields)
print(f"{cells} cells, {len(open_items)} open disagreements"
      + ("" if open_items else " -> gold.json written"))
