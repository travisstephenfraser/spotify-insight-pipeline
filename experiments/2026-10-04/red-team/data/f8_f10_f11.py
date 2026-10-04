"""F8 (hash order vs samples), F10 (lengths / 10-row windows), F11 (sample consistency + checksums)."""

import csv
import hashlib
import io
import json
import os
from common import DATA, FIELDS, load, trunc

manifest = json.load(open(DATA + "/manifest.json", encoding="utf-8"))
SEED = manifest["samples"]["seed"]
print("seed:", SEED)

header, rows = load()
assert header == FIELDS
by_id = {}
dup_ids = 0
for r in rows:
    if r[0] in by_id:
        dup_ids += 1
    by_id[r[0]] = r
print(
    "rows",
    len(rows),
    "unique ids",
    len(by_id),
    "duplicate ids",
    dup_ids,
    "blank ids",
    sum(1 for r in rows if not r[0]),
)
print("rows with != 6 fields:", sum(1 for r in rows if len(r) != 6))
print(
    "ratings outside 1-5:",
    sum(1 for r in rows if r[2] not in {"1", "2", "3", "4", "5"}),
)


def rank(rid):
    return int.from_bytes(hashlib.sha256((SEED + ":" + rid).encode()).digest(), "big")


samples = {}
for name in [
    "golden_50_to_label.csv",
    "cost_100.csv",
    "checkpoint_500.csv",
    "analysis_10000.csv",
]:
    h, rs = load(DATA + "/" + name)
    samples[name] = (h, rs)
    print(name, "rows", len(rs), "cols", len(h), h[:6] == FIELDS)

gold_ids = [r[0] for r in samples["golden_50_to_label.csv"][1]]
cost_ids = [r[0] for r in samples["cost_100.csv"][1]]
chk_ids = [r[0] for r in samples["checkpoint_500.csv"][1]]
ana_ids = [r[0] for r in samples["analysis_10000.csv"][1]]
print("\n== sample nesting ==")
print(
    "cost == checkpoint[:100]:",
    cost_ids == chk_ids[:100],
    "| checkpoint == analysis[:500]:",
    chk_ids == ana_ids[:500],
)
print(
    "gold ∩ analysis:",
    len(set(gold_ids) & set(ana_ids)),
    "| unique gold",
    len(set(gold_ids)),
    "unique analysis",
    len(set(ana_ids)),
)
expected = gold_ids + cost_ids + chk_ids[100:] + ana_ids[500:]
print("expected sequence length:", len(expected), "unique:", len(set(expected)))
print("all sample ids present in full file:", all(i in by_id for i in expected))

# ---------------- F8 ----------------
print("\n== F8 ==")
ranked_all = sorted(((rank(r[0]), r[0]) for r in rows))
order_all = [rid for _, rid in ranked_all]
prefix = order_all[: len(expected)]
print(
    "ALL-rows hash order prefix == golden+cost+checkpoint rest+analysis rest:",
    prefix == expected,
)
if prefix != expected:
    first_bad = next(i for i, (a, b) in enumerate(zip(prefix, expected)) if a != b)
    print(
        "  first mismatch at position",
        first_bad,
        "(0-based); all-rows id:",
        prefix[first_bad],
        "expected:",
        expected[first_bad],
    )
max_rank_sample = max(rank(i) for i in expected)
sample_set = set(expected)
intruders = [
    (rk, rid)
    for rk, rid in ranked_all
    if rk <= max_rank_sample and rid not in sample_set
]
print(
    "full-file rows with hash <= max sample hash that are NOT in the samples:",
    len(intruders),
)
for rk, rid in intruders:
    pos = order_all.index(rid)
    r = by_id[rid]
    print(
        f"   intruder at all-rows position {pos} (0-based): id={rid} text={r[1]!r} rating={r[2]} ts={r[5]}"
    )
print(
    "rows inside sample hash range (all rows):",
    sum(1 for rk, _ in ranked_all if rk <= max_rank_sample),
)
# eligible population per prepare_dataset.py: unique id, nonempty text (strip), nonblank id, rating in 1..5
elig = [r for r in rows if r[1].strip() and r[0] and r[2] in {"1", "2", "3", "4", "5"}]
order_elig = [rid for _, rid in sorted((rank(r[0]), r[0]) for r in elig)]
print(
    "eligible rows:",
    len(elig),
    "| eligible hash order prefix == expected:",
    order_elig[: len(expected)] == expected,
)
# where do the 13 empty rows fall in the all-rows order
empt = [r for r in rows if not r[1].strip()]
pos_of = {rid: i for i, rid in enumerate(order_all)}
print(
    "positions (0-based, all-rows order) of the",
    len(empt),
    "empty rows:",
    sorted(pos_of[r[0]] for r in empt),
)
# file order vs hash order within samples
print(
    "analysis file is in ascending hash order:",
    [rank(i) for i in ana_ids] == sorted(rank(i) for i in ana_ids),
)
print(
    "golden file is in ascending hash order:",
    [rank(i) for i in gold_ids] == sorted(rank(i) for i in gold_ids),
)
print(
    "max golden hash < min analysis hash:",
    max(rank(i) for i in gold_ids) < min(rank(i) for i in ana_ids),
)
# rank ties
print(
    "rank collisions among all rows:",
    len(ranked_all) - len({rk for rk, _ in ranked_all}),
)

# ---------------- F10 ----------------
print("\n== F10 ==")
lens = sorted(len(r[1]) for r in rows)
blens = sorted(len(r[1].encode("utf-8")) for r in rows)
n = len(lens)


def pct(sorted_vals, q):
    # nearest-rank percentile
    import math

    k = max(1, math.ceil(q * len(sorted_vals)))
    return sorted_vals[k - 1]


print(
    "chars: max",
    lens[-1],
    "p99.9",
    pct(lens, 0.999),
    "p99",
    pct(lens, 0.99),
    "p95",
    pct(lens, 0.95),
    "p50",
    pct(lens, 0.5),
    "mean",
    round(sum(lens) / n, 2),
    "total",
    sum(lens),
)
print(
    "utf-8 bytes: max",
    blens[-1],
    "p99.9",
    pct(blens, 0.999),
    "p99",
    pct(blens, 0.99),
    "mean",
    round(sum(blens) / n, 2),
)
ne_lens = sorted(len(r[1]) for r in rows if r[1].strip())
print(
    "nonempty-only chars: max",
    ne_lens[-1],
    "p99.9",
    pct(ne_lens, 0.999),
    "p99",
    pct(ne_lens, 0.99),
)
print(
    "rows >500 chars:",
    sum(1 for x in lens if x > 500),
    "| >1000:",
    sum(1 for x in lens if x > 1000),
    "| >2000:",
    sum(1 for x in lens if x > 2000),
)
longest = sorted(rows, key=lambda r: -len(r[1]))[:3]
for r in longest:
    print("   longest: len", len(r[1]), "bytes", len(r[1].encode()), trunc(r[1]))
bytes_longest = sorted(rows, key=lambda r: -len(r[1].encode()))[:1]
for r in bytes_longest:
    print("   most bytes: chars", len(r[1]), "bytes", len(r[1].encode()), trunc(r[1]))


def windows(order, k, label):
    L = [len(by_id[i][1]) for i in order]
    B = [len(by_id[i][1].encode("utf-8")) for i in order]
    # sliding
    s = sum(L[:k])
    best = s
    for j in range(k, len(L)):
        s += L[j] - L[j - k]
        if s > best:
            best = s
    sb = sum(B[:k])
    bestb = sb
    for j in range(k, len(B)):
        sb += B[j] - B[j - k]
        if sb > bestb:
            bestb = sb
    # aligned batches
    al = max(sum(L[j : j + k]) for j in range(0, len(L), k))
    alb = max(sum(B[j : j + k]) for j in range(0, len(B), k))
    print(
        f"   {label}, k={k}: sliding max chars {best} (bytes {bestb}) | aligned-batch max chars {al} (bytes {alb}) | mean batch chars {sum(L) / (len(L) / k):.1f}"
    )


nonempty_set = {r[0] for r in rows if r[1].strip()}
order_ne = [i for i in order_all if i in nonempty_set]
for k in (10, 50):
    windows(order_all, k, "hash order ALL rows")
    windows(order_ne, k, "hash order nonempty rows")
# worst possible: 10 longest distinct texts
distinct_lens = sorted({r[1] for r in rows if r[1].strip()}, key=len, reverse=True)
print(
    "   adversarial upper bound, 10 longest rows total chars:",
    sum(sorted((len(r[1]) for r in rows), reverse=True)[:10]),
    "| 50 longest:",
    sum(sorted((len(r[1]) for r in rows), reverse=True)[:50]),
)
# distinct-text ordering (if the pipeline batches distinct texts in first-occurrence hash order)
seen = set()
order_distinct = []
for i in order_ne:
    t = by_id[i][1]
    if t not in seen:
        seen.add(t)
        order_distinct.append(i)
print("   distinct texts in hash order:", len(order_distinct))
for k in (10, 50):
    windows(order_distinct, k, "hash order, first occurrence of each distinct text")

# ---------------- F11 ----------------
print("\n== F11 ==")
for name, (h, rs) in samples.items():
    mism = 0
    missing = 0
    for r in rs:
        full = by_id.get(r[0])
        if full is None:
            missing += 1
        elif r[:6] != full:
            mism += 1
    extra = ""
    if len(h) > 6:
        nonblank = sum(1 for r in rs if any(c != "" for c in r[6:]))
        extra = f"| extra cols {h[6:]} rows with any non-blank extra col: {nonblank}"
    print(
        f"{name}: rows {len(rs)} missing-from-full {missing} field-mismatch(first 6 cols) {mism} {extra}"
    )
    # byte-level: regenerate the sample file from the full-file rows with the builder's writer settings
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(h)
    for r in rs:
        w.writerow(by_id[r[0]] + [""] * (len(h) - 6))
    regen = buf.getvalue().encode("utf-8")
    actual = open(DATA + "/" + name, "rb").read()
    print(
        f"   regenerated-from-full bytes identical to file on disk: {regen == actual} (regen {len(regen)} bytes, disk {len(actual)} bytes)"
    )

for name, meta in manifest["files"].items():
    p = DATA + "/" + name
    with open(p, "rb") as f:
        d = hashlib.file_digest(f, "sha256").hexdigest()
    size = os.path.getsize(p)
    print(
        f"{name}: sha256 match {d == meta['sha256']} | bytes {size} match {size == meta['bytes']}"
    )
# raw byte facts of the full file
raw = open(DATA + "/spotify_reviews_18months.csv", "rb").read()
print(
    "full file: starts with BOM:",
    raw[:3] == b"\xef\xbb\xbf",
    "| CR bytes:",
    raw.count(b"\r"),
    "| LF bytes (physical lines):",
    raw.count(b"\n"),
    "| NUL bytes:",
    raw.count(b"\x00"),
)
try:
    raw.decode("utf-8")
    print("full file decodes as strict UTF-8: True")
except UnicodeDecodeError as e:
    print("full file decodes as strict UTF-8: False", e)
# manifest profile cross-checks
print("manifest profile:", manifest["profile"])
print(
    "measured: records",
    len(rows),
    "empty",
    len(empt),
    "missing app_version",
    sum(1 for r in rows if not r[4].strip()),
)
from collections import Counter

print(
    "ratings measured:",
    dict(sorted(Counter(r[2] for r in rows).items())),
    "== manifest:",
    dict(sorted(Counter(r[2] for r in rows).items())) == manifest["reviews_by_rating"],
)
print(
    "months measured == manifest:",
    dict(sorted(Counter(r[5][:7] for r in rows).items()))
    == manifest["reviews_by_month"],
)
