"""Score 'accept only when runs agree' across two or more run directories."""
import json
import sys
import tempfile
from pathlib import Path

from bench import CORE, matches, value_of

runs = [Path(r) for r in sys.argv[1:]]
preds = [json.loads((r / "preds.json").read_text(encoding="utf-8")) for r in runs]
merged = {}
for sid in set().union(*preds):
    out = {"id": int(sid)}
    for f in CORE:
        vals = [value_of(p.get(sid) or {}, f, True)[0] for p in preds]
        if all(v is not None for v in vals) and all(matches(f, v, [vals[0]]) for v in vals[1:]):
            out[f] = vals[0]
    merged[sid] = out
tmp = Path(tempfile.mkdtemp(prefix="consensus-", dir=runs[0].parent))
(tmp / "preds.json").write_text(json.dumps(merged, ensure_ascii=False))
metas = [json.loads((r / "calls.json").read_text()) for r in runs]
calls = [c for m in metas for c in m["calls"]]
meta = dict(metas[0]["meta"], evidence=False)
(tmp / "calls.json").write_text(json.dumps({"meta": meta, "calls": calls}))
print(tmp)
