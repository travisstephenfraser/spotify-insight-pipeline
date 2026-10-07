"""One review followed through a run's saved files, from its source ID to the memo's claims.

The source row, the record, every request that listed the review, the verifier's blind answer, the issue it
joined, that issue's ranking row and the claims the memo makes about it. It reads saved files only: no model,
no key, no state file. The source row is read and hashed again only when the CSV is there.

  python3 evals/trace_review.py REVIEW_ID [--grading grading] [--evidence runs/full] [--source PATH.csv]
"""

import argparse
import csv
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from pipeline import hashing  # noqa: E402

LABELS = ("topic", "intent", "severity")
CLAIM = re.compile(r"\[(CL-\d{3})\]")
SOURCE = (
    ROOT
    / "feed/Final Assignment - Spotify Reviews Dataset/spotify_reviews_18months.csv"
)
OK, REFUSED = 0, 2


class NoSuchReview(Exception):
    """The grading folder holds no record for this ID."""


def _saved(folder, name):
    """A saved file, plain or gzipped, whichever the export wrote. None when neither is there."""
    for path in (Path(folder) / name, Path(folder) / (name + ".gz")):
        if path.exists():
            return path
    return None


def _lines_naming(path, review_id):
    """Each JSON line that names the ID. The byte test comes first, so a 660,000-line file is not parsed whole."""
    if path is None:
        return
    needle = json.dumps(review_id).encode("utf-8")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as f:
        for raw in f:
            if needle in raw:
                yield json.loads(raw)


def _csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def _source_row(path, review_id):
    """The review's row, read the way prepare reads it: exact strings, nothing trimmed."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, strict=True):
            if row["review_id"] == review_id:
                return {k: row[k] for k in hashing.FIELDS}
    return None


def trace(review_id, *, grading, evidence=None, source=None):
    """Everything the saved files hold about one review. Each part is read from its own file."""
    grading = Path(grading)
    record = next(
        (
            r
            for r in _lines_naming(_saved(grading, "records.jsonl"), review_id)
            if r["review_id"] == review_id
        ),
        None,
    )
    if record is None:
        raise NoSuchReview(review_id)
    out = {
        "review_id": review_id,
        "record": record,
        "source": None,
        "quarantine": None,
        "memo": None,
    }

    if source is not None:
        row = _source_row(source, review_id)
        out["source"] = {
            "row": row,
            "hash_matches": row is not None
            and hashing.row_sha(row) == record["source_sha256"],
            "quote_in_text": row is not None
            and bool(record.get("evidence_quote"))
            and record["evidence_quote"] in row["review_text"],
        }

    # A copy was never sent: the request that labeled it is its original's.
    out["labeled_by"] = record.get("cache_source_id", review_id)
    calls = [
        c for c in _lines_naming(_saved(grading, "calls.jsonl"), out["labeled_by"])
        if c["role"] == "enrich" and out["labeled_by"] in c["review_ids"]
    ]  # fmt: skip
    if evidence is not None and calls:
        # The run log holds what the grading export has no column for: the error, the time taken, the session.
        logged = {
            c["request_id"]: c
            for c in _lines_naming(_saved(evidence, "run_log.jsonl"), out["labeled_by"])
        }
        for call in calls:
            extra = logged.get(call["request_id"], {})
            call.update(
                {
                    k: extra.get(k)
                    for k in (
                        "error",
                        "http_status",
                        "seconds",
                        "session_id",
                        "started_utc",
                    )
                }
            )
    out["calls"] = calls

    out["verify"] = None
    if evidence is not None:
        theirs = next(
            (
                v
                for v in _lines_naming(
                    _saved(evidence, "verify_predictions.jsonl"), review_id
                )
                if v["review_id"] == review_id
            ),
            None,
        )
        if theirs is not None:
            predicted = (
                theirs["outcome"] == "predicted" and record["status"] == "completed"
            )
            out["verify"] = {
                **theirs,
                "same": {f: record[f] == theirs[f] for f in LABELS}
                if predicted
                else None,
            }
        if record["status"] == "quarantined":
            row = next(
                (
                    q
                    for q in _lines_naming(
                        _saved(evidence, "quarantine.jsonl"), review_id
                    )
                    if q["review_id"] == review_id
                ),
                {},
            )
            out["quarantine"] = {
                "reason": record.get("reason"),
                "attempts": row.get("attempts"),
            }
    if record["status"] == "quarantined" and out["quarantine"] is None:
        out["quarantine"] = {"reason": record.get("reason"), "attempts": None}

    issues = [
        m["issue_id"]
        for m in _csv_rows(grading / "membership.csv")
        if m["review_id"] == review_id
    ]
    if len(issues) > 1:
        raise ValueError(
            f"{review_id} is a member of {len(issues)} issues; this trace follows one"
        )
    out["issue_id"] = issues[0] if issues else None
    out["ranking"] = next(
        (
            r
            for r in _csv_rows(grading / "ranking.csv")
            if r["issue_id"] == out["issue_id"]
        ),
        None,
    )
    out["claims"] = (
        [
            c
            for c in _csv_rows(grading / "claims.csv")
            if c["issue_id"] == out["issue_id"]
        ]
        if issues
        else []
    )

    memo = Path(evidence) / "memo.md" if evidence is not None else None
    if memo is not None and memo.exists():
        text = memo.read_text(encoding="utf-8")
        cited = set(CLAIM.findall(text))
        out["memo"] = {
            "cites_review": f"[review:{review_id}]" in text,
            "cites_claims": [
                c["claim_id"] for c in out["claims"] if c["claim_id"] in cited
            ],
        }
    return out


def _yes(flag):
    return "yes" if flag else "no"


def render(t):
    """The trace as six short blocks, one a stage, in the order the review moved through them."""
    record, lines = t["record"], [f"review {t['review_id']}", ""]
    add = lines.append

    add(f"1 source   row hash {record['source_sha256']}")
    if t["source"] is None:
        add(
            "           the source file was not read, so the text is not shown and the hash stands as recorded"
        )
    elif t["source"]["row"] is None:
        add("           NOT FOUND in the source file given")
    else:
        row = t["source"]["row"]
        add(
            f"           hashed again from the file: {'the same' if t['source']['hash_matches'] else 'DIFFERENT'}"
        )
        add(f"           text: {json.dumps(row['review_text'], ensure_ascii=False)}")
        add(
            f"           stars {row['review_rating']}, likes {row['review_likes']}, app {row['app_version'] or 'missing'}, {row['review_timestamp']}"
        )

    if record["status"] == "quarantined":
        q = t["quarantine"]
        attempts = "" if q["attempts"] is None else f", attempts {q['attempts']}"
        add(f"2 enrich   never labeled: quarantined, reason {q['reason']}{attempts}")
    else:
        add(
            f"2 enrich   {record['topic']} / {record['intent']} / severity {record['severity']}, sentiment {record['sentiment']:+.3f}, needs_review {_yes(record['needs_review'])}"
        )
        add(f"           entities {json.dumps(record['entities'], ensure_ascii=False)}")
        add(
            f"           quote: {json.dumps(record['evidence_quote'], ensure_ascii=False)}"
        )
        if t["source"] is not None and t["source"]["row"] is not None:
            add(
                f"           the quote is an exact piece of the text: {_yes(t['source']['quote_in_text'])}"
            )
        add(f"           label_config {record['label_config']}")
        if t["labeled_by"] != t["review_id"]:
            add(
                f"           a copy: never sent. Its label is the one given to {t['labeled_by']}, whose requests these are"
            )
    for call in t["calls"]:
        usage = (
            f"{call['input_tokens']} in, {call['output_tokens']} out"
            if call["usage_known"]
            else "usage unknown"
        )
        took = (
            ""
            if call.get("seconds") is None
            else f", {call['seconds']:.2f} s, session {call['session_id']}"
        )
        add(
            f"           request {call['request_id']}: {call['outcome']}, phase {call['phase']}, {call['model']}, {usage}{took}"
        )
        if call.get("error"):
            add(f"             error: {call['error'].strip()}")

    v = t["verify"]
    if v is None:
        add("3 verify   not in the verify sample")
    elif v["same"] is None:
        add(
            f"3 verify   in the sample, outcome {v['outcome']}: {v.get('reason') or 'no answer to compare'}"
        )
    else:
        add(
            f"3 verify   {v['topic']} / {v['intent']} / severity {v['severity']} (blind, request {v['request_id']})"
        )
        add(
            "           same as the record: "
            + ", ".join(f"{f} {_yes(v['same'][f])}" for f in LABELS)
        )
        if not all(v["same"].values()):
            add("           a disagreement is reported and changes no label")

    if t["issue_id"] is None:
        add(
            "4 group    in no issue: only a completed complaint or cancellation joins one"
        )
        add("5 rank     adds nothing to any issue")
        add("6 memo     no claim rests on it")
        return "\n".join(lines)
    add(f"4 group    {t['issue_id']}")
    r = t["ranking"]
    add(
        f"5 rank     {r['issue_id']} is rank {r['rank']}: {r['complaint_count']} complaints, severity sum {r['severity_sum']}, mean {r['mean_severity']}, score {r['priority_score']}"
    )
    add(
        f"           this review adds 1 to the count and {record['severity']} to the severity sum"
    )
    add(
        "6 memo     claims about this issue: "
        + (
            ", ".join(
                f"{c['claim_id']} {c['metric']} {c['value']}" for c in t["claims"]
            )
            or "none"
        )
    )
    if t["memo"] is not None:
        add(
            f"           cited in the memo: {', '.join(t['memo']['cites_claims']) or 'none'}"
        )
        add(
            f"           the memo quotes this review: {_yes(t['memo']['cites_review'])}"
        )
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("review_id")
    p.add_argument("--grading", default=str(ROOT / "grading"))
    p.add_argument(
        "--evidence",
        default=str(ROOT / "runs/full"),
        help="the run's evidence folder (default runs/full)",
    )
    p.add_argument(
        "--source",
        help="the input CSV; default is the supplied full file when it is there",
    )
    a = p.parse_args(argv)
    source = a.source or (str(SOURCE) if SOURCE.exists() else None)
    try:
        print(
            render(
                trace(
                    a.review_id, grading=a.grading, evidence=a.evidence, source=source
                )
            )
        )
    except NoSuchReview:
        print(f"refused: {a.grading} holds no record for {a.review_id}")
        return REFUSED
    return OK


if __name__ == "__main__":
    sys.exit(main())
