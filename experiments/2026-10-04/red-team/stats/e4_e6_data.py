"""E4 keyword proxy + E6 text-length comparison, on the real files. Read-only. Standard library only."""

import csv
import math
import random
import statistics
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)
D = str(Path(__file__).resolve().parents[4] / "feed/Final Assignment - Spotify Reviews Dataset") + "/"


def load(fn):
    with open(D + fn, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


full = load("spotify_reviews_18months.csv")
cost = load("cost_100.csv")
gold = load("golden_50_to_label.csv")
chk = load("checkpoint_500.csv")
ana = load("analysis_10000.csv")

# ------------------------------------------------------------ anchors
print("=== Known-answer anchors (from manifest.json / brief) ===")
n_rows = len(full)
empty = sum(1 for r in full if not r["review_text"].strip())
ids = {r["review_id"] for r in full}
nonempty = [r for r in full if r["review_text"].strip()]
distinct = {r["review_text"] for r in nonempty}
print(
    f"rows={n_rows} (expect 660622)  empty={empty} (expect 13)  unique ids={len(ids)}  nonempty={len(nonempty)} (expect 660609)  distinct nonempty texts={len(distinct)} (expect 484189)"
)
assert n_rows == 660622 and empty == 13 and len(nonempty) == 660609
cost_ids = [r["review_id"] for r in cost]
print(
    "cost_100 == first 100 of checkpoint_500:",
    cost_ids == [r["review_id"] for r in chk[:100]],
    "| golden disjoint from analysis_10000:",
    not ({r["review_id"] for r in gold} & {r["review_id"] for r in ana}),
)

# ------------------------------------------------------------ E4 keyword proxy
print(
    "\n=== E4: keyword-match prevalence (ROUGH PROXY: a keyword hit is a mention, not a primary-topic label) ==="
)
ACCESS = ["log in", "login", "password", "sign in", "account"]
ACCESS_NARROW = ["log in", "login", "password", "sign in"]
ACCESS_WIDE = ACCESS + [
    "logged",
    "log me",
    "logging",
    "signin",
    "sign up",
    "signup",
    "log out",
    "logout",
    "log on",
    "verification",
    "verify",
]
SUPPORT = ["customer service", "support team", "customer support"]
SUPPORT_WIDE = SUPPORT + [
    "customer care",
    "contacted support",
    "contact support",
    "help desk",
    "helpdesk",
    "tech support",
]


def hit(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def prevalence(rows, kws):
    return sum(1 for r in rows if hit(r["review_text"], kws))


N = len(nonempty)
for name, kws in (
    ("access (listed keywords)", ACCESS),
    ("access, without bare 'account'", ACCESS_NARROW),
    ("access, widened", ACCESS_WIDE),
    ("support (listed keywords)", SUPPORT),
    ("support, widened", SUPPORT_WIDE),
):
    c = prevalence(nonempty, kws)
    cg = prevalence(gold, kws)
    ca = prevalence(ana, kws)
    p = c / N
    # P(>=5 in 50) under binomial with this p
    pge5 = 1 - sum(math.comb(50, k) * p**k * (1 - p) ** (50 - k) for k in range(5))
    p0 = (1 - p) ** 50
    print(
        f"  {name:34s} full: {c:6d}/{N} = {p * 100:5.2f}%   expected in 50: {50 * p:4.2f}   P(>=5 of 50)={pge5:.4f}  P(0 of 50)={p0:.3f} | analysis_10000: {ca} ({ca / 100:.2f}%) | ACTUAL golden 50: {cg}"
    )
print("  per-keyword counts in the full file:")
for k in ACCESS + SUPPORT:
    c = sum(1 for r in nonempty if k in r["review_text"].lower())
    print(f"    '{k}': {c} ({c / N * 100:.2f}%)")
print(
    "  golden-50 rows matching any listed access keyword / support keyword (review_id prefix, first 70 chars):"
)
for r in gold:
    a, s = hit(r["review_text"], ACCESS), hit(r["review_text"], SUPPORT)
    if a or s:
        print(
            f"    [{'access' if a else ''}{'+' if a and s else ''}{'support' if s else ''}] {r['review_id'][:8]} {r['review_text'][:70]!r}"
        )

# ------------------------------------------------------------ E6 lengths
print("\n=== E6: review_text length, cost_100 vs full file ===")


def L(rows):
    return [len(r["review_text"]) for r in rows]


def B(rows):
    return [len(r["review_text"].encode("utf-8")) for r in rows]


def W(rows):
    return [len(r["review_text"].split()) for r in rows]


def q(xs, p):
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
    return s[i]


def desc(name, xs):
    print(
        f"  {name:38s} n={len(xs):6d} mean={statistics.fmean(xs):7.2f} sd={statistics.pstdev(xs):7.2f} p10={q(xs, 0.10):4d} median={q(xs, 0.50):4d} p75={q(xs, 0.75):4d} p90={q(xs, 0.90):4d} p99={q(xs, 0.99):4d} max={max(xs)}"
    )


full_len = L(nonempty)
cost_len = L(cost)
desc("FULL nonempty rows (chars)", full_len)
desc("FULL distinct texts (chars)", [len(t) for t in distinct])
desc("cost_100 (chars)", cost_len)
desc("checkpoint_500 (chars)", L(chk))
desc("analysis_10000 (chars)", L(ana))
desc("golden_50 (chars)", L(gold))
desc("FULL nonempty rows (utf-8 bytes)", B(nonempty))
desc("cost_100 (utf-8 bytes)", B(cost))
desc("FULL nonempty rows (whitespace words)", W(nonempty))
desc("cost_100 (whitespace words)", W(cost))

mu = statistics.fmean(full_len)
sd = statistics.pstdev(full_len)
for name, xs, ref in (
    ("chars", cost_len, full_len),
    ("utf-8 bytes", B(cost), B(nonempty)),
    ("words", W(cost), W(nonempty)),
):
    m, r = statistics.fmean(xs), statistics.fmean(ref)
    print(
        f"  cost_100 mean {name} vs full mean: {m:.2f} vs {r:.2f}  -> relative error {(m / r - 1) * 100:+.1f}%"
    )
m500, m10k = statistics.fmean(L(chk)), statistics.fmean(L(ana))
print(
    f"  checkpoint_500 mean chars rel. error {(m500 / mu - 1) * 100:+.1f}% ; analysis_10000 rel. error {(m10k / mu - 1) * 100:+.1f}%"
)
dist_mean = statistics.fmean([len(t) for t in distinct])
print(
    f"  distinct-text mean chars {dist_mean:.2f} vs row mean {mu:.2f}: distinct texts are {(dist_mean / mu - 1) * 100:+.1f}% longer on average"
)
dup_cost = len(cost) - len({r["review_text"] for r in cost})
print(
    f"  exact-duplicate texts inside cost_100: {dup_cost} of 100 (full file: {N - len(distinct)} of {N} = {(N - len(distinct)) / N * 100:.1f}% of rows are repeats of an earlier text)"
)
print(
    f"  theory: SE of a mean of 100 = sd/sqrt(100) = {sd / 10:.2f} chars = {sd / 10 / mu * 100:.1f}% of the mean; +/-20% = {0.2 * mu / (sd / 10):.2f} SE"
)

# length buckets
print("  share of reviews by length bucket (chars):   full      cost_100")
for lo, hi in ((1, 20), (21, 50), (51, 100), (101, 200), (201, 350), (351, 10**9)):
    f = sum(1 for x in full_len if lo <= x <= hi) / len(full_len)
    c = sum(1 for x in cost_len if lo <= x <= hi) / len(cost_len)
    print(
        f"    {lo:>4}-{hi if hi < 10**8 else 'max':<5}                              {f * 100:5.1f}%   {c * 100:5.1f}%"
    )

# bootstrap: random samples of 100 nonempty reviews, without replacement
random.seed(42)
REPS = 50000
ratios = []
for _ in range(REPS):
    s = random.sample(full_len, 100)
    ratios.append(sum(s) / 100 / mu)
ratios.sort()
within20 = sum(1 for r in ratios if 0.8 <= r <= 1.2) / REPS
within10 = sum(1 for r in ratios if 0.9 <= r <= 1.1) / REPS
print(
    f"\n  Bootstrap ({REPS} random samples of 100 nonempty reviews, without replacement):"
)
print(
    f"    sample-mean / population-mean: sd={statistics.pstdev(ratios):.4f}  2.5%={ratios[int(0.025 * REPS)]:.3f}  50%={ratios[REPS // 2]:.3f}  97.5%={ratios[int(0.975 * REPS)]:.3f}  min={ratios[0]:.3f} max={ratios[-1]:.3f}"
)
print(
    f"    share of samples within +/-20% of the true mean: {within20 * 100:.1f}%   within +/-10%: {within10 * 100:.1f}%"
)
cr = statistics.fmean(cost_len) / mu
pct = sum(1 for r in ratios if r <= cr) / REPS
print(
    f"    the actual cost_100 ratio {cr:.3f} sits at the {pct * 100:.1f}th percentile of that distribution"
)
for n in (500, 10000):
    rr = []
    for _ in range(4000):
        s = random.sample(full_len, n)
        rr.append(sum(s) / n / mu)
    rr.sort()
    print(
        f"    same for samples of {n}: 2.5%={rr[int(0.025 * len(rr))]:.3f}  97.5%={rr[int(0.975 * len(rr))]:.3f}"
    )

# input-size share: per-review input = shared prompt overhead + text. Show how the text error propagates
print(
    "\n  Propagation to billed INPUT tokens per review (text tokens approximated as chars/4; overhead is an assumption, shown for a range):"
)
tt_full, tt_cost = mu / 4, statistics.fmean(cost_len) / 4
for ov in (0, 20, 50, 100, 300):
    print(
        f"    per-review overhead {ov:>3} tokens: full {tt_full + ov:6.1f} vs cost_100 {tt_cost + ov:6.1f} -> error {((tt_cost + ov) / (tt_full + ov) - 1) * 100:+.1f}%"
    )
