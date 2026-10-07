"""Label the cut-off-half reviews the pilot does not cover, so the cut-off table has all 60 (spec item 24).

The cut-off half is 60 development reviews held back for choosing the needs_review cut-off.
The 100-review pilot covers 32 of them. This labels the rest once, with the frozen wording,
and saves each answer with its lowest top probability. No golden review is among them.

  python3 evals/cutoff_rows.py --standin
  python3 evals/cutoff_rows.py --go --have PILOT_ANSWERS.jsonl          paid: 28 requests
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "evals")]
import common  # noqa: E402

OUT = ROOT / "evals/cutoff_rows_out.jsonl"


def missing(have_ids):
    """The cut-off-half reviews with no answer yet, in the half's own order."""
    _, cutoff_half = common.halves()
    text = {r["review_id"]: r["review_text"] for r in common._sheet("dev_150_labeled.csv")}
    return [{"id": i, "text": text[i]} for i in cutoff_half if i not in have_ids]


def run(ask, items):
    rows = []
    for item in items:
        record = ask(item["id"], item["text"])
        if record.get("invalid"):
            rows.append({"review_id": item["id"], "invalid": record["invalid"]})
            continue
        rows.append(
            {"review_id": item["id"], "topic": record["topic"], "intent": record["intent"], "severity": record["severity"], "min_top": record["min_top_probability"]}
        )
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    common.add_arguments(ap)
    ap.add_argument("--have", action="append", default=[], help="saved answers that already cover some rows (may be given more than once)")
    a = ap.parse_args(argv)
    have = set()
    for path in a.have:
        have |= {json.loads(line)["review_id"] for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}
    if OUT.exists() and a.go:
        print(f"refused: {OUT.name} is already there. These rows are labeled once.")
        return 2
    todo = missing(have)
    with common.session(a, "cut-off rows") as paid:
        if paid is None:
            return 2
        rows = run(paid.ask, todo)
    if a.go:
        OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    else:
        print("stand-in run: nothing saved")
    print(f"labeled {sum('invalid' not in r for r in rows)} of {len(todo)} cut-off-half rows that had no answer; {sum('invalid' in r for r in rows)} invalid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
