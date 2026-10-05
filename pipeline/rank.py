"""Stage 5: the contract's baseline ranking. Pure code: no model, no state file.

`from_files` rebuilds ranking.csv from the committed grading files alone, so anyone with a
clean clone can check the ranking.
"""

import csv
import gzip
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

COLUMNS = ("rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score")
RANKED_INTENTS = ("complaint", "cancellation")


class BadMembership(Exception):
    """A member that is not a completed complaint or cancellation. One bad record changes the ranking."""


def mean_string(total, n):
    """Mean severity to six decimals, rounded half-up, with no floating point."""
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def rank(records, membership):
    """Ranking rows in export form: every value a string. Score descending, then issue ID ascending."""
    by_id = {r["review_id"]: r for r in records}
    severities = {}
    for issue_id, review_id in membership:
        record = by_id.get(review_id)
        if record is None:
            raise BadMembership(f"{review_id} is a member of {issue_id} but has no record")
        if record.get("status") != "completed" or record.get("intent") not in RANKED_INTENTS:
            raise BadMembership(f"{review_id} is a member of {issue_id} but is not a completed complaint or cancellation")
        severities.setdefault(issue_id, []).append(record["severity"])
    ordered = sorted(severities.items(), key=lambda kv: (-sum(kv[1]), kv[0]))
    return [
        {
            "rank": str(n),
            "issue_id": issue_id,
            "complaint_count": str(len(values)),
            "severity_sum": str(sum(values)),
            "mean_severity": mean_string(sum(values), len(values)),
            "priority_score": str(sum(values)),
        }
        for n, (issue_id, values) in enumerate(ordered, 1)
    ]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_records(grading_dir):
    """Records from records.jsonl, or from its gzip when that is the form present."""
    plain = Path(grading_dir) / "records.jsonl"
    stream = plain.open(encoding="utf-8") if plain.exists() else gzip.open(str(plain) + ".gz", "rt", encoding="utf-8")
    with stream as f:
        return [json.loads(line) for line in f if line.strip()]


def from_files(grading_dir):
    """Rewrite ranking.csv from records and membership.csv in `grading_dir`."""
    grading_dir = Path(grading_dir)
    with open(grading_dir / "membership.csv", encoding="utf-8-sig", newline="") as f:
        membership = [(row["issue_id"], row["review_id"]) for row in csv.DictReader(f)]
    rows = rank(read_records(grading_dir), membership)
    write_csv(grading_dir / "ranking.csv", rows)
    return rows
