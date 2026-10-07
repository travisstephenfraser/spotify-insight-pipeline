"""THROWAWAY scorer for the Jev probe. Not pipeline code.

--sanity : degeneracy checks on Jev's saved answers. Prints pass/fail only, no labels.
default  : checks the format of the human labels (row numbers and column names only),
           then scores both question styles against the labeled rows.
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "evals/dev_150_labeled.csv"
HERE = Path(__file__).parent
TOPICS = [
    "access",
    "usability",
    "playback",
    "downloads",
    "catalog",
    "billing",
    "support",
    "other",
]
INTENTS = ["cancellation", "complaint", "request", "praise", "unclear"]
SEV = {"no_problem": 1, "annoyance": 2, "degraded": 3, "blocked": 4, "serious_harm": 5}


def load(style):
    return [
        json.loads(line) for line in open(HERE / f"{style}.jsonl", encoding="utf-8")
    ]


def simple_records():
    out = {}
    for row in load("simple"):
        a = row["response"]["answers"]
        text = row["request"]["state"]
        ev = a.get("evidence")
        quote = (
            row["request"]["questions"]["evidence"]["criteria"][ev["choice"]]
            if ev
            else text.strip()
        )
        out[row["review_id"]] = {
            "topic": a["topic"]["choice"],
            "intent": a["intent"]["choice"],
            "severity": SEV[a["severity"]["choice"]],
            "sentiment": a["tone"]["score"] / 2 - 1,
            "quote": quote,
            "p_topic": max(a["topic"]["probabilities"].values()),
        }
    return out


def sentence_records():
    by_review = defaultdict(list)
    for row in load("sentence"):
        by_review[row["review_id"]].append(row)
    out = {}
    for rid, rows in by_review.items():
        rows.sort(key=lambda r: r["piece_index"])
        sents = []
        for r in rows:
            a = r["response"]["answers"]
            kind = a["kind"]["choice"]
            sev = SEV[a["impact"]["choice"]] if kind in ("problem", "leaving") else 1
            if kind == "problem":
                sev = max(
                    sev, 2
                )  # a stated problem is at least an annoyance under the contract
            sents.append(
                {
                    "piece": r["request"]["state"]["sentence"],
                    "about": a["about"]["choice"],
                    "kind": kind,
                    "sev": sev,
                    "p_about": max(a["about"]["probabilities"].values()),
                }
            )
        kinds = {s["kind"] for s in sents}
        intent = (
            "cancellation"
            if "leaving" in kinds
            else "complaint"
            if "problem" in kinds
            else "request"
            if "request" in kinds
            else "praise"
            if "praise" in kinds
            else "unclear"
        )
        problems = [s for s in sents if s["kind"] in ("problem", "leaving")]
        if problems:
            top = max(problems, key=lambda s: s["sev"])  # max() keeps the first on ties
            specific = [
                s for s in problems if s["sev"] == top["sev"] and s["about"] != "other"
            ]
            chosen = specific[0] if specific else top
        else:
            praise = [
                s for s in sents if s["kind"] == "praise" and s["about"] != "other"
            ]
            chosen = praise[0] if praise else sents[0]
        tone = rows[0]["response"]["answers"]["tone"]["score"]
        out[rid] = {
            "topic": chosen["about"],
            "intent": intent,
            "severity": max(s["sev"] for s in sents) if problems else 1,
            "sentiment": tone / 2 - 1,
            "quote": chosen["piece"],
            "p_topic": chosen["p_about"],
        }
    return out


def sanity():
    ok = True
    for name, recs in (("simple", simple_records()), ("sentence", sentence_records())):
        topics, intents, sevs = (
            Counter(r[k] for r in recs.values())
            for k in ("topic", "intent", "severity")
        )
        checks = {
            "100 reviews have a record": len(recs) == 100,
            "no topic above 90%": max(topics.values()) <= 90,
            "at least 4 topics used": len(topics) >= 4,
            "no intent above 90%": max(intents.values()) <= 90,
            "at least 3 intents used": len(intents) >= 3,
            "at least 3 severity levels used": len(sevs) >= 3,
            "every label in the allowed lists": all(
                r["topic"] in TOPICS and r["intent"] in INTENTS for r in recs.values()
            ),
            "every quote is an exact copy": True,
        }
        texts = {
            row["review_id"]: (
                row["request"]["state"]
                if isinstance(row["request"]["state"], str)
                else row["request"]["state"]["review"]
            )
            for row in load(name)
        }
        checks["every quote is an exact copy"] = all(
            r["quote"] and r["quote"] in texts[rid] for rid, r in recs.items()
        )
        for label, passed in checks.items():
            ok &= passed
            print(f"{name:<9} {'PASS' if passed else 'FAIL'}  {label}")
    print("SANITY:", "all checks passed" if ok else "at least one check FAILED")


def human_rows(limit):
    rows = list(csv.DictReader(open(LABELS, encoding="utf-8-sig", newline="")))[:limit]
    good, problems = [], []
    for n, r in enumerate(rows, 2):  # spreadsheet row number, header is row 1
        if not any(
            (r.get(c) or "").strip()
            for c in (
                "intent",
                "topic",
                "severity",
                "sentiment",
                "evidence_quote",
                "needs_review",
            )
        ):
            continue  # not labeled yet
        bad = []
        if (r["intent"] or "").strip().lower() not in INTENTS:
            bad.append("intent")
        if (r["topic"] or "").strip().lower() not in TOPICS:
            bad.append("topic")
        if (r["severity"] or "").strip() not in {"1", "2", "3", "4", "5"}:
            bad.append("severity")
        try:
            float(r["sentiment"])
            assert -1 <= float(r["sentiment"]) <= 1
        except Exception:
            bad.append("sentiment")
        q = r["evidence_quote"] or ""
        if not q.strip() or q.strip() not in r["review_text"]:
            bad.append("evidence_quote")
        if (r["needs_review"] or "").strip().upper() not in {"TRUE", "FALSE"}:
            bad.append("needs_review")
        (problems if bad else good).append((n, r, bad))
    return good, problems


def score(limit=30):
    good, problems = human_rows(limit)
    print(
        f"labeled rows found in the first {limit}: {len(good) + len(problems)}  usable: {len(good)}"
    )
    for n, _, bad in problems:
        print(f"  row {n}: fix {', '.join(bad)}")
    if not good:
        return
    for name, recs in (("simple", simple_records()), ("sentence", sentence_records())):
        hits = Counter()
        sev_err = sen_err = 0.0
        misses = []
        for n, r, _ in good:
            j = recs[r["review_id"]]
            alt = (r.get("notes") or "").lower()
            t_ok = (
                j["topic"] == r["topic"].strip().lower()
                or f"alt topic: {j['topic']}" in alt
            )
            i_ok = (
                j["intent"] == r["intent"].strip().lower()
                or f"alt intent: {j['intent']}" in alt
            )
            s_ok = j["severity"] == int(r["severity"])
            hq = r["evidence_quote"].strip()
            q_ok = hq in j["quote"] or j["quote"] in hq
            hits.update(topic=t_ok, intent=i_ok, severity=s_ok, quote_overlap=q_ok)
            sev_err += abs(j["severity"] - int(r["severity"]))
            sen_err += abs(j["sentiment"] - float(r["sentiment"]))
            if not (t_ok and i_ok and s_ok):
                misses.append((n, r, j))
        k = len(good)
        print(f"\n=== {name} ===  n={k}")
        print(
            f"topic {hits['topic']}/{k}  intent {hits['intent']}/{k}  severity exact {hits['severity']}/{k}  "
            f"severity mean error {sev_err / k:.2f}  sentiment mean error {sen_err / k:.2f}  quote overlaps yours {hits['quote_overlap']}/{k}"
        )
        for n, r, j in misses:
            text = re.sub(r"\s+", " ", r["review_text"])[:110]
            print(
                f"  row {n}: you {r['topic']}/{r['intent']}/{r['severity']}  jev {j['topic']}/{j['intent']}/{j['severity']}  | {text}"
            )


if __name__ == "__main__":
    sanity() if "--sanity" in sys.argv else score(
        int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
    )
