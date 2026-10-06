"""The wording trial: the probe's intent wording against a candidate, on the tuning cases only.

Cases: the 4 planted slogan cases and the 30 real boycott reviews marked `tune`. The 30
marked `holdout` are never read here; they are scored once, later, by holdout_score.py.

  python3 evals/wording_trial.py --standin
  python3 evals/wording_trial.py --go [--candidate enrich-v2.json]     paid: about 68 requests
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "evals")]
import common  # noqa: E402
from pipeline import jev  # noqa: E402
import planted_cases  # noqa: E402


class HoldoutTouched(Exception):
    """A held-back review reached the trial. Tuning on it would spend the only clean score."""


def tuning_items():
    slogans = [{"id": f"planted:{c['id']}", "text": c["text"]} for c in planted_cases.cases() if c["group"] == "slogan"]
    return slogans + [{"id": r["id"], "text": r["text"]} for r in common.boycott("tune")]


items = tuning_items  # the name the tests and the gate notes use


def run(asks, items=None):
    """Score each wording. `asks` maps a wording's name to its `ask(item_id, text)`."""
    todo = tuning_items() if items is None else items
    held = {r["id"] for r in common.boycott("holdout")}
    touched = [i["id"] for i in todo if i["id"] in held]
    if touched:
        raise HoldoutTouched(f"{len(touched)} held-back review(s) were given to the wording trial")
    slogans = {f"planted:{c['id']}": c for c in planted_cases.cases() if c["group"] == "slogan"}
    shared = common.shared_rater_labels()
    out = {}
    for name, ask in asks.items():
        right, matches, with_shared, per_item = {}, 0, 0, []
        for item in todo:
            record = ask(item["id"], item["text"])
            per_item.append({"id": item["id"], "intent": record.get("intent"), "invalid": record.get("invalid")})
            if item["id"] in slogans:
                right[item["id"].split(":")[1]] = planted_cases.is_right(slogans[item["id"]], record)
            elif item["id"] in shared:
                with_shared += 1
                matches += record.get("intent") == shared[item["id"]]["intent"]
        out[name] = {
            "slogans_right": sum(right.values()),
            "slogans": right,
            "tune_rows": sum(i["id"] not in slogans for i in todo),
            "tune_with_shared_rater_intent": with_shared,
            "tune_intent_matches": matches,
            "per_item": per_item,
        }
    return out


def marks(probe, candidate):
    """The pass marks the candidate missed. Empty means it may replace the probe wording."""
    missed = []
    for case, ok in sorted(candidate["slogans"].items()):
        if not ok:
            missed.append(f"planted slogan {case} does not match its accepted answer")
    for case, ok in sorted(probe["slogans"].items()):
        if ok and not candidate["slogans"].get(case):
            missed.append(f"planted slogan {case} was right with the probe wording and is wrong now")
    if candidate["tune_intent_matches"] < probe["tune_intent_matches"]:
        missed.append(
            f"on the tune half the candidate matches the raters' shared intent on {candidate['tune_intent_matches']} rows, "
            f"fewer than the probe wording's {probe['tune_intent_matches']}"
        )
    return list(dict.fromkeys(missed))


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    common.add_arguments(ap)
    ap.add_argument("--candidate", default="enrich-v2.json")
    a = ap.parse_args(argv)
    with common.session(a, "wording trial, probe", jev.PROBE_PROMPT_FILE) as probe:
        if probe is None:
            return 2
        first = run({"probe": probe.ask})
    with common.session(a, "wording trial, candidate", a.candidate) as candidate:
        second = run({"candidate": candidate.ask})
    result = {**first, **second, "candidate_file": a.candidate}
    result["marks_missed"] = marks(result["probe"], result["candidate"])
    if a.go:
        (ROOT / "evals/wording_trial_out.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    else:
        print("stand-in run: nothing saved")
    for name in ("probe", "candidate"):
        r = result[name]
        print(f"{name}: slogans {r['slogans_right']} of 4 {r['slogans']}; tune intent matches {r['tune_intent_matches']} of {r['tune_with_shared_rater_intent']} rows the raters agree on")
    print("pass marks missed: " + ("none" if not result["marks_missed"] else "; ".join(result["marks_missed"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
