"""THROWAWAY read-only look at Jev's top probabilities in the saved pilot responses. No model call."""
import csv, json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from score_spike import LABELS, simple_records
from compare import gemma_records

FIELDS = ("topic", "intent", "severity")
low = {}  # review_id -> lowest top probability across the three labels
for line in open(HERE / "simple.jsonl", encoding="utf-8"):
    r = json.loads(line)
    a = r["response"]["answers"]
    low[r["review_id"]] = min(max(a[f]["probabilities"].values()) for f in FIELDS)

vals = sorted(low.values())
assert len(vals) == 100, len(vals)
assert len(set(vals)) > 5, "degenerate: top probabilities are all the same"
print("lowest top probability per review, 100 pilot reviews")
for cut in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
    print(f"  below {cut:.2f}: {sum(v < cut for v in vals):3d} of 100")

jev, gem = simple_records(), gemma_records()
rows = list(csv.DictReader(open(LABELS, encoding="utf-8-sig", newline="")))[:30]
rows = [r for r in rows if r["intent"].strip()]
right, wrong = [], []
for r in rows:
    j = jev[r["review_id"]]
    ok = j["topic"] == r["topic"] and j["intent"] == r["intent"] and int(j["severity"]) == int(r["severity"])
    (right if ok else wrong).append(low[r["review_id"]])
assert (len(right), len(wrong)) == (24, 5), (len(right), len(wrong))  # anchor: compare.py says 24/29
print(f"\nlabeled rows: {len(rows)}; Jev all-three right {len(right)}, wrong {len(wrong)}")
print("  lowest top probability on the 5 wrong rows:", sorted(round(v, 2) for v in wrong))
for cut in (0.6, 0.7, 0.8, 0.9):
    print(f"  cut {cut:.1f}: flags {sum(v < cut for v in wrong)} of 5 wrong, {sum(v < cut for v in right)} of 24 right")

dis = [rid for rid in low if any(str(jev[rid][f]) != str(gem[rid][f]) for f in FIELDS)]
assert len(dis) == 23, len(dis)  # anchor: engines matched on 77 of 100
print(f"\nJev and Gemma disagree on {len(dis)} of 100")
for cut in (0.6, 0.7, 0.8, 0.9):
    d = sum(low[rid] < cut for rid in dis)
    print(f"  cut {cut:.1f}: flags {d} of 23 disagreements, {sum(v < cut for v in vals) - d} of 77 agreements")
