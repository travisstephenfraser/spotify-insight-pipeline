"""THROWAWAY three-way comparison on the labeled development rows. Not pipeline code."""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from score_spike import INTENTS, LABELS, TOPICS, sentence_records, simple_records

HERE = Path(__file__).parent


def gemma_records():
    out = {}
    for line in open(HERE / "gemma.jsonl", encoding="utf-8"):
        r = json.loads(line)
        out[r["review_id"]] = {
            "topic": r["topic"],
            "intent": r["intent"],
            "severity": r["severity"],
            "sentiment": r["sentiment"],
            "quote": r["evidence_quote"],
        }
    return out


def main(limit):
    rows = list(csv.DictReader(open(LABELS, encoding="utf-8-sig", newline="")))[:limit]
    rows = [(n, r) for n, r in enumerate(rows, 2) if r["intent"].strip()]
    for n, r in rows:
        assert (
            r["intent"] in INTENTS
            and r["topic"] in TOPICS
            and r["severity"] in list("12345")
        ), f"row {n} has an invalid label"
    engines = {
        "jev simple": simple_records(),
        "jev sentence": sentence_records(),
        "gemma": gemma_records(),
    }
    k = len(rows)
    hard = [(n, r) for n, r in rows if r["intent"] in ("complaint", "cancellation")]
    print(f"labeled reviews: {k}  (complaints and cancellations: {len(hard)})")
    print(
        f"{'engine':<13} {'topic':>7} {'intent':>7} {'sev':>7} {'all 3':>7} {'sev err':>8} {'sent err':>9} | complaints: {'topic':>6} {'intent':>7} {'sev':>6}"
    )
    misses = {}
    for name, recs in engines.items():
        h = Counter()
        hh = Counter()
        se = st = 0.0
        misses[name] = []
        for n, r in rows:
            j = recs[r["review_id"]]
            alt = (r.get("notes") or "").lower()
            t = j["topic"] == r["topic"] or f"alt topic: {j['topic']}" in alt
            i = j["intent"] == r["intent"] or f"alt intent: {j['intent']}" in alt
            s = j["severity"] == int(r["severity"])
            h.update(t=t, i=i, s=s, a=t and i and s)
            if (n, r) in hard:
                hh.update(t=t, i=i, s=s)
            se += abs(j["severity"] - int(r["severity"]))
            st += abs(j["sentiment"] - float(r["sentiment"]))
            if not (t and i and s):
                misses[name].append((n, r, j))
        print(
            f"{name:<13} {h['t']:>4}/{k} {h['i']:>4}/{k} {h['s']:>4}/{k} {h['a']:>4}/{k} {se / k:>8.2f} {st / k:>9.2f} |             {hh['t']:>3}/{len(hard)} {hh['i']:>4}/{len(hard)} {hh['s']:>3}/{len(hard)}"
        )
    for name in ("gemma", "jev simple"):
        print(f"\n{name} misses:")
        for n, r, j in misses[name]:
            print(
                f"  row {n}: you {r['topic']}/{r['intent']}/{r['severity']}  {name.split()[0]} {j['topic']}/{j['intent']}/{j['severity']}  | {re.sub(chr(10), ' ', r['review_text'])[:95]}"
            )
    # Does disagreement between the two engines point at errors?
    a, b = engines["jev simple"], engines["gemma"]
    ids = list(a)
    same = [
        rid
        for rid in ids
        if (a[rid]["topic"], a[rid]["intent"], a[rid]["severity"])
        == (b[rid]["topic"], b[rid]["intent"], b[rid]["severity"])
    ]
    print(
        f"\njev simple vs gemma on all 100: identical topic+intent+severity on {len(same)}; "
        f"topic agrees {sum(a[r]['topic'] == b[r]['topic'] for r in ids)}, intent agrees {sum(a[r]['intent'] == b[r]['intent'] for r in ids)}, severity agrees {sum(a[r]['severity'] == b[r]['severity'] for r in ids)}"
    )
    lab = {r["review_id"]: r for _, r in rows}

    def right(rec, r):
        return (
            rec["topic"] == r["topic"]
            and rec["intent"] == r["intent"]
            and rec["severity"] == int(r["severity"])
        )

    agree = [rid for rid in lab if rid in same]
    differ = [rid for rid in lab if rid not in same]
    print(
        f"on the {k} labeled: engines agree on {len(agree)}, and that shared answer matches yours on {sum(right(a[r], lab[r]) for r in agree)}; "
        f"engines differ on {len(differ)}: jev matches you on {sum(right(a[r], lab[r]) for r in differ)}, gemma on {sum(right(b[r], lab[r]) for r in differ)}, neither on {sum(not right(a[r], lab[r]) and not right(b[r], lab[r]) for r in differ)}"
    )
    print(
        "label spread on all 100 (topic):",
        {
            n: dict(Counter(v["topic"] for v in e.values()).most_common())
            for n, e in engines.items()
            if n != "jev sentence"
        },
    )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
