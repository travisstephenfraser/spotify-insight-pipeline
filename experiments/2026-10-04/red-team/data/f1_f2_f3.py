"""F1, F2, F3: sentence splitter behaviour."""

import re
from collections import Counter
from common import load, trunc

header, rows = load()
assert header == [
    "review_id",
    "review_text",
    "review_rating",
    "review_likes",
    "app_version",
    "review_timestamp",
], header
print("rows", len(rows))
texts = [r[1] for r in rows]
nonempty = [t for t in texts if t.strip() != ""]
N = len(nonempty)
print("nonempty", N, "empty", len(texts) - N)

# Splitter exactly as the claim words it: split after . ! ? when followed by whitespace, and at line breaks.
# Variant A (raw): re.split with zero-width boundary after [.!?] before whitespace, plus line breaks. No cleanup.
RAW_A = re.compile(r"(?<=[.!?])(?=\s)|[\r\n]+")
# Variant B (consume whitespace): split on the whitespace run that follows [.!?], and on line breaks. No cleanup.
RAW_B = re.compile(r"(?<=[.!?])\s+|[\r\n]+")


def split_raw_a(t):
    return RAW_A.split(t)


def split_raw_b(t):
    return RAW_B.split(t)


def split_clean(t):
    """Variant C: B, then strip each piece and drop blanks (the most charitable reading)."""
    return [p.strip() for p in RAW_B.split(t) if p.strip() != ""]


for name, fn in [
    ("A raw zero-width", split_raw_a),
    ("B raw consume-ws", split_raw_b),
    ("C strip+drop-blank", split_clean),
]:
    blank_pieces = 0
    rows_with_blank = 0
    not_substring = 0
    dist = Counter()
    mx = 0
    mx_text = ""
    over255 = 0
    zero = 0
    for t in nonempty:
        ps = fn(t)
        b = sum(1 for p in ps if p.strip() == "")
        blank_pieces += b
        rows_with_blank += 1 if b else 0
        not_substring += sum(1 for p in ps if p not in t)
        n = len(ps)
        dist[n] += 1
        if n == 0:
            zero += 1
        if n > 255:
            over255 += 1
        if n > mx:
            mx, mx_text = n, t
    print(f"\n== variant {name} ==")
    print(
        "blank pieces",
        blank_pieces,
        "rows with >=1 blank piece",
        rows_with_blank,
        "pieces not substring",
        not_substring,
    )
    print(
        "rows with 0 pieces",
        zero,
        "rows >255 pieces",
        over255,
        "max pieces",
        mx,
        "| max text:",
        trunc(mx_text),
        "len",
        len(mx_text),
    )
    buckets = [
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
        (5, 5),
        (6, 10),
        (11, 20),
        (21, 50),
        (51, 255),
        (256, 10**9),
    ]
    for lo, hi in buckets:
        c = sum(v for k, v in dist.items() if lo <= k <= hi)
        print(f"  pieces {lo}-{hi}: {c} ({100 * c / N:.3f}%)")
    print("  0 pieces:", dist.get(0, 0))
    top = sorted(dist.items(), key=lambda kv: -kv[0])[:8]
    print("  largest piece counts:", top)

# Order-preserving exactness: do pieces occur in order, non-overlapping, and cover every non-whitespace char?
bad_cover = 0
for t in nonempty:
    ps = split_clean(t)
    pos = 0
    ok = True
    for p in ps:
        i = t.find(p, pos)
        if i < 0:
            ok = False
            break
        if t[pos:i].strip() != "":
            ok = False
            break
        pos = i + len(p)
    if ok and t[pos:].strip() != "":
        ok = False
    if not ok:
        bad_cover += 1
print(
    "\nvariant C: rows where pieces are not an in-order, gap-free (whitespace-only gaps) cover:",
    bad_cover,
)

# F2: single-piece reviews (variant C; single-piece set is the same for B/C on nonempty text unless blanks)
single = [t for t in nonempty if len(split_clean(t)) == 1]
S = len(single)
u200 = sum(1 for t in single if len(t) < 200)
o200 = sum(1 for t in single if len(t) > 200)
ge200 = sum(1 for t in single if len(t) >= 200)
o400 = sum(1 for t in single if len(t) > 400)
print("\n== F2 ==")
print("single-piece reviews", S, f"({100 * S / N:.3f}% of nonempty)")
print("single-piece under 200 chars", u200, f"({100 * u200 / S:.4f}% of single-piece)")
print(
    "single-piece >=200",
    ge200,
    "| >200:",
    o200,
    f"({100 * o200 / N:.4f}% of nonempty, {100 * o200 / S:.4f}% of single)",
)
print(
    "single-piece >400:",
    o400,
    f"({100 * o400 / N:.4f}% of nonempty, {100 * o400 / S:.4f}% of single)",
)
ls = sorted(len(t) for t in single)
print(
    "single-piece length percentiles: p50",
    ls[S // 2],
    "p90",
    ls[int(S * 0.9)],
    "p95",
    ls[int(S * 0.95)],
    "p99",
    ls[int(S * 0.99)],
    "max",
    ls[-1],
)
ex = sorted(single, key=len, reverse=True)[:3]
for t in ex:
    print("  longest single-piece ex len", len(t), ":", trunc(t))

# Also: any PIECE (in multi-piece reviews) that is long? pieces over 200 / 400 chars across all reviews
pl200 = pl400 = rows_pl200 = 0
for t in nonempty:
    ps = split_clean(t)
    a = sum(1 for p in ps if len(p) > 200)
    pl200 += a
    pl400 += sum(1 for p in ps if len(p) > 400)
    rows_pl200 += 1 if a else 0
print(
    "all reviews: pieces >200 chars",
    pl200,
    "pieces >400",
    pl400,
    "rows with any piece >200",
    rows_pl200,
    f"({100 * rows_pl200 / N:.4f}%)",
)

# Splits that the '. followed by whitespace' rule misses: sentence punctuation followed directly by a letter ("bad.I hate")
glued = re.compile(r"[.!?][^\W\d_]")
gl = sum(1 for t in nonempty if glued.search(t))
print(
    "rows with [.!?] immediately followed by a letter (no split there):",
    gl,
    f"({100 * gl / N:.3f}%)",
)
# Over-splitting on abbreviations / ellipses: pieces of <=3 chars
tiny = 0
rows_tiny = 0
for t in nonempty:
    ps = split_clean(t)
    if len(ps) > 1:
        a = sum(1 for p in ps if len(p) <= 3)
        tiny += a
        rows_tiny += 1 if a else 0
print(
    "multi-piece rows with at least one piece of <=3 chars:",
    rows_tiny,
    "such pieces:",
    tiny,
)
# pieces with no letter/digit (punctuation/emoji only fragments)
noalnum = rows_noalnum = 0
for t in nonempty:
    ps = split_clean(t)
    if len(ps) > 1:
        a = sum(1 for p in ps if not any(ch.isalnum() for ch in p))
        noalnum += a
        rows_noalnum += 1 if a else 0
print(
    "multi-piece rows with at least one piece lacking any letter/digit:",
    rows_noalnum,
    "such pieces:",
    noalnum,
)

# F3: non-ASCII sentence punctuation
PUNCT = {
    "।": "DEVANAGARI DANDA",
    "॥": "DEVANAGARI DOUBLE DANDA",
    "。": "CJK FULL STOP",
    "．": "FULLWIDTH FULL STOP",
    "！": "FULLWIDTH EXCLAMATION",
    "？": "FULLWIDTH QUESTION",
    "｡": "HALFWIDTH IDEOGRAPHIC FULL STOP",
    "؟": "ARABIC QUESTION MARK",
    "۔": "ARABIC FULL STOP",
    "։": "ARMENIAN FULL STOP",
    "።": "ETHIOPIC FULL STOP",
    "၊": "MYANMAR LITTLE SECTION",
    "။": "MYANMAR SECTION",
    "។": "KHMER KHAN",
    "།": "TIBETAN SHAD",
    ";": "GREEK QUESTION MARK",
    "…": "HORIZONTAL ELLIPSIS",
    "‼": "DOUBLE EXCLAMATION",
    "⁉": "EXCLAMATION QUESTION",
    "⁇": "DOUBLE QUESTION",
    "⁈": "QUESTION EXCLAMATION",
    "¡": "INVERTED EXCLAMATION",
    "¿": "INVERTED QUESTION",
    "෴": "SINHALA KUNDDALIYA",
    "፧": "ETHIOPIC QUESTION",
    "、": "CJK IDEOGRAPHIC COMMA",
    "،": "ARABIC COMMA",
}
STRICT = set("।॥。．！？｡؟۔։።၊။។།;፧")
per = Counter()
strict_rows = strict_single = strict_single200 = strict_single400 = 0
strict_nosplit_at_mark = 0
ex3 = []
ascii_split = re.compile(r"[.!?]\s|[\r\n]")
strict_only_rows = 0  # rows that have foreign terminators and NO ascii split point
for t in nonempty:
    hit = False
    for ch in set(t):
        if ch in PUNCT:
            per[ch] += 1
            if ch in STRICT:
                hit = True
    if hit:
        strict_rows += 1
        n = len(split_clean(t))
        if not ascii_split.search(t):
            strict_only_rows += 1
        if n == 1:
            strict_single += 1
            if len(t) > 200:
                strict_single200 += 1
                if len(ex3) < 3:
                    ex3.append(t)
            if len(t) > 400:
                strict_single400 += 1
print("\n== F3 ==")
for ch, c in per.most_common():
    print(f"  U+{ord(ch):04X} {PUNCT[ch]}: {c} rows")
print(
    "rows containing a non-ASCII sentence TERMINATOR (strict set, excludes ellipsis/inverted/commas/double-bang):",
    strict_rows,
)
print(
    "  of which single piece:",
    strict_single,
    "| single piece >200 chars:",
    strict_single200,
    "| >400:",
    strict_single400,
)
print(
    "  rows where the foreign terminator is the only sentence boundary signal (no ASCII .!?+ws and no line break):",
    strict_only_rows,
)
for t in ex3:
    print("  ex len", len(t), ":", trunc(t))

# How many foreign terminators would have produced a split had they been honoured?
FOREIGN = re.compile("[" + "".join(sorted(STRICT)) + "]")
missed_rows = 0
missed_marks = 0
for t in nonempty:
    ms = [
        m
        for m in FOREIGN.finditer(t)
        if t[m.end() :].strip() != "" and t[m.end() : m.end() + 1] not in ("\n", "\r")
    ]
    # a mark that is followed by more non-blank text and not by a line break => a boundary the splitter does not take
    if ms:
        missed_rows += 1
        missed_marks += len(ms)
print(
    "rows with >=1 foreign terminator followed by more text on the same line (boundary not taken):",
    missed_rows,
    "marks:",
    missed_marks,
)
