"""Score a run against the golden 50, once, in both readings (spec section 10 and item 32).

It reads the golden labels and prints counts and review IDs only: never a label Travis
wrote, a quote or a note. The first reading is against the labels as frozen. The second
applies the contract's fixed severity rule to the golden labels by code.

  python3 evals/score_golden.py --run NAME [--records grading/records.jsonl]
"""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from pipeline import labels  # noqa: E402

FIELDS = ("topic", "intent", "severity")


class BadGolden(Exception):
    """A golden cell cannot be read. The message names the row and column and never shows the cell."""


def _golden(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for n, row in enumerate(rows, 2):
        try:
            int(row["severity"])
        except (ValueError, TypeError, KeyError):
            raise BadGolden(f"row {n}: the severity cell is not a whole number") from None
        try:
            if row.get("sentiment", "").strip():
                Decimal(row["sentiment"].strip())
        except (ArithmeticError, ValueError):
            raise BadGolden(f"row {n}: the sentiment cell is not a number") from None
    return rows


def _records(path):
    path = Path(path)
    if not path.exists() and Path(str(path) + ".gz").exists():
        path = Path(str(path) + ".gz")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return {r["review_id"]: r for r in map(json.loads, (line for line in f if line.strip()))}


def score(golden, predictions, *, rule):
    """One reading. `rule` applies the contract's fixed severity rule to the golden severity."""
    agree, diffs, sentiment = Counter(), [], []
    confusion = {f: defaultdict(Counter) for f in FIELDS}
    flag = Counter()
    quotes = Counter()
    disagreements = []
    for row in golden:
        gold = {"topic": row["topic"].strip(), "intent": row["intent"].strip(), "severity": int(row["severity"])}
        if rule:
            gold["severity"] = labels.by_rule(gold["intent"], gold["severity"])
        got = predictions.get(row["review_id"])
        if not got or got.get("status") != "completed":
            disagreements.append({"review_id": row["review_id"], "fields": ["no prediction"]})
            agree["missing"] += 1
            continue
        wrong = [f for f in FIELDS if str(got[f]) != str(gold[f])]
        for f in FIELDS:
            agree[f] += f not in wrong
            confusion[f][str(gold[f])][str(got[f])] += 1
        agree["all_three"] += not wrong
        diffs.append(got["severity"] - gold["severity"])
        if row.get("sentiment", "").strip():
            sentiment.append(abs(Decimal(str(got["sentiment"])) - Decimal(row["sentiment"].strip())))
        if wrong:
            disagreements.append({"review_id": row["review_id"], "fields": wrong})
        flag["wrong_labels" if wrong else "right_labels"] += 1
        if got["needs_review"]:
            flag["wrong_caught" if wrong else "right_flagged"] += 1
        quotes["checked"] += 1
        quotes["exact"] += got["evidence_quote"] in row["review_text"]
    n = len(diffs)
    return {
        "rows": len(golden),
        "missing_predictions": agree["missing"],
        "topic": agree["topic"],
        "intent": agree["intent"],
        "severity_exact": agree["severity"],
        "all_three": agree["all_three"],
        "severity_error": {
            "mean_signed": str(Decimal(sum(diffs)) / n) if n else None,
            "mean_unsigned": str(Decimal(sum(map(abs, diffs))) / n) if n else None,
            "on_rows": n,
        },
        "sentiment_mean_abs_error": str(sum(sentiment, Decimal(0)) / len(sentiment)) if sentiment else None,
        "golden_rows_per_topic": dict(Counter(r["topic"].strip() for r in golden)),
        "confusion": {f: {g: dict(row) for g, row in sorted(table.items())} for f, table in confusion.items()},
        "ambiguous_cases": sum(bool(r.get("notes", "").strip()) for r in golden),
        "needs_review": {k: flag[k] for k in ("wrong_labels", "wrong_caught", "right_labels", "right_flagged")},
        "quotes_exact_copies": dict(quotes) or {"checked": 0, "exact": 0},
        "disagreements": disagreements,
    }


def report(golden_path, records_path):
    golden, predictions = _golden(golden_path), _records(records_path)
    changed = sum(labels.by_rule(r["intent"].strip(), r["severity"]) != int(r["severity"]) for r in golden)
    return {
        "as_written": score(golden, predictions, rule=False),
        "by_rule": score(golden, predictions, rule=True),
        "rule_changes": changed,
        "rule": "intent unclear, praise or request means severity 1 (the contract's severity table), applied to the golden labels by code",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--run", required=True, help="the run being scored; names the output file")
    ap.add_argument("--golden", default=str(ROOT / "evals/golden_50_labeled.csv"))
    ap.add_argument("--records", default=str(ROOT / "grading/records.jsonl"))
    ap.add_argument("--out-dir", default=str(ROOT / "evals"))
    ap.add_argument("--again", action="store_true", help="score again although a result exists; say why in the validation log")
    a = ap.parse_args(argv)
    out = Path(a.out_dir) / f"golden_score_{a.run}.json"
    if out.exists() and not a.again:
        print(f"refused: {out.name} already exists. The golden 50 is scored once on the final setup.")
        return 2
    try:
        result = report(a.golden, a.records)
    except BadGolden as e:
        print(f"refused: {e}. Nothing was scored.")
        return 2
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name, title in (("as_written", "against the labels as frozen"), ("by_rule", "with the contract's fixed severity rule applied")):
        r = result[name]
        e, q, f = r["severity_error"], r["quotes_exact_copies"], r["needs_review"]
        print(f"{title}: {r['rows']} rows, {r['missing_predictions']} with no prediction")
        print(f"  topic {r['topic']}, intent {r['intent']}, severity exact {r['severity_exact']}, all three {r['all_three']}")
        print(f"  severity error on {e['on_rows']} rows: mean {e['mean_signed']}, mean absolute {e['mean_unsigned']}")
        print(f"  needs_review caught {f['wrong_caught']} of {f['wrong_labels']} wrong labels and flagged {f['right_flagged']} of {f['right_labels']} right ones")
        print(f"  quotes that are exact copies: {q['exact']} of {q['checked']}; ambiguous cases noted: {r['ambiguous_cases']}")
        print(f"  disagreements (review ID: fields): {'; '.join(d['review_id'] + ': ' + ', '.join(d['fields']) for d in r['disagreements']) or 'none'}")
    print(f"the rule changes {result['rule_changes']} golden labels; saved {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
