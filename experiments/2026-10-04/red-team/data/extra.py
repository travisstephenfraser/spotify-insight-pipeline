"""Small follow-ups: F3 union counts, burst months, 4th invisible row, F2 exact-200 boundary."""
import re
from collections import Counter
from common import load, trunc

header, rows = load()
ne = [r for r in rows if r[1].strip() != ""]
N = len(ne)
STRICT = "।॥。．！？｡؟۔։።၊။។།;፧"
BROAD = STRICT + "…‼⁉⁇⁈¡¿、،"
rs = re.compile("[" + STRICT + "]")
rb = re.compile("[" + BROAD + "]")
SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
pieces = lambda t: [p.strip() for p in SPLIT.split(t) if p.strip() != ""]
s_rows = [r[1] for r in ne if rs.search(r[1])]
b_rows = [r[1] for r in ne if rb.search(r[1])]
print("strict terminator rows:", len(s_rows), f"({100*len(s_rows)/N:.4f}%)", "| broad set rows:", len(b_rows))
print("broad: single piece", sum(1 for t in b_rows if len(pieces(t)) == 1), "| single >200", sum(1 for t in b_rows if len(pieces(t)) == 1 and len(t) > 200))
# strict excluding halfwidth ideographic full stop (kaomoji noise)
s2 = [t for t in s_rows if re.search("[" + STRICT.replace("｡", "") + "]", t)]
print("strict excl. U+FF61:", len(s2), "single", sum(1 for t in s2 if len(pieces(t)) == 1), "single>200", sum(1 for t in s2 if len(pieces(t)) == 1 and len(t) > 200))
ex = [t for t in s2 if len(pieces(t)) == 1 and len(t) > 200][:3]
for t in ex:
    print("  ex len", len(t), trunc(t))
# invisible rows
import unicodedata
EXTRA = {"ㅤ", "⠀", "ᅟ", "ᅠ", "ﾠ"}
inv = [r for r in ne if all(ch.isspace() or ch in EXTRA or unicodedata.category(ch) in ("Cf", "Cc") or 0xFE00 <= ord(ch) <= 0xFE0F for ch in r[1])]
for r in inv:
    print("invisible row:", r[0][:8], ascii(r[1])[:80], "rating", r[2])
# F2 boundary
single = [r[1] for r in ne if len(pieces(r[1])) == 1]
print("single:", len(single), "len<200:", sum(1 for t in single if len(t) < 200), "len==200:", sum(1 for t in single if len(t) == 200), "len<=200:", sum(1 for t in single if len(t) <= 200))
# burst months
for m in ("2023-07", "2023-10", "2023-09", "2023-11"):
    sub = [r for r in ne if r[5].startswith(m)]
    words = Counter()
    for r in sub:
        if r[2] == "1":
            words.update(set(re.findall(r"[a-z']{4,}", r[1].lower())))
    stop = {"this", "that", "with", "have", "they", "just", "your", "from", "when", "what", "will", "even", "very", "them", "because", "there", "like", "about", "more", "than", "can't", "don't", "only", "then", "were", "been", "listen", "music", "song", "songs", "spotify", "application", "play"}
    top = [(w, c) for w, c in words.most_common(60) if w not in stop][:12]
    print(m, "rows", len(sub), "1-star", sum(1 for r in sub if r[2] == "1"), "| top 1-star words:", top)
burst = sum(1 for r in rows if r[5][:7] in ("2023-07", "2023-09", "2023-10", "2023-11"))
print("rows in Jul/Sep/Oct/Nov 2023:", burst, f"({100*burst/len(rows):.1f}% of all rows in 4 of 19 months)")
bare = [r for r in ne if "boycott" in r[1].lower() and len(r[1]) <= 30]
print("short (<=30 chars) texts containing 'boycott':", len(bare), Counter(r[1] for r in bare).most_common(3))
