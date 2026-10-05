"""Score the held-back cases once, with the frozen wording: 30 real boycott reviews and the 25 planted cases.

There is no pass mark. The result is recorded as it falls, each case with its own outcome,
and is never used to change the wording. A second run is refused unless asked for by name.

  python3 evals/holdout_score.py --standin
  python3 evals/holdout_score.py --go --prompt-file enrich-v2.json      paid: 55 requests
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "evals")]
import common  # noqa: E402
import planted_cases  # noqa: E402


class AlreadyScored(Exception):
    """The holdout has been scored with this wording. Scoring it again is how a clean score stops being one."""


def items():
    planted = [{"id": f"planted:{c['id']}", "text": c["text"]} for c in planted_cases.cases()]
    return [{"id": r["id"], "text": r["text"]} for r in common.boycott("holdout")] + planted


def run(ask, *, out_path, again=False):
    out_path = Path(out_path)
    if out_path.exists() and not again:
        raise AlreadyScored(f"{out_path.name} exists")
    shared, disputed = common.shared_rater_labels(), common.disputed_by_raters()
    rows, matches = [], {f: 0 for f in (*common.FIELDS, "all_three")}
    held = common.boycott("holdout")
    for item in held:
        record = ask(item["id"], item["text"])
        got = {f: record.get(f) for f in common.FIELDS}
        row = {"id": item["id"], "got": got, "invalid": record.get("invalid"), "raters_dispute": item["id"] in disputed}
        if item["id"] in shared:
            row["matches"] = {f: got[f] == shared[item["id"]][f] for f in common.FIELDS}
            for f in common.FIELDS:
                matches[f] += row["matches"][f]
            matches["all_three"] += all(row["matches"].values())
        rows.append(row)
    planted = planted_cases.score(ask)
    result = {
        "holdout_rows": len(held),
        "with_shared_rater_answer": sum("matches" in r for r in rows),
        "matches_shared_rater_answer": matches,
        "disputed_by_the_raters": sum(r["raters_dispute"] for r in rows),
        "holdout": rows,
        "planted": planted,
        "note": "Scored once. Agreement with two other models is not accuracy.",
    }
    out_path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    common.add_arguments(ap)
    ap.add_argument("--again", action="store_true", help="score again although a result exists; say why in the validation log")
    a = ap.parse_args(argv)
    with common.session(a, "holdout score") as paid:
        if paid is None:
            return 2
        folder = ROOT / "evals" if a.go else Path(tempfile.mkdtemp(prefix="holdout-standin-"))  # a stand-in result never lands in evals/
        out = folder / f"holdout_score_{paid.setup.prompt['version']}.json"
        try:
            result = run(paid.ask, out_path=out, again=a.again)
        except AlreadyScored as e:
            print(f"refused: {e}. The holdout is scored once.")
            return 2
    m = result["matches_shared_rater_answer"]
    print(f"holdout: {result['holdout_rows']} rows, {result['with_shared_rater_answer']} with a shared rater answer; all three match on {m['all_three']}, intent on {m['intent']}")
    print(f"planted: {result['planted']['right']} of {result['planted']['of']}; by group {result['planted']['by_group']}")
    for r in result["planted"]["results"]:
        if r["group"] == "injection":
            print(f"  injection {r['id']}: {'right' if r['right'] else 'moved'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
