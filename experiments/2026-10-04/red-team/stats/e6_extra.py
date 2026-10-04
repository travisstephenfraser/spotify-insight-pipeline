"""E6 extra: projection onto the exact-text-reuse workload (484,189 distinct texts), tail, and E5 noise arithmetic."""

import csv
import random
import statistics
import sys

csv.field_size_limit(sys.maxsize)
D = "/Users/travis/Developer/pepeclass/assign5-multiagent/feed/Final Assignment - Spotify Reviews Dataset/"


def load(fn):
    with open(D + fn, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


full = [r for r in load("spotify_reviews_18months.csv") if r["review_text"].strip()]
cost = load("cost_100.csv")
texts = [r["review_text"] for r in full]
row_len = [len(t) for t in texts]
distinct = set(texts)
dist_len = [len(t) for t in distinct]
N, K = len(row_len), len(dist_len)
row_mean, dist_mean = statistics.fmean(row_len), statistics.fmean(dist_len)
cost_mean = statistics.fmean(len(r["review_text"]) for r in cost)
tot_rows, tot_dist = sum(row_len), sum(dist_len)
print(
    f"total chars, all {N} nonempty rows (no reuse): {tot_rows:,}  mean {row_mean:.2f}"
)
print(
    f"total chars, {K} distinct texts (with reuse):   {tot_dist:,}  mean {dist_mean:.2f}"
)
print(f"cost_100 mean chars per review: {cost_mean:.2f}")
print("\nProjection of TEXT volume from cost_100:")
print(
    f"  no reuse:   {N} x {cost_mean:.2f} = {N * cost_mean:,.0f} vs true {tot_rows:,}  -> error {(N * cost_mean / tot_rows - 1) * 100:+.1f}%"
)
print(
    f"  with reuse: {K} x {cost_mean:.2f} = {K * cost_mean:,.0f} vs true {tot_dist:,}  -> error {(K * cost_mean / tot_dist - 1) * 100:+.1f}%"
)
print(
    f"  expected error of a random row sample projected onto distinct texts: {(row_mean / dist_mean - 1) * 100:+.1f}% (systematic, not noise)"
)

random.seed(7)
REPS = 50000
inside_rows = inside_dist = 0
for _ in range(REPS):
    m = sum(random.sample(row_len, 100)) / 100
    if 0.8 <= m / row_mean <= 1.2:
        inside_rows += 1
    if 0.8 <= m / dist_mean <= 1.2:
        inside_dist += 1
print(f"\nBootstrap, {REPS} random 100-row samples:")
print(
    f"  within +/-20% of the per-row mean (no-reuse projection):        {inside_rows / REPS * 100:.1f}%"
)
print(
    f"  within +/-20% of the distinct-text mean (reuse projection):     {inside_dist / REPS * 100:.1f}%"
)

print(
    "\nPropagation to input tokens for the reuse projection (text ~ chars/4; per-review prompt overhead assumed, range shown):"
)
for ov in (0, 20, 50, 100, 300):
    t, c = dist_mean / 4 + ov, cost_mean / 4 + ov
    print(
        f"  overhead {ov:>3} tok/review: true {t:6.1f} vs pilot {c:6.1f} -> {(c / t - 1) * 100:+.1f}%"
    )

over500 = sum(1 for x in row_len if x > 500)
print(
    f"\nTail: rows longer than 500 chars: {over500} ({over500 / N * 100:.3f}%), longest {max(row_len)}; cost_100 longest {max(len(r['review_text']) for r in cost)}"
)
nonascii_full = sum(1 for t in texts if any(ord(ch) > 127 for ch in t)) / N
nonascii_cost = (
    sum(1 for r in cost if any(ord(ch) > 127 for ch in r["review_text"])) / 100
)
print(
    f"Share of reviews containing any non-ASCII character: full {nonascii_full * 100:.1f}%, cost_100 {nonascii_cost * 100:.1f}%"
)
print(
    "NOT MEASURED: real tokenizer counts (no tokenizer in the standard library); chars, bytes and words are proxies."
)

# -------- E5 arithmetic: how a single imperfect annotator distorts measured accuracy
print(
    "\nE5 arithmetic (stated model): classifier true accuracy c; lone annotator's label is right with prob a;"
)
print(
    "when either is wrong it picks uniformly among the other K-1 labels, independently. K=8 (topic), K=5 (intent)."
)
for K_ in (8, 5):
    for a in (1.0, 0.95, 0.90, 0.85):
        for c in (0.80, 0.70):
            agree = c * a + (1 - c) * (1 - a) / (K_ - 1)
            print(
                f"  K={K_} annotator acc={a:.2f} classifier true acc={c:.2f} -> measured agreement {agree * 100:.1f}%  (shift {(agree - c) * 100:+.1f} pts)"
            )
print(
    "  Independent-error case only. If the annotator shares the classifier's reading of ambiguous items (same person wrote the prompt), measured agreement is inflated instead; one annotator cannot tell which."
)
