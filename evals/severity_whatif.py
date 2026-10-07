"""The exported ranking, recounted with the severity scale read other ways. No label is changed.

An outside review on 2026-10-07 read 20 complaints the classifier rated 4 or 5 and would have rated 11 of them lower,
ten of those a 3 (validation log entry 39). This asks what that direction of error would do to the order of the issues.
It reads the saved grading files only: no model, no key, no state file. It first rebuilds ranking.csv from the records
and the membership and refuses if the two differ, so every other row is a recount of the same run.

  python3 evals/severity_whatif.py [--grading grading] [--out evals/severity_whatif.json] [--places 4]
"""

import argparse
import collections
import csv
import gzip
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from pipeline import rank  # noqa: E402

SCALE = (1, 2, 3, 4, 5)
READINGS = (
    ("as_labeled", "The labels as exported: the sum of severities", lambda s: s),
    ("four_as_three", "Every 4 counted as 3", lambda s: 3 if s == 4 else s),
    ("high_as_three", "Every 4 and 5 counted as 3", lambda s: min(s, 3)),
    ("count_only", "Every complaint counted once", lambda s: 1),
    (
        "blocked_only",
        "Only complaints rated 4 or 5, each counted once",
        lambda s: 1 if s >= 4 else 0,
    ),
)
OK, REFUSED = 0, 2


class Mismatch(Exception):
    """The records and the membership do not give the exported ranking. A what-if on them would be about another run."""


class Degenerate(Exception):
    """A reading gives every issue the same total. That is a count reading nothing, never a finding."""


def _severities(grading):
    """The severity of every completed complaint or cancellation, by review ID."""
    plain = grading / "records.jsonl"
    stream = (
        plain.open(encoding="utf-8")
        if plain.exists()
        else gzip.open(str(plain) + ".gz", "rt", encoding="utf-8")
    )
    out = {}
    with stream as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if (
                r.get("status") == "completed"
                and r.get("intent") in rank.RANKED_INTENTS
            ):
                out[r["review_id"]] = r["severity"]
    return out


def _counts(grading):
    """For each issue, how many of its members carry each severity."""
    severities = _severities(grading)
    counts = collections.defaultdict(collections.Counter)
    with open(grading / "membership.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["review_id"] not in severities:
                raise Mismatch(
                    f"{row['review_id']} is a member of {row['issue_id']} but is not a completed complaint or cancellation"
                )
            counts[row["issue_id"]][severities[row["review_id"]]] += 1
    return counts


def _ordered(counts, weight):
    """(issue, total) with the ranking's own order: total descending, then issue ID."""
    totals = {
        issue: sum(weight(s) * n for s, n in c.items()) for issue, c in counts.items()
    }
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))


def _check_against_export(grading, counts):
    """The known answer. Raises unless these counts rebuild ranking.csv, every column of every row."""
    rebuilt = [
        {
            "rank": str(n),
            "issue_id": issue,
            "complaint_count": str(sum(counts[issue].values())),
            "severity_sum": str(total),
            "mean_severity": rank.mean_string(total, sum(counts[issue].values())),
            "priority_score": str(total),
        }
        for n, (issue, total) in enumerate(_ordered(counts, lambda s: s), 1)
    ]
    with open(grading / "ranking.csv", encoding="utf-8-sig", newline="") as f:
        exported = [{k: row[k] for k in rank.COLUMNS} for row in csv.DictReader(f)]
    if rebuilt != exported:
        wrong = next((a for a, b in zip(rebuilt, exported) if a != b), None)
        raise Mismatch(
            f"the records and membership do not give {grading / 'ranking.csv'}: rebuilt {wrong}"
            if wrong
            else "the ranking has a different number of rows"
        )


def _break_even(counts):
    """Pairs that change places once some share of every issue's 4s is counted as 3, and that share."""
    order = _ordered(counts, lambda s: s)
    out = []
    for at, (ahead, lead_total) in enumerate(order):
        for behind, total in order[at + 1 :]:
            more_fours = counts[ahead][4] - counts[behind][4]
            if more_fours > 0 and 0 < Fraction(lead_total - total, more_fours) <= 1:
                share = Decimal(lead_total - total) / Decimal(more_fours)
                out.append(
                    {
                        "ahead": ahead,
                        "behind": behind,
                        "share_of_fours": str(
                            share.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                        ),
                    }
                )
    return out


def whatif(grading):
    """Every reading of the saved labels, as plain values that save to JSON unchanged."""
    grading = Path(grading)
    counts = _counts(grading)
    _check_against_export(grading, counts)
    readings = {}
    for name, title, weight in READINGS:
        ordered = _ordered(counts, weight)
        if len(ordered) > 1 and len({total for _, total in ordered}) == 1:
            raise Degenerate(f"the reading '{name}' gives every issue {ordered[0][1]}")
        readings[name] = {
            "title": title,
            "order": [issue for issue, _ in ordered],
            "totals": dict(ordered),
        }
    return {
        "what": "The exported ranking recounted with the severity scale read other ways. No label is changed.",
        "members": sum(sum(c.values()) for c in counts.values()),
        "severity_counts": {
            issue: {str(s): counts[issue][s] for s in SCALE} for issue in sorted(counts)
        },
        "readings": readings,
        "first": {name: reading["order"][0] for name, reading in readings.items()},
        "break_even": _break_even(counts),
    }


def _place(n):
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n, 'th') }"


def table(result, places=None):
    """One row a reading: the first `places` issues in that reading's order, each with its total."""
    width = min(places or 10**6, len(result["readings"]["as_labeled"]["order"]))
    lines = [
        "| Reading | " + " | ".join(_place(n) for n in range(1, width + 1)) + " |",
        "|---" * (width + 1) + "|",
    ]
    for reading in result["readings"].values():
        cells = [
            f"{issue} {reading['totals'][issue]:,}"
            for issue in reading["order"][:width]
        ]
        lines.append(f"| {reading['title']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("--grading", default=str(ROOT / "grading"))
    p.add_argument("--out", default=str(ROOT / "evals/severity_whatif.json"))
    p.add_argument(
        "--places",
        type=int,
        default=4,
        help="how many issues of each reading to print (default 4)",
    )
    a = p.parse_args(argv)
    try:
        result = whatif(a.grading)
    except (Mismatch, Degenerate) as e:
        print(f"refused: {e}")
        return REFUSED
    Path(a.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(table(result, a.places))
    print()
    for pair in result["break_even"]:
        print(
            f"{pair['ahead']} and {pair['behind']} change places once {Decimal(pair['share_of_fours']):.0%} of the 4s are counted as 3."
        )
    if not result["break_even"]:
        print("No two issues change places however many 4s are counted as 3.")
    print(
        f"{result['members']:,} complaints and cancellations recounted; saved: {a.out}"
    )
    return OK


if __name__ == "__main__":
    sys.exit(main())
