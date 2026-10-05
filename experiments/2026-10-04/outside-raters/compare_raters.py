"""THROWAWAY comparison of the two outside raters. No model call. Not pipeline code.

Reads the saved rater answers, reports where they agree, checks them against the hand
labels and the planted cases, and writes the blind sheet for Travis:
  evals/adjudication_sheet.csv   review text and blank label columns, in hash order
  evals/adjudication_key.json    which rows are disputed and which are agreed checks

The sheet never shows a rater's answer or which kind of row it is.
"""

import ast
import csv
import hashlib
import json
import re
import sys
from collections import Counter

import raters

ROOT = raters.ROOT
EFFORT = sys.argv[1] if len(sys.argv) > 1 else "medium"
F = ("topic", "intent", "severity")
SEED = "adjudicate-v1"
N_AGREED = 15


def same(a, b, fields=F):
    return all(str(a[f]) == str(b[f]) for f in fields)


def show(x):
    return "/".join(str(x[f]) for f in F)


def main():
    items = {i["id"]: i for i in raters.items()}
    got = {
        p: {r["id"]: r for r in raters.saved(p, EFFORT)}
        for p in ("anthropic", "openai")
    }
    for p, rows in got.items():
        bad = [k for k, r in rows.items() if not r["labels"]]
        print(
            f"{p}: {len(rows)} saved at {EFFORT} effort, {len(bad)} without labels, refused {sum(r['refused'] for r in rows.values())}, spend at every setting ${sum(r['cost_usd'] for r in raters.saved(p)):.2f}"
        )
    A = {k: r["labels"] for k, r in got["anthropic"].items() if r["labels"]}
    O = {k: r["labels"] for k, r in got["openai"].items() if r["labels"]}
    both = [k for k in items if k in A and k in O]
    print(f"rated by both: {len(both)} of {len(items)}")

    # Guards: a measure that reads itself, or a bad join, must not pass quietly.
    for name, L in (("fable", A), ("astra", O)):
        assert len({v["topic"] for v in L.values()}) > 2, (
            f"degenerate: {name} used almost one topic"
        )
    agree = [k for k in both if same(A[k], O[k])]
    assert 0.3 < len(agree) / len(both) < 1.0, (
        f"agreement {len(agree)}/{len(both)} is not believable"
    )

    print("\n== rater against rater ==")
    for s in ("dev", "boycott", "planted", None):
        ks = [k for k in both if s is None or items[k]["set"] == s]
        per = {f: sum(same(A[k], O[k], (f,)) for k in ks) for f in F}
        print(
            f"{s or 'all':8s} n={len(ks):3d}  all three {sum(same(A[k], O[k]) for k in ks):3d}  topic {per['topic']:3d}  intent {per['intent']:3d}  severity {per['severity']:3d}"
        )
    gap = Counter(abs(A[k]["severity"] - O[k]["severity"]) for k in both)
    print(f"severity gap between raters: {dict(sorted(gap.items()))}")

    # The 29 hand-labeled development rows, as they stand and as first written.
    with open(
        ROOT / "evals/dev_150_labeled.csv", encoding="utf-8-sig", newline=""
    ) as f:
        sheet = [(n, r) for n, r in enumerate(csv.DictReader(f), 2)]
    labeled = [(n, r) for n, r in sheet if r["intent"].strip()]
    assert len(labeled) == 29, len(labeled)
    print("\n== against the 29 hand labels ==")
    revised = {}
    for n, r in labeled:
        m = re.search(r"revised .*?: (topic|intent|severity) was (\w+)", r["notes"])
        if m:
            revised[r["review_id"]] = (n, m.group(1), m.group(2))
    assert len(revised) == 5, revised
    for name, L in (("fable", A), ("astra", O)):
        now = sum(same(L[r["review_id"]], r) for _, r in labeled)
        first = sum(
            same(
                L[r["review_id"]],
                {**r, revised[r["review_id"]][1]: revised[r["review_id"]][2]}
                if r["review_id"] in revised
                else r,
            )
            for _, r in labeled
        )
        per = {f: sum(same(L[r["review_id"]], r, (f,)) for _, r in labeled) for f in F}
        print(
            f"{name}: all three {now}/29 against the labels as they stand, {first}/29 against the labels as first written | topic {per['topic']}, intent {per['intent']}, severity {per['severity']}"
        )
    print("the five revised rows (field: first -> revised | fable, astra):")
    for rid, (n, field, was) in sorted(revised.items(), key=lambda kv: kv[1][0]):
        r = dict(labeled)[n]
        print(
            f"  row {n} {field}: {was} -> {r[field]} | {A[rid][field]}, {O[rid][field]}"
        )
    for n, r in labeled:
        if n in (5, 19, 29):
            print(
                f"  row {n} severity: yours {r['severity']} | fable {A[r['review_id']]['severity']}, astra {O[r['review_id']]['severity']}"
            )

    # Anchor from outside this script: rows where Jev, Gemma and the hand label all agree.
    sys.path.insert(0, str(ROOT / "experiments/2026-10-04/tool-choice"))
    from compare import gemma_records
    from score_spike import simple_records

    J, G = simple_records(), gemma_records()
    firm = [
        r
        for _, r in labeled
        if same(J[r["review_id"]], r) and same(G[r["review_id"]], r)
    ]
    assert len(firm) == 21, len(firm)
    for name, L in (("fable", A), ("astra", O)):
        hit = sum(same(L[r["review_id"]], r) for r in firm)
        print(
            f"anchor: {name} matches {hit} of the {len(firm)} rows where Jev, Gemma and the hand label agree"
        )
        assert hit >= 15, f"{name} fails the anchor; check the join"

    # Planted cases against the answers written from the contract.
    tree = ast.parse(raters.CASES_SRC.read_text(encoding="utf-8"))
    cases = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "CASES"
    )
    print("\n== planted cases (expected answers were written by the assistant) ==")
    off = set()
    for name, L in (("fable", A), ("astra", O)):
        right = Counter()
        for cid, group, _, topics, intents, sevs in cases:
            x = L[f"planted:{cid}"]
            ok = (
                x["topic"] in topics
                and x["intent"] in intents
                and x["severity"] in sevs
            )
            right[group] += ok
            if not ok:
                off.add(f"planted:{cid}")
        total = Counter(c[1] for c in cases)
        print(
            f"{name}: {sum(right.values())}/25  "
            + "  ".join(f"{g} {right[g]}/{total[g]}" for g in total)
        )
    print(
        f"planted cases where a rater differs from the expected answer: {sorted(k.split(':')[1] for k in off)}"
    )

    # The blind sheet: disputed rows, differing planted cases, and a hash-picked check of agreed rows.
    done = {r["review_id"] for _, r in labeled}
    open_rows = [
        k for k in both if items[k]["set"] in ("dev", "boycott") and k not in done
    ]
    disputed = [k for k in open_rows if not same(A[k], O[k])]
    agreed = sorted(
        (k for k in open_rows if same(A[k], O[k])),
        key=lambda k: hashlib.sha256(f"{SEED}:{k}".encode()).hexdigest(),
    )[:N_AGREED]
    picked = {
        **{k: "disputed" for k in disputed},
        **{k: "planted_differs" for k in off},
        **{k: "agreed_check" for k in agreed},
    }
    order = sorted(
        picked, key=lambda k: hashlib.sha256(f"{SEED}:order:{k}".encode()).hexdigest()
    )
    sheet_path = ROOT / "evals/adjudication_sheet.csv"
    if sheet_path.exists():
        # Never rewrite the sheet: Travis may already have typed labels into it.
        with open(sheet_path, encoding="utf-8-sig", newline="") as f:
            assert [r["review_id"] for r in csv.DictReader(f)] == order, "sheet rows differ"
        print("\nsheet already exists with these rows; left untouched")
    else:
        with open(sheet_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["review_id", "review_text", "intent", "topic", "severity", "needs_review", "notes"])
            for k in order:
                w.writerow([k, items[k]["text"], "", "", "", "", ""])
        (ROOT / "evals/adjudication_key.json").write_text(
            json.dumps({"seed": SEED, "effort": EFFORT, "rows": picked}, indent=1) + "\n",
            encoding="utf-8",
        )
    kinds = Counter(picked.values())
    by_set = Counter(items[k]["set"] for k in disputed)
    print(f"\n== sheet for Travis: {len(order)} rows ==")
    print(
        f"disputed {kinds['disputed']} (development {by_set['dev']} of {sum(items[k]['set'] == 'dev' for k in open_rows)}, boycott {by_set['boycott']} of 60), planted {kinds['planted_differs']}, agreed checks {kinds['agreed_check']}"
    )
    print(
        f"disputed among the 29 already labeled (not on the sheet): {sum(not same(A[k], O[k]) for k in done)}"
    )
    tune = {
        r["review_id"]: r["split"]
        for r in csv.DictReader(
            open(ROOT / "evals/boycott_60.csv", encoding="utf-8", newline="")
        )
    }
    print(
        f"boycott disputed by split: {dict(Counter(tune[k] for k in disputed if k in tune))}"
    )
    print(
        "boycott intents, fable:",
        dict(Counter(A[k]["intent"] for k in both if items[k]["set"] == "boycott")),
        "| astra:",
        dict(Counter(O[k]["intent"] for k in both if items[k]["set"] == "boycott")),
    )


if __name__ == "__main__":
    main()
