import json, re, sqlite3, sys, os
sys.path.insert(0, "/tmp"); 
from bench import DB, load_sample, GOLD_FILE
from qayem import enrichment as E
exec(open("/tmp/funnel.py").read().split("def missing")[0].split("TEMPLATE =")[1].join(["TEMPLATE =", ""]) if False else "")
RELEVANT = ["property_type", "area_m2", "is_resale", "finishing", "delivery_status", "compound", "down_payment", "installment_months"]
src = open("/tmp/funnel.py").read()
SIGNAL = eval(src[src.index("SIGNAL = ") + 9: src.index("}\ndef missing") + 1], {"E": E})
gold = json.loads(GOLD_FILE.read_text())
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
kept = lost = 0; lost_list = []
for l in load_sample():
    row = con.execute(f"select {', '.join(RELEVANT)} from properties where id=?", (l["id"],)).fetchone()
    miss = [f for f, v in zip(RELEVANT, row) if E.is_missing(f, v)]
    text = E.listing_text(l["title"], l["description"]); t2 = text + "\n" + E._folded(text)
    passes = any(re.search(SIGNAL[f], t2, re.I) for f in miss)
    for f in miss:
        acc = gold[str(l["id"])].get(f)
        if acc and None not in acc:
            if passes: kept += 1
            else: lost += 1; lost_list.append((l["id"], f, acc))
print(f"gold facts on missing valuation fields: kept={kept} lost={lost}", lost_list[:10])
