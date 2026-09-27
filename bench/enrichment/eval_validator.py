"""Apply the production validator to benchmark answers; score filled cells against gold."""
import json, os, sqlite3, sys
from pathlib import Path
from bench import DB, GOLD_FILE, load_sample, matches, CORE
from qayem.enrichment import Task, validated_facts, missing_fields, INFERABLE_FIELDS
from qayem.models import Property

gold = json.loads(GOLD_FILE.read_text())
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
listings = {l["id"]: l for l in load_sample()}
cols = list(INFERABLE_FIELDS)
db = {}
for pid in listings:
    row = con.execute(f"select price, {', '.join(cols)} from properties where id=?", (pid,)).fetchone()
    miss = tuple(f for f, v in zip(cols, row[1:]) if v is None or (isinstance(v, str) and v.strip().casefold() in {"", "-", "unknown", "n/a", "null"}))
    db[pid] = (row[0], miss)
for rd in sys.argv[1:]:
    preds = json.loads((Path(rd) / "preds.json").read_text())
    stats = {"raw": [0, 0, 0], "validated": [0, 0, 0]}  # tp, bad, gold-required
    dropped_good, kept_bad = [], []
    for pid, l in listings.items():
        price, miss = db[pid]
        p = preds.get(str(pid)) or {}
        facts = []
        for f in CORE:
            v = p.get(f)
            if isinstance(v, dict): v = v.get("value")
            if v is None: continue
            facts.append({"field": f, "value": str(v).lower() if isinstance(v, bool) else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))})
        task = Task(pid, l["title"], l["description"], miss, price)
        validated, notes = validated_facts(facts, task)
        multi = any(n.startswith("Multi") for n in notes)
        raw = {f["field"]: p.get(f["field"]) for f in facts if f["field"] in miss}
        raw = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in raw.items()}
        for name, vals in (("raw", raw), ("validated", validated)):
            s = stats[name]
            for f in miss:
                acc = gold[str(pid)].get(f)
                optional = bool(acc) and None in acc
                if acc and not optional: s[2] += 1
                v = vals.get(f)
                if v is None: continue
                ok = bool(acc) and acc != [None] and matches(f, v, acc)
                s[0] += ok; s[1] += not ok
                if name == "validated" and not ok: kept_bad.append((pid, f, v, acc))
        for f, v in raw.items():
            acc = gold[str(pid)].get(f)
            if f not in validated and acc and acc != [None] and matches(f, v, acc) and not multi:
                reason = "price=down" if f == "down_payment" and price == v else ""
                dropped_good.append((pid, f, v, reason))
    for name, (tp, bad, g) in stats.items():
        print(f"{Path(rd).name} {name:9}: filled={tp+bad} correct={tp} wrong={bad} P={tp/max(1,tp+bad):.3f} coverage={tp/max(1,g):.3f}")
    print("   dropped correct:", dropped_good[:40])
    print("   kept wrong:", kept_bad)
