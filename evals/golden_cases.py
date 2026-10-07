"""The golden 50 one review to a row: the hand label, the run's label, and which fields match.

It scores nothing new. It lays the one saved score out case by case, and it refuses to write
unless its own totals equal the saved score's in both readings (validation log entries 36 and 37).

  python3 evals/golden_cases.py --run NAME [--records runs/NAME/grading/records.jsonl.gz]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "evals")]
import score_golden  # noqa: E402
from pipeline import labels  # noqa: E402

FIELDS = score_golden.FIELDS
COLUMNS = (
    "review_id", "status",
    "expected_topic", "predicted_topic", "topic_ok",
    "expected_intent", "predicted_intent", "intent_ok",
    "expected_severity", "expected_severity_by_rule", "predicted_severity", "severity_ok", "severity_ok_by_rule",
    "all_three", "all_three_by_rule",
    "predicted_needs_review", "quote_is_exact_copy", "labeler_note",
)  # fmt: skip


def cases(golden_path, records_path):
    """One row for each golden review, in the golden file's order. A review with no prediction matches nothing."""
    predictions = score_golden._records(records_path)
    out = []
    for row in score_golden._golden(golden_path):
        gold = {
            "topic": row["topic"].strip(),
            "intent": row["intent"].strip(),
            "severity": int(row["severity"]),
        }
        ruled = labels.by_rule(gold["intent"], gold["severity"])
        got = predictions.get(row["review_id"]) or {}
        done = got.get("status") == "completed"
        ok = {f: int(done and str(got[f]) == str(gold[f])) for f in FIELDS}
        severity_by_rule = int(done and got["severity"] == ruled)
        out.append(
            {
                "review_id": row["review_id"],
                "status": got.get("status", "no record"),
                "expected_topic": gold["topic"],
                "predicted_topic": got["topic"] if done else "",
                "topic_ok": ok["topic"],
                "expected_intent": gold["intent"],
                "predicted_intent": got["intent"] if done else "",
                "intent_ok": ok["intent"],
                "expected_severity": gold["severity"],
                "expected_severity_by_rule": ruled,
                "predicted_severity": got["severity"] if done else "",
                "severity_ok": ok["severity"],
                "severity_ok_by_rule": severity_by_rule,
                "all_three": int(all(ok.values())),
                "all_three_by_rule": int(
                    ok["topic"] and ok["intent"] and severity_by_rule
                ),
                "predicted_needs_review": int(bool(got["needs_review"]))
                if done
                else "",
                "quote_is_exact_copy": int(got["evidence_quote"] in row["review_text"])
                if done
                else "",
                "labeler_note": int(bool(row.get("notes", "").strip())),
            }
        )
    return out


def totals(table):
    """The four counts of each reading, named as the saved score names them."""

    def count(key):
        return sum(c[key] for c in table)

    return {
        "as_written": {
            "topic": count("topic_ok"),
            "intent": count("intent_ok"),
            "severity_exact": count("severity_ok"),
            "all_three": count("all_three"),
        },
        "by_rule": {
            "topic": count("topic_ok"),
            "intent": count("intent_ok"),
            "severity_exact": count("severity_ok_by_rule"),
            "all_three": count("all_three_by_rule"),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument(
        "--run",
        required=True,
        help="the run that was scored; names the saved score and the table",
    )
    ap.add_argument("--golden", default=str(ROOT / "evals/golden_50_labeled.csv"))
    ap.add_argument("--records", default=str(ROOT / "grading/records.jsonl"))
    ap.add_argument("--out-dir", default=str(ROOT / "evals"))
    a = ap.parse_args(argv)
    saved = Path(a.out_dir) / f"golden_score_{a.run}.json"
    if not saved.exists():
        print(
            f"refused: no saved score {saved.name}. This lays a score out; it does not make one."
        )
        return 2
    score = json.loads(saved.read_text(encoding="utf-8"))
    table = cases(a.golden, a.records)
    mine = totals(table)
    theirs = {name: {k: score[name][k] for k in mine[name]} for name in mine}
    if mine != theirs or len(table) != score["as_written"]["rows"]:
        print(
            f"refused: the case table does not add up to the saved score. Table {mine}, saved {theirs}. Nothing was written."
        )
        return 2
    out = Path(a.out_dir) / f"golden_cases_{a.run}.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(table)
    r = mine["as_written"]
    print(
        f"{len(table)} rows; topic {r['topic']}, intent {r['intent']}, severity exact {r['severity_exact']}, all three {r['all_three']}: equal to {saved.name}"
    )
    print(f"saved {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
