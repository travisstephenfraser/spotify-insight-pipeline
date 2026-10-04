"""F4, F5, F6, F7, F9: dedup, emptiness, scripts, prompt/JSON hazards, duplicate groups."""

import re
import unicodedata
from collections import Counter, defaultdict
from common import load, trunc

header, rows = load()
texts = [r[1] for r in rows]
empty = [t for t in texts if t.strip() == ""]
nonempty_rows = [r for r in rows if r[1].strip() != ""]
nonempty = [r[1] for r in nonempty_rows]
N = len(nonempty)
print("rows", len(rows), "nonempty", N, "empty(strip)==''", len(empty))
print(
    "empty breakdown: exactly '' =",
    sum(1 for t in empty if t == ""),
    "| whitespace-only =",
    sum(1 for t in empty if t != ""),
)

# ---------------- F4 ----------------
print("\n== F4 ==")
exact = Counter(nonempty)
d_exact = len(exact)
d_strip = len({t.strip() for t in nonempty})
d_strip_lower = len({t.strip().lower() for t in nonempty})
d_strip_casefold = len({t.strip().casefold() for t in nonempty})
d_ws = len({" ".join(t.split()) for t in nonempty})
d_ws_lower = len({" ".join(t.split()).lower() for t in nonempty})
d_nfc = len({unicodedata.normalize("NFC", t) for t in nonempty})
print("distinct exact:", d_exact, "(claim 484189; match:", d_exact == 484189, ")")
print("distinct after strip:", d_strip, "-> additional merges:", d_exact - d_strip)
print(
    "distinct after strip+lower:",
    d_strip_lower,
    "-> additional merges vs exact:",
    d_exact - d_strip_lower,
)
print(
    "distinct after strip+casefold:",
    d_strip_casefold,
    "-> merges vs exact:",
    d_exact - d_strip_casefold,
)
print(
    "distinct after whitespace-collapse:", d_ws, "-> merges vs exact:", d_exact - d_ws
)
print(
    "distinct after whitespace-collapse+lower:",
    d_ws_lower,
    "-> merges vs exact:",
    d_exact - d_ws_lower,
)
print("distinct after NFC only:", d_nfc, "-> merges vs exact:", d_exact - d_nfc)
lead = sum(1 for t in nonempty if t != t.lstrip())
trail = sum(1 for t in nonempty if t != t.rstrip())
either = sum(1 for t in nonempty if t != t.strip())
print(
    "rows with leading ws:",
    lead,
    "| trailing ws:",
    trail,
    "| either:",
    either,
    f"({100 * either / N:.4f}%)",
)
# distinct incl. the empty rows (i.e. all 660,622)
print("distinct exact over ALL rows incl. empty:", len(set(texts)))

# ---------------- F9 ----------------
print("\n== F9 ==")
copies = N - d_exact
print("copies (nonempty - distinct):", copies, f"({100 * copies / N:.3f}% of nonempty)")
groups = [(t, c) for t, c in exact.items() if c > 1]
print(
    "groups with size>=2:",
    len(groups),
    "rows in those groups:",
    sum(c for _, c in groups),
)
for t, c in exact.most_common(15):
    print(f"  {c:6d}  {trunc(t)!r}")
c20 = sum(c - 1 for t, c in groups if len(t) <= 20)
c10 = sum(c - 1 for t, c in groups if len(t) <= 10)
c50 = sum(c - 1 for t, c in groups if len(t) <= 50)
c_gt50 = sum(c - 1 for t, c in groups if len(t) > 50)
c_gt100 = sum(c - 1 for t, c in groups if len(t) > 100)
print(
    f"copies with len<=10: {c10} ({100 * c10 / copies:.2f}%) | <=20: {c20} ({100 * c20 / copies:.2f}%) | <=50: {c50} ({100 * c50 / copies:.2f}%) | >50: {c_gt50} | >100: {c_gt100}"
)
top15 = sum(c - 1 for _, c in exact.most_common(15))
print(
    "copies inside the 15 largest groups:",
    top15,
    f"({100 * top15 / copies:.2f}% of copies)",
)
# longest duplicated texts
longdup = sorted(groups, key=lambda kv: -len(kv[0]))[:3]
for t, c in longdup:
    print("  longest duplicated text: len", len(t), "x", c, ":", trunc(t))
# mixed-rating groups
by_text = defaultdict(set)
for r in nonempty_rows:
    by_text[r[1]].add(r[2])
mixed = [
    (t, exact[t])
    for t, rs in by_text.items()
    if exact[t] > 1 and (rs & {"1", "2"}) and (rs & {"4", "5"})
]
print(
    "duplicate groups whose rows span BOTH low (1-2) and high (4-5) star ratings:",
    len(mixed),
    "rows in them:",
    sum(c for _, c in mixed),
)
for t, c in sorted(mixed, key=lambda kv: -kv[1])[:3]:
    print(f"    {c:6d} {trunc(t)!r} ratings={sorted(by_text[t])}")

# ---------------- F5 ----------------
print("\n== F5 ==")
cat = {}


def category(ch):
    c = cat.get(ch)
    if c is None:
        c = cat[ch] = unicodedata.category(ch)
    return c


def has_ln(t):
    return any(category(ch)[0] in "LN" for ch in t)


no_ln = [t for t in nonempty if not has_ln(t)]
no_isalnum = [t for t in nonempty if not any(ch.isalnum() for ch in t)]
no_letter = [t for t in nonempty if not any(category(ch)[0] == "L" for ch in t)]
print(
    "nonempty rows with NO letter or digit (unicodedata L*/N*):",
    len(no_ln),
    f"({100 * len(no_ln) / N:.4f}%)",
    "| distinct texts:",
    len(set(no_ln)),
)
print("nonempty rows with no str.isalnum() char:", len(no_isalnum))
print(
    "nonempty rows with no LETTER at all (digits/symbols only):",
    len(no_letter),
    "| distinct:",
    len(set(no_letter)),
)
for t, c in Counter(no_ln).most_common(3):
    print(f"   ex x{c}: {trunc(t)!r}")
# sub-breakdown of the no-letter/digit rows
only_punct = sum(
    1 for t in no_ln if all(category(ch)[0] in "PZC" or ch.isspace() for ch in t)
)
has_emoji = sum(
    1
    for t in no_ln
    if any(category(ch) in ("So", "Sk") or ord(ch) >= 0x1F000 for ch in t)
)
print(
    "   of which only punctuation/space/control:",
    only_punct,
    "| containing symbol/emoji:",
    has_emoji,
)
# invisible-only: every char is whitespace or category Cf/Cc/Mn/Me or variation selector
invisible = [
    t
    for t in nonempty
    if all(
        ch.isspace() or category(ch) in ("Cf", "Cc", "Mn", "Me", "Cn", "Co") for ch in t
    )
]
print(
    "nonempty-by-strip rows made only of invisible/format/combining chars:",
    len(invisible),
    [ascii(t)[:80] for t in invisible[:3]],
)
# digits only
digits_only = sum(1 for t in nonempty if t.strip().isdigit())
print("rows whose stripped text is digits only:", digits_only)

# ---------------- F6 ----------------
print("\n== F6 ==")
script_cache = {}
MULTI = {
    "CJK": "CJK(Han)",
    "HIRAGANA": "Hiragana",
    "KATAKANA": "Katakana",
    "HANGUL": "Hangul",
    "CANADIAN": "Canadian Aboriginal",
    "OLD": None,
    "NEW": None,
}


def script(ch):
    """Script label for a letter (category L*), from the Unicode character name."""
    s = script_cache.get(ch)
    if s is not None:
        return s
    try:
        name = unicodedata.name(ch)
    except ValueError:
        s = "UNNAMED"
        script_cache[ch] = s
        return s
    tok = name.split()
    first = tok[0]
    if "LATIN" in tok:
        if (
            first in ("FULLWIDTH", "MODIFIER", "SUPERSCRIPT", "SUBSCRIPT")
            or first == "MATHEMATICAL"
        ):
            s = "STYLED-LATIN"
        else:
            s = "LATIN"
    elif first in (
        "MATHEMATICAL",
        "DOUBLE-STRUCK",
        "SCRIPT",
        "BLACK-LETTER",
        "FEMININE",
        "MASCULINE",
        "MICRO",
        "FULLWIDTH",
        "MODIFIER",
        "KELVIN",
        "ANGSTROM",
        "OHM",
        "PLANCK",
        "SUPERSCRIPT",
        "SUBSCRIPT",
        "TURNED",
        "ROTATED",
        "INFORMATION",
        "EULER",
        "ESTIMATED",
    ):
        # letterlike symbols; decide by NFKC fold
        folded = unicodedata.normalize("NFKC", ch)
        if folded != ch and all(
            (not c.isalpha()) or "LATIN" in unicodedata.name(c, "") for c in folded
        ):
            s = "STYLED-LATIN"
        elif first == "MODIFIER":
            s = "MODIFIER-LETTER"
        else:
            s = "STYLED-OTHER(" + first + ")"
    elif first == "HALFWIDTH":
        s = (
            "Katakana"
            if "KATAKANA" in tok
            else ("Hangul" if "HANGUL" in tok else "HALFWIDTH-OTHER")
        )
    elif first == "CJK":
        s = "CJK(Han)"
    elif first in (
        "OLD",
        "NEW",
        "CANADIAN",
        "MEETEI",
        "TAI",
        "SYLOTI",
        "PHAGS-PA",
        "LINEAR",
        "INSCRIPTIONAL",
        "PAU",
        "NYIAKENG",
        "HANIFI",
        "MASARAM",
        "GUNJALA",
        "WARANG",
        "PAHAWH",
        "OL",
        "SORA",
        "ZANABAZAR",
        "CYPRO",
        "IMPERIAL",
        "EGYPTIAN",
        "ANATOLIAN",
    ):
        s = " ".join(tok[:2]).title()
    else:
        s = first.title()
    script_cache[ch] = s
    return s


row_scripts = Counter()
nonlatin_rows = 0
nonlatin_strict_rows = 0  # anything not plain LATIN, incl. styled Latin
only_nonlatin_rows = 0
mixed_rows = 0
nonlatin_texts = []
for t in nonempty:
    ss = set()
    for ch in set(t):
        if category(ch)[0] == "L":
            ss.add(script(ch))
    if not ss:
        continue
    real_non = ss - {"LATIN", "STYLED-LATIN"}
    if ss - {"LATIN"}:
        nonlatin_strict_rows += 1
    if real_non:
        nonlatin_rows += 1
        nonlatin_texts.append(t)
        if "LATIN" in ss:
            mixed_rows += 1
        else:
            only_nonlatin_rows += 1
    for s in ss:
        row_scripts[s] += 1
print(
    "rows with >=1 letter outside Latin script (styled/fullwidth/math Latin counted as Latin):",
    nonlatin_rows,
    f"({100 * nonlatin_rows / N:.4f}% of nonempty)",
)
print(
    "rows with >=1 letter that is not a plain LATIN-named letter (styled Latin counted as non-Latin):",
    nonlatin_strict_rows,
    f"({100 * nonlatin_strict_rows / N:.4f}%)",
)
print(
    "  of the non-Latin rows: no Latin letters at all:",
    only_nonlatin_rows,
    "| mixed with Latin:",
    mixed_rows,
)
print("script row counts (top 14):")
for s, c in row_scripts.most_common(14):
    print(f"   {s:22s} {c:7d} ({100 * c / N:.4f}%)")
# non-ASCII Latin letters (accents): hint at non-English Latin-script text
acc = sum(
    1
    for t in nonempty
    if any(
        ord(ch) > 127 and category(ch)[0] == "L" and script(ch) == "LATIN"
        for ch in set(t)
    )
)
print("rows with accented/non-ASCII LATIN letters:", acc, f"({100 * acc / N:.4f}%)")
# splitter behaviour on non-Latin rows
SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+")


def pieces(t):
    return [p.strip() for p in SPLIT.split(t) if p.strip() != ""]


nl_single = sum(1 for t in nonlatin_texts if len(pieces(t)) == 1)
nl_single200 = sum(1 for t in nonlatin_texts if len(pieces(t)) == 1 and len(t) > 200)
print(
    "non-Latin rows that are a single piece:",
    nl_single,
    f"({100 * nl_single / max(1, len(nonlatin_texts)):.2f}%)",
    "| single piece >200 chars:",
    nl_single200,
)
# heuristic: non-English in Latin script (stopword hits) -- labelled heuristic
STOP = {
    "es": {
        "muy",
        "pero",
        "porque",
        "canciones",
        "aplicación",
        "aplicacion",
        "música",
        "buena",
        "excelente",
        "gracias",
        "mejor",
        "esta",
        "está",
        "anuncios",
        "para",
        "tiene",
        "puedo",
    },
    "pt": {
        "muito",
        "não",
        "nao",
        "aplicativo",
        "músicas",
        "musicas",
        "ótimo",
        "otimo",
        "bom",
        "você",
        "voce",
        "mais",
        "gostei",
        "anúncios",
    },
    "id": {
        "bagus",
        "sangat",
        "tidak",
        "lagu",
        "aplikasi",
        "iklan",
        "banget",
        "saya",
        "bisa",
        "nya",
        "gak",
        "yang",
    },
    "hi-rom": {
        "bahut",
        "accha",
        "achha",
        "acha",
        "nahi",
        "gana",
        "gaana",
        "hai",
        "bohot",
        "kya",
        "mast",
    },
    "tl": {"maganda", "naman", "kasi", "ganda", "lang", "po", "yung", "ako", "sana"},
    "de": {"sehr", "nicht", "aber", "und", "ich", "ist", "werbung"},
    "fr": {"très", "tres", "mais", "avec", "chansons", "c'est", "je", "pas", "musique"},
    "tr": {"çok", "cok", "güzel", "guzel", "ama", "değil", "bir", "şarkı"},
    "it": {"molto", "sono", "canzoni", "più", "perché", "non"},
}
WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)
lang_rows = Counter()
any2 = 0
for t in nonempty:
    ws = set(w.lower() for w in WORD.findall(t))
    best = 0
    for lang, sw in STOP.items():
        k = len(ws & sw)
        if k >= 2:
            lang_rows[lang] += 1
        best = max(best, k)
    if best >= 2:
        any2 += 1
print(
    "HEURISTIC rows with >=2 distinct stopwords from one non-English Latin-script list:",
    any2,
    f"({100 * any2 / N:.3f}%)",
    dict(lang_rows.most_common()),
)

# ---------------- F7 ----------------
print("\n== F7 ==")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
C1 = re.compile(r"[\x80-\x9f]")
ctrl_rows = [t for t in nonempty if CTRL.search(t)]
ctrl_chars = Counter(ch for t in ctrl_rows for ch in CTRL.findall(t))
print(
    "rows with ASCII control chars other than \\t\\n\\r:",
    len(ctrl_rows),
    {f"0x{ord(k):02x}": v for k, v in ctrl_chars.items()},
)
print("rows with C1 controls U+0080-009F:", sum(1 for t in nonempty if C1.search(t)))
print("rows with NUL:", sum(1 for t in nonempty if "\x00" in t))
print(
    "rows with tab:",
    sum(1 for t in nonempty if "\t" in t),
    "| with \\n:",
    sum(1 for t in nonempty if "\n" in t),
    "| with \\r:",
    sum(1 for t in nonempty if "\r" in t),
    "| with \\r not followed by \\n:",
    sum(1 for t in nonempty if re.search(r"\r(?!\n)", t)),
)
print(
    "rows with U+2028/2029/0085 line seps:",
    sum(1 for t in nonempty if re.search("[  \x85]", t)),
)
LIT = [
    "<start_of_turn>",
    "<end_of_turn>",
    "<s>",
    "</s>",
    "[INST]",
    "<|",
    "```",
    "<|im_start|>",
    "<<SYS>>",
    "</review>",
    "<review",
    "{{",
    "}}",
    "{",
    "}",
    "\\",
    '"',
    "<",
    ">",
    "###",
    "Human:",
    "Assistant:",
    "�",
    "​",
    "‮",
    "﻿",
    "‍",
    "️",
]
for lit in LIT:
    c = sum(1 for t in nonempty if lit in t)
    cl = (
        sum(1 for t in nonempty if lit.lower() in t.lower())
        if lit.lower() != lit.upper()
        else c
    )
    print(
        f"  literal {ascii(lit):22s} rows: {c}"
        + (f" (case-insensitive: {cl})" if cl != c else "")
    )
tag = re.compile(r"</?[A-Za-z][A-Za-z0-9_-]*\s*/?>")
tag_rows = [t for t in nonempty if tag.search(t)]
print(
    "rows with an HTML/XML-like tag <word> or </word>:",
    len(tag_rows),
    [trunc(t) for t in tag_rows[:3]],
)
fmt = sum(1 for t in nonempty if any(category(ch) == "Cf" for ch in set(t)))
print("rows with any Unicode format char (Cf: ZWJ, ZWSP, bidi, BOM...):", fmt)
bidi = sum(1 for t in nonempty if re.search("[‪-‮⁦-⁩]", t))
print("rows with bidi override/isolate controls:", bidi)
PHR = [
    "ignore previous",
    "ignore all",
    "ignore the above",
    "system prompt",
    "you are an ai",
    "as an ai",
    "chatgpt",
    "disregard",
    "instruction",
    "prompt",
    "openai",
    "language model",
    "jailbreak",
    "classify",
    "json",
    " ai ",
]
ex_inj = []
for p in PHR:
    hits = [t for t in nonempty if p in t.lower()]
    print(f"  phrase {p!r:22s} rows: {len(hits)}")
    if p in (
        "ignore previous",
        "ignore all",
        "ignore the above",
        "system prompt",
        "you are an ai",
        "as an ai",
        "chatgpt",
    ):
        ex_inj.extend((p, t) for t in hits[:2])
core = [
    "ignore previous",
    "ignore all",
    "ignore the above",
    "system prompt",
    "you are an ai",
    "as an ai",
    "chatgpt",
]
union = [t for t in nonempty if any(p in t.lower() for p in core)]
print("rows matching ANY of the 7 listed instruction-like phrases:", len(union))
for p, t in ex_inj[:14]:
    print(f"    [{p}] {trunc(t)!r}")
