"""THROWAWAY import of hand labels from a Numbers document into a label CSV. No model call.

Numbers keeps its own iCloud document and never writes back to the CSV it opened. This
copies the document, exports the copy as CSV through Numbers, and fills the repo CSV by
review_id. Review text always comes from the repo CSV. Only blank cells are filled.

It prints row numbers, column names and counts. It never prints a label value, so it is
safe for the golden sheet.

  import_numbers.py TARGET.csv --numbers DOC.numbers           check only, writes nothing
  import_numbers.py TARGET.csv --numbers DOC.numbers --write   fill TARGET.csv if the check is clean
  import_numbers.py TARGET.csv --from-csv EXPORT.csv           an export made by hand, no Numbers
"""

import argparse
import csv
import hashlib
import io
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Copied from evals/golden_labeling_guide.md.
ALLOWED = {
    "intent": {"cancellation", "complaint", "request", "praise", "unclear"},
    "topic": {
        "access",
        "usability",
        "playback",
        "downloads",
        "catalog",
        "billing",
        "support",
        "other",
    },
    "severity": {"1", "2", "3", "4", "5"},
    "sentiment": {"-1", "-0.5", "0", "0.5", "1"},
    "needs_review": {"TRUE", "FALSE"},
}
KEEP = ("review_id", "review_text")  # always from the repo CSV
OPTIONAL = ("entities", "notes")

# Opens the copy, exports it, closes it unsaved. It never brings Numbers to the front.
SCRIPT = """
on run argv
    set src to POSIX file (item 1 of argv)
    set dst to POSIX file (item 2 of argv)
    tell application "Numbers"
        set d to open src
        export d to dst as CSV
        close d saving no
    end tell
end run
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    raw = Path(path).read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    eol = "\r\n" if b"\r\n" in raw else "\n"
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    header = rows[0]
    return header, [dict(zip(header, r, strict=True)) for r in rows[1:]], bom, eol


def dump_csv(header, rows, bom, eol):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator=eol)
    w.writerow(header)
    w.writerows([r[c] for c in header] for r in rows)
    return (b"\xef\xbb\xbf" if bom else b"") + buf.getvalue().encode("utf-8")


def tidy(col, v, text):
    """Format only: spacing, letter case, how a number is written. Never which value."""
    if col == "evidence_quote":
        return v if v in text or v.strip() not in text else v.strip()
    v = v.strip()
    if col in ("intent", "topic"):
        return v.lower()
    if col == "needs_review":
        return v.upper()
    if col in ("severity", "sentiment") and v:
        try:
            d = Decimal(v.replace("−", "-"))
        except InvalidOperation:
            return v
        return "0" if d == 0 else format(d.normalize(), "f")  # 3.0 -> 3, 0.50 -> 0.5
    return v


def from_numbers(doc, tmp):
    copy = tmp / Path(doc).name
    shutil.copy2(doc, copy)
    print(f"Numbers document: {Path(doc).name}, SHA-256 {sha(copy)}")
    out = tmp / "export.csv"
    subprocess.run(
        ["osascript", "-e", SCRIPT, str(copy), str(out)], check=True, timeout=120
    )
    assert sha(copy) == sha(doc), "the document changed while it was being exported"
    # One table exports as a file, several as a folder of files.
    files = [out] if out.is_file() else sorted(out.rglob("*.csv"))
    hits = [f for f in files if "review_id" in read_csv(f)[0]]
    assert len(hits) == 1, f"{len(hits)} exported tables have a review_id column"
    return hits[0]


def check(header, rows):
    """Problems as (sheet row, column, what). No values."""
    out = []
    for n, r in enumerate(rows, 2):
        for col in header:
            if col in KEEP or col in OPTIONAL:
                continue
            v = r[col]
            if not v.strip():
                out.append((n, col, "blank"))
            elif col in ALLOWED and v not in ALLOWED[col]:
                out.append((n, col, "not in the list"))
            elif col == "evidence_quote" and v not in r["review_text"]:
                out.append((n, col, "not an exact copy of the text"))
    return out


def odd_entities(rows):
    """Rows whose entities cell is not lowercase names split by ';'. Shape only, not blocking."""
    out = {}
    for n, r in enumerate(rows, 2):
        v = r.get("entities", "").strip()
        if not v:
            continue
        parts = [p.strip() for p in v.split(";")]
        if v != v.lower():
            out.setdefault("has capital letters", []).append(n)
        if "," in v:
            out.setdefault("has a comma", []).append(n)
        if not all(parts):
            out.setdefault("has an empty name", []).append(n)
        if any(p.upper() in ALLOWED["needs_review"] for p in parts):
            out.setdefault("reads TRUE or FALSE", []).append(n)
    return out


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("target", help="the repo CSV to fill")
    ap.add_argument("--numbers", help="the Numbers document")
    ap.add_argument("--from-csv", help="an export made by hand")
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--keep-export",
        help="also save the export here. It holds label values: keep it out of git",
    )
    ap.add_argument(
        "--earlier",
        help="an export kept from an earlier run; reports which cells changed since",
    )
    a = ap.parse_args()
    assert bool(a.numbers) != bool(a.from_csv), "give --numbers or --from-csv, not both"

    header, rows, bom, eol = read_csv(a.target)
    before = Path(a.target).read_bytes()
    held = [tuple(r[c] for c in KEEP) for r in rows]  # IDs and texts as they were
    labels = [c for c in header if c not in KEEP]
    print(f"target: {a.target}, {len(rows)} rows, SHA-256 {sha(a.target)[:16]} before")
    if dump_csv(header, rows, bom, eol) != before:
        print(
            "note: rewriting changes this file's quoting; the cell contents stay the same"
        )

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(a.from_csv) if a.from_csv else from_numbers(a.numbers, Path(tmp))
        xh, xrows, _, _ = read_csv(src)
        if a.keep_export:
            shutil.copy2(src, a.keep_export)
            print(f"export kept: {a.keep_export}, SHA-256 {sha(a.keep_export)}")
    blank_ids = sum(not r["review_id"].strip() for r in xrows)
    xrows = [r for r in xrows if r["review_id"].strip()]
    ids = Counter(r["review_id"].strip() for r in xrows)
    assert max(ids.values()) == 1, "a review_id repeats in the export"
    assert set(ids) == {r["review_id"] for r in rows}, (
        f"IDs differ: {len(set(ids) - {r['review_id'] for r in rows})} only in the export, "
        f"{len({r['review_id'] for r in rows} - set(ids))} only in the target"
    )
    missing = [c for c in labels if c not in xh]
    assert not missing, f"export has no column {missing}"
    extra = [c for c in xh if c not in header and c.strip()]
    print(
        f"export: {len(xrows)} rows with an ID, {blank_ids} without (dropped), "
        f"extra columns ignored: {extra or 'none'}"
    )
    X = {r["review_id"].strip(): r for r in xrows}

    if a.earlier:
        # What changed since an earlier export: which cells, never what they hold.
        E = {
            r["review_id"].strip(): r
            for r in read_csv(a.earlier)[1]
            if r["review_id"].strip()
        }
        assert set(E) == set(X), "the earlier export holds different reviews"
        cells = [
            (n, c, E[r["review_id"]][c], X[r["review_id"]][c])
            for n, r in enumerate(rows, 2)
            for c in labels
        ]
        newly = [(n, c) for n, c, old, new in cells if not old.strip() and new.strip()]
        changed = [(n, c) for n, c, old, new in cells if old.strip() and old != new]
        print(
            f"since the earlier export (SHA-256 {sha(a.earlier)[:16]}): {len(newly)} blank cells filled"
            f" {newly}; cells that held a value and changed: {changed or 'none'}"
        )

    # Anchor: the join is right only if the text beside each ID is the text we already hold.
    text_off = [
        n
        for n, r in enumerate(rows, 2)
        if X[r["review_id"]]["review_text"] != r["review_text"]
    ]
    assert len(text_off) < len(rows) / 2, (
        "most texts differ from the source: wrong document or a bad join"
    )
    print(
        f"review text differs in the Numbers copy on rows {text_off or 'none'}; the repo text is kept"
    )

    tidied, filled, kept = Counter(), Counter(), []
    for n, r in enumerate(rows, 2):
        for col in labels:
            raw = X[r["review_id"]][col]
            new = tidy(col, raw, r["review_text"])
            tidied[col] += new != raw
            if r[col].strip():
                if r[col] != new:
                    kept.append((n, col))
                continue
            r[col] = new
            filled[col] += bool(new)
    print(
        "cells filled:   " + "  ".join(f"{c} {filled[c]}/{len(rows)}" for c in labels)
    )
    print(
        "format tidied:  "
        + ("  ".join(f"{c} {v}" for c, v in tidied.items() if v) or "none")
    )
    if kept:
        print(f"already filled in the target and left alone: {kept}")
    assert sum(filled.values()), "nothing was filled: the export holds no labels"

    for what, ns in odd_entities(rows).items():
        print(f"worth a look, not blocking: entities {what} on rows {ns}")
    problems = check(header, rows)
    if problems:
        print(f"\n{len(problems)} format problems (sheet row, column):")
        for what in sorted({p[2] for p in problems}):
            by_col = {}
            for n, col, w in problems:
                if w == what:
                    by_col.setdefault(col, []).append(n)
            for col, ns in by_col.items():
                print(f"  {what}: {col} rows {ns}")
        print("nothing written. Fix these in Numbers and run again.")
        sys.exit(1)
    print("\nformat check: clean")

    if not a.write:
        print("check only, nothing written (add --write)")
        return
    Path(a.target).write_bytes(dump_csv(header, rows, bom, eol))
    h2, back, _, _ = read_csv(a.target)
    assert h2 == header and [tuple(r[c] for c in KEEP) for r in back] == held, (
        "IDs or texts changed on write"
    )
    print(f"written: {a.target}, SHA-256 {sha(a.target)}")


if __name__ == "__main__":
    main()
