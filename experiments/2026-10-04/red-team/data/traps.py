"""Follow-ups: splitter sensitivity, F6 class listing, F7 row dump, F11 raw-byte check, and other traps."""

import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter, defaultdict
from common import FULL, load, trunc

header, rows = load()
ne_rows = [r for r in rows if r[1].strip() != ""]
nonempty = [r[1] for r in ne_rows]
N = len(nonempty)

# ---- F11: is the full file itself byte-reproducible from its parsed rows? (then parsed-field equality == raw-byte equality)
buf = io.StringIO(newline="")
w = csv.writer(buf, lineterminator="\n")
w.writerow(header)
w.writerows(rows)
regen = buf.getvalue().encode("utf-8")
raw = open(FULL, "rb").read()
print(
    "F11 full file re-serialised from parsed rows == raw bytes:",
    regen == raw,
    hashlib.sha256(regen).hexdigest()[:16],
)
del buf, regen, raw

# ---- F1 sensitivity
B = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
D = re.compile(
    r"(?<=[.!?])\s+|\r\n|\n|\r"
)  # no collapsing of consecutive line breaks, no blank filter
E = re.compile(r"(?<=[.!?])\s|\n")  # one whitespace char only, no blank filter
for name, rx in [("D no-collapse/no-filter", D), ("E single-ws/no-filter", E)]:
    blank = rws = mx = 0
    for t in nonempty:
        ps = rx.split(t)
        b = sum(1 for p in ps if p.strip() == "")
        blank += b
        rws += 1 if b else 0
        mx = max(mx, len(ps))
    print(f"F1 variant {name}: blank pieces {blank} in {rws} rows; max pieces {mx}")


def pieces(t):
    return [p.strip() for p in B.split(t) if p.strip() != ""]


top = sorted(nonempty, key=lambda t: -len(pieces(t)))[:3]
for t in top:
    ps = pieces(t)
    print(
        "F1 top piece-count:",
        len(ps),
        "len",
        len(t),
        "| text:",
        trunc(t),
        "| piece-length counter:",
        Counter(len(p) for p in ps).most_common(3),
        "| sample pieces:",
        ps[1:4],
    )
# pieces without any letter/digit over the whole corpus (incl. single-piece rows)
tot_p = junk_p = 0
for t in nonempty:
    for p in pieces(t):
        tot_p += 1
        if not any(ch.isalnum() for ch in p):
            junk_p += 1
print(
    "F1 total pieces:",
    tot_p,
    "| pieces with no letter/digit:",
    junk_p,
    f"({100 * junk_p / tot_p:.3f}%)",
)
# duplicate pieces inside a row (a piece index is unambiguous, a quoted string is not)
dup_piece_rows = sum(1 for t in nonempty if len(pieces(t)) != len(set(pieces(t))))
print("F1 rows whose piece list contains repeated identical pieces:", dup_piece_rows)
# ASCII-only whitespace engines (RE2/JS-less): [.!?] followed by non-ASCII whitespace
nonascii_ws = sum(1 for t in nonempty if re.search(r"[.!?][^\S \t\n\r\f\v]", t))
print(
    "F1 rows where [.!?] is followed by a NON-ASCII whitespace char (engine-dependent split):",
    nonascii_ws,
)
uni_space = Counter()
for t in nonempty:
    for ch in set(t):
        if ch.isspace() and ch not in " \n":
            uni_space[f"U+{ord(ch):04X}"] += 1
print("rows by non-space/newline whitespace char:", dict(uni_space))

# ---- F5 extras: visually blank but nonempty by strip()
INVIS_EXTRA = {"ㅤ", "⠀", "ᅟ", "ᅠ", "ﾠ", "​", "‌", "‍", "⁠", "﻿", "­", "͏", "؜", "᠎"}


def invisible(t):
    return all(
        ch.isspace()
        or ch in INVIS_EXTRA
        or unicodedata.category(ch) in ("Cf", "Cc")
        or 0xFE00 <= ord(ch) <= 0xFE0F
        for ch in t
    )


inv = [r for r in ne_rows if invisible(r[1])]
print(
    "F5 rows nonempty under strip() but rendering as blank (whitespace + invisible/filler/variation-selector chars only):",
    len(inv),
    [ascii(r[1])[:60] for r in inv[:3]],
)
short = Counter(len(t) for t in nonempty)
print(
    "F5 nonempty rows of length 1:",
    short[1],
    "| length 2:",
    short[2],
    "| length <=3:",
    short[1] + short[2] + short[3],
)

# ---- F6 full class listing
cat = {}


def category(ch):
    c = cat.get(ch)
    if c is None:
        c = cat[ch] = unicodedata.category(ch)
    return c


prefix_rows = Counter()
for t in nonempty:
    pf = set()
    for ch in set(t):
        if category(ch)[0] == "L":
            nm = unicodedata.name(ch, "UNNAMED")
            tok = nm.split()
            pf.add("LATIN*" if "LATIN" in tok and tok[0] != "LATIN" else tok[0])
    for p in pf:
        prefix_rows[p] += 1
print("F6 rows per Unicode-name first token of letters (all classes):")
print("  ", prefix_rows.most_common(45))

# ---- F7 dumps
core = [
    "ignore previous",
    "ignore all",
    "ignore the above",
    "system prompt",
    "you are an ai",
    "as an ai",
    "chatgpt",
]
print("F7 all rows matching listed phrases:")
for t in nonempty:
    lo = t.lower()
    hit = [p for p in core if p in lo]
    if hit:
        i = lo.find(hit[0])
        print("   ", hit, "| ctx:", trunc(t[max(0, i - 30) : i + 50]))
for lit in ["```", "{{", "}}"]:
    for t in nonempty:
        if lit in t:
            i = t.find(lit)
            print(f"F7 literal {lit!r} ctx:", trunc(t[max(0, i - 30) : i + 50]))
# whole-word version of 'as an ai' and 'ai'
print(
    "F7 rows with whole-word 'as an ai':",
    sum(1 for t in nonempty if re.search(r"\bas an ai\b", t, re.I)),
)
# second-person/imperative addressed to a model or reviewer
imper = re.compile(
    r"\b(ignore (this|my|the) (review|rating|comment)|do not (classify|label)|rate this (review|as)|mark this as|respond with|output (only|json)|new instructions?)\b",
    re.I,
)
hits = [t for t in nonempty if imper.search(t)]
print(
    "F7 rows with reviewer/model-directed imperatives (regex):",
    len(hits),
    [trunc(t) for t in hits[:3]],
)

# ---- Other traps
print("\n== other traps ==")
PANDAS_NA = {
    "",
    "#N/A",
    "#N/A N/A",
    "#NA",
    "-1.#IND",
    "-1.#QNAN",
    "-NaN",
    "-nan",
    "1.#IND",
    "1.#QNAN",
    "<NA>",
    "N/A",
    "NA",
    "NULL",
    "NaN",
    "None",
    "n/a",
    "nan",
    "null",
}
na_hits = Counter(t for t in nonempty if t in PANDAS_NA)
print(
    "T1 nonempty rows whose text is a pandas default NA token (read_csv would turn into NaN):",
    sum(na_hits.values()),
    dict(na_hits),
)
na_ci = Counter(
    t.strip().lower()
    for t in nonempty
    if t.strip().lower() in {"na", "n/a", "null", "none", "nan", "nil", "true", "false"}
)
print("   case-insensitive null/bool-like texts:", sum(na_ci.values()), dict(na_ci))
print(
    "   app_version values that are pandas NA tokens (non-blank):",
    sum(1 for r in rows if r[4] in PANDAS_NA and r[4] != ""),
)
num_like = [t for t in nonempty if re.fullmatch(r"\s*[-+]?\d+(\.\d+)?\s*", t)]
print(
    "   numeric-looking texts (type inference / JSON number coercion):",
    len(num_like),
    Counter(num_like).most_common(5),
)

nfc = [t for t in nonempty if unicodedata.normalize("NFC", t) != t]
nfkc = [t for t in nonempty if unicodedata.normalize("NFKC", t) != t]
print(
    "T2 rows not in NFC:",
    len(nfc),
    "| rows changed by NFKC:",
    len(nfkc),
    [trunc(t, 40) for t in nfc[:2]],
)
curly = sum(1 for t in nonempty if re.search("[‘’“”]", t))
dbl_space = sum(1 for t in nonempty if "  " in t)
nbsp = sum(1 for t in nonempty if " " in t)
emoji_vs = sum(1 for t in nonempty if "️" in t or "‍" in t)
astral = sum(1 for t in nonempty if any(ord(ch) > 0xFFFF for ch in t))
print(
    "T3 verbatim-copy hazards for evidence_quote: rows with curly quotes/apostrophes:",
    curly,
    "| double spaces:",
    dbl_space,
    "| NBSP:",
    nbsp,
    "| VS16/ZWJ emoji sequences:",
    emoji_vs,
    "| astral (non-BMP) chars:",
    astral,
    "| ASCII double-quote:",
    sum(1 for t in nonempty if '"' in t),
    "| backslash:",
    sum(1 for t in nonempty if "\\" in t),
)
any_hazard = sum(
    1
    for t in nonempty
    if re.search('[‘’“” ️‍"\\\\]|  ', t) or any(ord(ch) > 0xFFFF for ch in t)
)
print(
    "   rows with at least one of those hazards:",
    any_hazard,
    f"({100 * any_hazard / N:.2f}%)",
)

# T4 month spikes / campaigns
by_month = defaultdict(list)
for r in ne_rows:
    by_month[r[5][:7]].append(r)
print("T4 per-month: rows, 1-star share, top text")
for m in sorted(by_month):
    rs = by_month[m]
    one = sum(1 for r in rs if r[2] == "1")
    c = Counter(r[1] for r in rs).most_common(1)[0]
    print(
        f"   {m}: {len(rs):6d} rows, 1-star {100 * one / len(rs):5.1f}%, top text x{c[1]}: {trunc(c[0], 40)!r}"
    )
kw = ["boycott", "palestin", "israel", "gaza", "hate this application"]
for k in kw:
    hs = [r for r in ne_rows if k in r[1].lower()]
    months = Counter(r[5][:7] for r in hs).most_common(3)
    print(f"   keyword {k!r}: {len(hs)} rows; top months {months}")
day = Counter(r[5][:10] for r in rows)
print(
    "   busiest days:",
    day.most_common(5),
    "| median day:",
    sorted(day.values())[len(day) // 2],
)
hate = [r for r in ne_rows if r[1] == "Hate this application 👎"]
print(
    "   'Hate this application 👎' rows:",
    len(hate),
    "ratings",
    dict(Counter(r[2] for r in hate)),
    "top days",
    Counter(r[5][:10] for r in hate).most_common(3),
)

# T5 metadata fields
print(
    "T5 review_likes non-digit:",
    sum(1 for r in rows if not r[3].isdigit()),
    "| max likes:",
    max(int(r[3]) for r in rows if r[3].isdigit()),
)
ts_bad = sum(
    1 for r in rows if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", r[5])
)
print(
    "   timestamps not 'YYYY-MM-DD HH:MM:SS':",
    ts_bad,
    "| file is time-sorted ascending:",
    all(rows[i][5] <= rows[i + 1][5] for i in range(len(rows) - 1)),
    "| duplicate timestamps:",
    len(rows) - len({r[5] for r in rows}),
)
idpat = Counter(
    "uuid"
    if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", r[0]
    )
    else "other"
    for r in rows
)
print(
    "   review_id shapes:",
    dict(idpat),
    "| case-insensitive id collisions:",
    len(rows) - len({r[0].lower() for r in rows}),
    "| ids with surrounding ws:",
    sum(1 for r in rows if r[0] != r[0].strip()),
)
ver = Counter(r[4] for r in rows)
print(
    "   app_version blank:",
    ver[""],
    "| distinct versions:",
    len(ver),
    "| versions not matching d.d.d.d:",
    sum(c for v, c in ver.items() if v and not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", v)),
)
formula = sum(1 for t in nonempty if t[0] in "=+-@")
print(
    "   texts starting with = + - @ (spreadsheet formula injection on export):", formula
)
multi_nl = sum(1 for t in nonempty if "\n" in t)
print(
    "   rows with embedded newline:",
    multi_nl,
    "| total embedded newlines:",
    sum(t.count("\n") for t in nonempty),
    "| physical lines - 1 - rows:",
    660792 - 1 - len(rows),
)
# star/text disagreement on obviously polar duplicate texts
pos = {
    "Good",
    "Nice",
    "Excellent",
    "Great",
    "Awesome",
    "Love it",
    "Very good",
    "Amazing",
    "Best",
    "Super",
}
p = [r for r in ne_rows if r[1] in pos]
print(
    "T6 rows with a generic positive one-word text:",
    len(p),
    "| of which rated 1-2 stars:",
    sum(1 for r in p if r[2] in "12"),
)
