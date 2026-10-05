"""THROWAWAY count of hand labels that the contract's fixed severity rule would change. No model call.

The contract's severity 1 is "No reported problem: praise, neutral/unclear content, or a
pure feature request". So a label whose intent is unclear, praise or request has severity 1
by rule. This counts hand labels that say otherwise. It changes no file.

For the golden file it prints counts only: never a row number, never a value.
"""

import csv
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NO_PROBLEM = ("unclear", "praise", "request")
GOLDEN_SHA = "b9d25cf271d921ec0a2545d2ca4a3ad8655e3b7056ac492b5a0458c5e4f2b79d"  # frozen, dcab9ff


def by_rule(intent, severity):
    """The severity the contract's rule gives this label."""
    return 1 if intent in NO_PROBLEM else int(severity)


def touched(path):
    """(labeled rows, [(sheet row, intent)] where the rule would change the severity)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [
            (n, r) for n, r in enumerate(csv.DictReader(f), 2) if r["intent"].strip()
        ]
    hits = [
        (n, r["intent"])
        for n, r in rows
        if by_rule(r["intent"], r["severity"]) != int(r["severity"])
    ]
    return len(rows), hits


def line(name, n, hits, show_rows):
    c = Counter(i for _, i in hits)
    out = (
        f"{name}: {n} labeled rows; the rule would change {len(hits)}"
        f" (unclear {c['unclear']}, praise {c['praise']}, request {c['request']})"
    )
    return out + (f"; sheet rows {[r for r, _ in hits]}" if show_rows else "")


def main():
    print(
        "rule: intent unclear, praise or request means severity 1 (contract, severity table)"
    )

    # Known answer, read by eye from score_adjudication_out.txt before this script existed:
    # the eight boycott rows labeled unclear with severity 2, and no praise or request row.
    n, hits = touched(ROOT / "evals/adjudication_sheet.csv")
    assert n == 39 and hits == [
        (r, "unclear") for r in (4, 8, 11, 22, 24, 25, 35, 36)
    ], "the count does not reproduce the blind sheet's known rows"
    print(line("blind sheet", n, hits, True))

    n, hits = touched(ROOT / "evals/dev_150_labeled.csv")
    assert n == 29, n
    print(line("development sheet", n, hits, True))

    golden = ROOT / "evals/golden_50_labeled.csv"
    assert hashlib.sha256(golden.read_bytes()).hexdigest() == GOLDEN_SHA, (
        "not the frozen golden file"
    )
    n, hits = touched(golden)
    assert n == 50, n
    print(line("golden 50", n, hits, False))


if __name__ == "__main__":
    main()
