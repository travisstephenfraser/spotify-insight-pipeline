"""Read the 100-review pilot (run pilot-cold) for the gate: no model call, nothing written but this script's output.

Compares the frozen wording's labels with the probe wording's saved answers on the same 100
reviews, and both engines with the development labels and the outside raters' shared answer.
Development labels and rater labels are tuning material, not the golden set.

    python3 experiments/2026-10-05/pilot-100/gate_read.py
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "evals")]
import common  # noqa: E402

from pipeline import jev  # noqa: E402

RUN = ROOT / "runs/pilot-cold"
FIELDS = ("topic", "intent", "severity")


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def same(a, b, fields=FIELDS):
    return all(str(a[f]) == str(b[f]) for f in fields)


def score(pred, ref, ids):
    ids = [i for i in ids if i in pred and i in ref]
    out = {f: sum(str(pred[i][f]) == str(ref[i][f]) for i in ids) for f in FIELDS}
    out["all_three"] = sum(same(pred[i], ref[i]) for i in ids)
    out["n"] = len(ids)
    return out


def main():
    records = {r["review_id"]: r for r in jsonl(RUN / "grading/records.jsonl")}
    gemma = {r["review_id"]: r for r in jsonl(RUN / "verify_predictions.jsonl")}
    probe_setup = jev.load_setup(ROOT / "prompts", 0.7, prompt_name=jev.PROBE_PROMPT_FILE)
    probe = {}
    for row in jsonl(ROOT / "experiments/2026-10-04/tool-choice/simple.jsonl"):
        probe[row["review_id"]] = jev.to_record(
            row["request"]["state"], row["response"]["answers"], features=probe_setup.features, cutoff=0.7, label_config=probe_setup.label_config
        )
    ids = sorted(records)
    print(f"reviews: {len(ids)} in the run, {len(probe)} with a saved probe answer, {len(gemma)} verifier predictions")

    print("\n1. The frozen wording (v2) against the probe wording (v1), same 100 reviews, same model")
    changed = {f: [i for i in ids if str(records[i][f]) != str(probe[i][f])] for f in FIELDS}
    print("   changed:", {f: len(v) for f, v in changed.items()}, "| any of the three:", len({i for v in changed.values() for i in v}))
    print("   intent moves (v1 -> v2):", dict(Counter(f"{probe[i]['intent']} -> {records[i]['intent']}" for i in changed["intent"])))
    print("   topic moves:", dict(Counter(f"{probe[i]['topic']} -> {records[i]['topic']}" for i in changed["topic"])))
    print("   severity moves:", dict(Counter(f"{probe[i]['severity']} -> {records[i]['severity']}" for i in changed["severity"])))
    for name, recs in (("v1", probe), ("v2", records)):
        members = [i for i in ids if recs[i]["intent"] in ("complaint", "cancellation")]
        sums = Counter()
        for i in members:
            sums[recs[i]["topic"]] += int(recs[i]["severity"])
        print(f"   {name}: {len(members)} complaints or cancellations; severity sums {dict(sums.most_common())}; needs_review {sum(bool(recs[i]['needs_review']) for i in ids)}")

    dev = common.dev_labels()
    originals = {k: dict(v) for k, v in dev.items()}
    sheet = {r["review_id"]: r for r in csv.DictReader(open(ROOT / "evals/dev_150_labeled.csv", encoding="utf-8-sig", newline=""))}
    revised = 0
    for rid in originals:
        m = re.search(r"revised .*?: (topic|intent|severity) was (\S+)", sheet[rid].get("notes", ""))
        if m:
            originals[rid][m.group(1)] = int(m.group(2)) if m.group(1) == "severity" else m.group(2)
            revised += 1
    by_rule = {k: {**v, "severity": 1 if v["intent"] in ("unclear", "praise", "request") else v["severity"]} for k, v in dev.items()}
    print(f"\n2. Against the {len(dev)} development labels ({revised} revised after seeing a model; the severity rule changes {sum(by_rule[k] != dev[k] for k in dev)})")
    for name, pred in (("Jev v1", probe), ("Jev v2", records), ("Gemma, one review a request", gemma)):
        a, b = score(pred, dev, dev), score(pred, originals, dev)
        print(f"   {name}: all three {a['all_three']} of {a['n']} as the labels stand ({b['all_three']} as first written); topic {a['topic']}, intent {a['intent']}, severity {a['severity']}")

    shared = common.shared_rater_labels()
    both = [i for i in ids if i in shared]
    print(f"\n3. Against the answer the two outside raters share ({len(both)} of the 100): agreement with other models, not accuracy")
    for name, pred in (("Jev v1", probe), ("Jev v2", records), ("Gemma, one review a request", gemma)):
        a = score(pred, shared, both)
        print(f"   {name}: all three {a['all_three']} of {a['n']}; topic {a['topic']}, intent {a['intent']}, severity {a['severity']}")

    report = json.loads((RUN / "verify_report.json").read_text())
    print("\n4. Jev v2 against Gemma (the run's own verify report)")
    print("   all pairs:", report["agreement"])
    for group, row in report["by_group"].items():
        print(f"   {group}:", row)
    disagree = [i for i in ids if not same(records[i], gemma[i])]
    flagged = {i for i in ids if records[i]["needs_review"]}
    print(f"   disagreements {len(disagree)}; of those flagged needs_review at 0.70: {len(flagged & set(disagree))}; flagged in all: {len(flagged)}")

    print("\n5. Quotes and entities")
    print("   records with entities:", sum(bool(records[i]["entities"]) for i in ids), "| most common:", Counter(e for i in ids for e in records[i]["entities"]).most_common(8))


if __name__ == "__main__":
    main()
