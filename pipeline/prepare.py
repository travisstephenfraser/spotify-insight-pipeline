"""Stage 1: read the input CSV into the state file. Code only, no model.

Every row is kept exactly as read. Empty text is quarantined, identical texts share one
original, and the run order and the verify sample are fixed here, before any model call.
"""

import csv
from pathlib import Path

from pipeline import hashing

# The supplied full file. When the input is this file its counts must match, or prepare raises.
SUPPLIED = {
    "sha256": "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6",
    "rows": 660622,
    "empty": 13,
    "distinct_texts": 484189,
    "missing_app_version": 159701,
}


class BadInput(Exception):
    """The CSV cannot be used as it stands. The message says what to fix."""


class GuardFailed(Exception):
    """The supplied file did not give its known counts: the reading is wrong, not the file."""


def read_rows(path):
    """The six source fields of every row, as exact strings. Extra columns are ignored."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        names = reader.fieldnames or []
        if len(set(names)) != len(names):
            raise BadInput("the CSV has a repeated column name")
        missing = [k for k in hashing.FIELDS if k not in names]
        if missing:
            raise BadInput("the CSV is missing the column " + ", ".join(missing))
        rows, seen = [], set()
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise BadInput(
                    f"line {reader.line_num} does not have one value per column"
                )
            if row["review_id"] in seen:
                raise BadInput(
                    f"the review_id {row['review_id']} appears more than once"
                )
            seen.add(row["review_id"])
            rows.append({k: row[k] for k in hashing.FIELDS})
    if not rows:
        raise BadInput("the CSV has no rows")
    return rows


def prepare(db, run, input_path, *, seed, verify_seed, verify_size=5000):
    """Fill `reviews` for this run and return the counts. The caller owns the transaction."""
    rows = read_rows(input_path)
    rows.sort(key=lambda r: hashing.order_key(seed, r["review_id"]))

    originals = {}  # text key -> review_id of the first review in run order with that text
    records = []
    for order, row in enumerate(rows):
        text = row["review_text"]
        key = hashing.text_key(text)
        if not text.strip():
            status, reason, source = "quarantined", "empty_review_text", None
        else:
            status, reason = "pending", None
            source = originals.get(key)
            if source is None:
                originals[key] = row["review_id"]
        records.append((row, key, order, status, reason, source))

    nonempty = [
        row["review_id"] for row, _, _, status, _, _ in records if status == "pending"
    ]
    sample = set(
        sorted(nonempty, key=lambda i: hashing.order_key(verify_seed, i))[:verify_size]
    )

    db.executemany(
        "INSERT INTO reviews (run, review_id, review_text, review_rating, review_likes, app_version, "
        "review_timestamp, source_sha256, text_key, run_order, status, reason, cache_source_id, in_verify_sample) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            (run, *(row[k] for k in hashing.FIELDS), hashing.row_sha(row), key, order, status, reason, source,
             int(row["review_id"] in sample))
            for row, key, order, status, reason, source in records
        ),
    )  # fmt: skip

    counts = {
        "rows": len(rows),
        "empty": len(rows) - len(nonempty),
        "distinct_texts": len(originals),
        "copies": len(nonempty) - len(originals),
        "missing_app_version": sum(not row["app_version"].strip() for row in rows),
        "verify_sample": len(sample),
        "supplied_file": hashing.file_sha(input_path) == SUPPLIED["sha256"],
    }
    if counts["supplied_file"]:
        wrong = [
            f"{k}: read {counts[k]}, known {v}"
            for k, v in SUPPLIED.items()
            if k != "sha256" and counts[k] != v
        ]
        if wrong:
            raise GuardFailed("the supplied file was read wrongly. " + "; ".join(wrong))
    return counts
