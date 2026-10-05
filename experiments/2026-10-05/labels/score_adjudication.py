"""THROWAWAY scoring of Travis's blind sheet against the two outside raters. No model call.

  score_adjudication.py                   score evals/adjudication_sheet.csv
  score_adjudication.py --test-sheet P    score a made-up sheet; every line is marked TEST

It refuses the real sheet unless it is committed and unchanged since. The labels are frozen
before any rater answer for these rows is shown (validation log entry 16).
"""

import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/2026-10-04/outside-raters"))
import raters  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from rule_check import by_rule  # noqa: E402

F = ("topic", "intent", "severity")
SHEET = ROOT / "evals/adjudication_sheet.csv"
KEY = ROOT / "evals/adjudication_key.json"


def same(a, b, fields=F):
    return all(str(a[f]) == str(b[f]) for f in fields)


def show(x):
    return "/".join(str(x[f]) for f in F)


def frozen():
    """The commit that holds the sheet exactly as it is on disk, or stop."""
    rel = str(SHEET.relative_to(ROOT))

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    assert not git("status", "--porcelain", "--", rel), (
        "the sheet has uncommitted changes. Commit it first: that is the freeze"
    )
    return git("log", "-1", "--format=%h, committed %cI", "--", rel)


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--test-sheet", help="a made-up sheet, for testing this script")
    a = ap.parse_args()
    path = Path(a.test_sheet) if a.test_sheet else SHEET
    tag = "TEST, made-up labels: " if a.test_sheet else ""

    key = json.loads(KEY.read_text(encoding="utf-8"))
    kind = key["rows"]
    items = {i["id"]: i for i in raters.items()}
    A, O = (
        {r["id"]: r["labels"] for r in raters.saved(p, key["effort"]) if r["labels"]}
        for p in ("anthropic", "openai")
    )
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [(n, r) for n, r in enumerate(csv.DictReader(f), 2)]
    order = [r["review_id"] for _, r in rows]

    # Guards: a wrong file or a bad join must stop here, not turn into a score.
    assert set(order) == set(kind) and len(order) == len(kind), (
        "sheet and key rows differ"
    )
    assert Counter(kind.values()) == {
        "disputed": 23,
        "planted_differs": 1,
        "agreed_check": 15,
    }
    for n, r in rows:
        assert r["review_text"] == items[r["review_id"]]["text"], (
            f"row {n}: text is not the source text"
        )
        assert (
            r["topic"] in raters.TOPICS
            and r["intent"] in raters.INTENTS
            and r["severity"] in ("1", "2", "3", "4", "5")
            and r["needs_review"] in ("TRUE", "FALSE")
        ), f"row {n}: a label is blank or outside the lists"
    H = {
        r["review_id"]: {
            "topic": r["topic"],
            "intent": r["intent"],
            "severity": int(r["severity"]),
        }
        for _, r in rows
    }
    for k, v in kind.items():
        # The key was built from the raters' answers, so it must still describe them.
        assert same(A[k], O[k]) == (v == "agreed_check"), (
            f"key and rater files disagree on {k}"
        )

    if a.test_sheet:
        print(f"{tag}{path}")
    else:
        print(f"sheet: {SHEET.relative_to(ROOT)}, commit {frozen()}")
        print(f"SHA-256 {hashlib.sha256(SHEET.read_bytes()).hexdigest()}")
    flagged = [n for n, r in rows if r["needs_review"] == "TRUE"]
    noted = [n for n, r in rows if r["notes"].strip()]
    print(
        f"{tag}{len(rows)} rows; needs_review TRUE on {len(flagged)}; a note on {len(noted)}"
    )

    by = {v: [k for k in order if kind[k] == v] for v in set(kind.values())}
    agreed, disputed, (pid,) = by["agreed_check"], by["disputed"], by["planted_differs"]
    real = agreed + disputed

    def sets(ks):
        c = Counter(items[k]["set"] for k in ks)
        return f"development {c['dev']}, boycott {c['boycott']}"

    print(
        f"\n{tag}== the {len(agreed)} agreed checks ({sets(agreed)}): both raters gave one answer =="
    )
    hit = [k for k in agreed if same(H[k], A[k])]
    per = {f: sum(same(H[k], A[k], (f,)) for k in agreed) for f in F}
    print(
        f"{tag}your label is the same on all three: {len(hit)} of {len(agreed)}"
        f" | topic {per['topic']}, intent {per['intent']}, severity {per['severity']}"
    )
    print(f"{tag}  of those, {sets(hit)}")

    print(
        f"\n{tag}== the {len(disputed)} disputed rows ({sets(disputed)}): the raters differ =="
    )
    side = Counter()
    for k in disputed:
        fa, fo = same(H[k], A[k]), same(H[k], O[k])
        # Which direction of failure would look like success: a label compared with itself.
        assert not (fa and fo), (
            "one label equals two different answers: the join is wrong"
        )
        side["fable" if fa else "astra" if fo else "neither"] += 1
    print(
        f"{tag}all three fields: you match Fable {side['fable']}, Astra {side['astra']},"
        f" neither {side['neither']}"
    )
    for f in F:
        ks = [k for k in disputed if not same(A[k], O[k], (f,))]
        c = Counter(
            "fable"
            if same(H[k], A[k], (f,))
            else "astra"
            if same(H[k], O[k], (f,))
            else "neither"
            for k in ks
        )
        rest = [k for k in disputed if k not in ks]
        shared = sum(same(H[k], A[k], (f,)) for k in rest)
        print(
            f"{tag}  {f:8s} raters differ on {len(ks):2d}: you give Fable's {c['fable']},"
            f" Astra's {c['astra']}, neither {c['neither']}"
            f" | raters agree on {len(rest):2d}: you give theirs on {shared}"
        )

    print(f"\n{tag}== each rater against you, the {len(real)} real reviews ==")
    for name, L in (("Fable", A), ("Astra", O)):
        per = {f: sum(same(H[k], L[k], (f,)) for k in real) for f in F}
        gap = Counter(H[k]["severity"] - L[k]["severity"] for k in real)
        print(
            f"{tag}{name}: all three {sum(same(H[k], L[k]) for k in real)} of {len(real)}"
            f" | topic {per['topic']}, intent {per['intent']}, severity {per['severity']}"
            f" | your severity minus theirs: {dict(sorted(gap.items()))}"
        )

    # Second reading, ruled by Travis on 2026-10-05: the labels stay as frozen, and every
    # score is also shown with the contract's fixed severity rule applied to them by code.
    H2 = {
        k: {**h, "severity": by_rule(h["intent"], h["severity"])} for k, h in H.items()
    }
    moved = [n for n, r in rows if H2[r["review_id"]] != H[r["review_id"]]]
    # A rule that rewrites most labels would lift every score: stop, do not report it.
    assert len(moved) < len(rows) / 2, "the rule changed most of the labels"
    broke = {
        name: sum(
            by_rule(L[k]["intent"], L[k]["severity"]) != L[k]["severity"] for k in order
        )
        for name, L in (("Fable", A), ("Astra", O))
    }
    print(
        f"\n{tag}== second reading: the contract's fixed rule applied to your labels by code =="
    )
    print(
        f"{tag}rule: intent unclear, praise or request means severity 1."
        f" It changes {len(moved)} of your labels (sheet rows {moved})."
        f" Rater labels that break it: Fable {broke['Fable']}, Astra {broke['Astra']}"
    )
    hit2 = [k for k in agreed if same(H2[k], A[k])]
    print(
        f"{tag}agreed checks: all three {len(hit2)} of {len(agreed)} (was {len(hit)})"
        f" | severity {sum(same(H2[k], A[k], ('severity',)) for k in agreed)}"
        f" (was {sum(same(H[k], A[k], ('severity',)) for k in agreed)})"
    )
    side2 = Counter(
        "fable" if same(H2[k], A[k]) else "astra" if same(H2[k], O[k]) else "neither"
        for k in disputed
    )
    print(
        f"{tag}disputed rows: you match Fable {side2['fable']}, Astra {side2['astra']},"
        f" neither {side2['neither']}"
        f" (was {side['fable']}, {side['astra']}, {side['neither']})"
    )
    for name, L in (("Fable", A), ("Astra", O)):
        print(
            f"{tag}{name}: all three {sum(same(H2[k], L[k]) for k in real)} of {len(real)}"
            f" (was {sum(same(H[k], L[k]) for k in real)})"
            f" | severity {sum(same(H2[k], L[k], ('severity',)) for k in real)}"
            f" (was {sum(same(H[k], L[k], ('severity',)) for k in real)})"
        )

    # Planted case. Known answer from validation log entry 13: Astra matches the expected
    # answer on this case and Fable does not. If that fails, the files are not the ones scored then.
    tree = ast.parse(raters.CASES_SRC.read_text(encoding="utf-8"))
    cases = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "CASES"
    )
    _, _, _, topics, intents, sevs = next(c for c in cases if f"planted:{c[0]}" == pid)

    def ok(x):
        return x["topic"] in topics and x["intent"] in intents and x["severity"] in sevs

    assert ok(O[pid]) and not ok(A[pid]), (
        "planted case does not match the recorded result"
    )
    print(
        f"\n{tag}== planted case {pid.split(':')[1]} (expected answer written by the assistant) =="
    )
    print(
        f"{tag}expected topic {sorted(topics)}, intent {sorted(intents)}, severity {sorted(sevs)}"
        f" | yours {show(H[pid])} ({'matches' if ok(H[pid]) else 'differs'})"
        f" | Fable {show(A[pid])} | Astra {show(O[pid])}"
    )

    print(f"\n{tag}== row by row (topic/intent/severity; * = differs from yours) ==")
    print(
        f"{tag}row  kind      set      yours                      Fable                       Astra"
    )
    for n, r in rows:
        k = r["review_id"]
        cells = [show(L[k]) + ("" if same(H[k], L[k]) else " *") for L in (A, O)]
        mark = "  needs_review" if r["needs_review"] == "TRUE" else ""
        print(
            f"{tag}{n:3d}  {kind[k].split('_')[0]:8s}  {items[k]['set']:7s}  {show(H[k]):25s}"
            f"  {cells[0]:26s}  {cells[1]}{mark}"
        )


if __name__ == "__main__":
    main()
