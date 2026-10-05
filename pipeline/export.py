"""Export: the grading folder, the run evidence, then the supplied checker.

Everything is written from the state file. Export always writes and always reports what
the checker says; it never hides a `review_required`.
"""

import csv
import gzip
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from pipeline import hashing, memo, rank, state

VERSION = "a5-audit-v1"
GZIPPABLE = (
    "records.jsonl",
    "calls.jsonl",
)  # the only files the checker reads compressed
LABEL_FIELDS = (
    "topic",
    "intent",
    "sentiment",
    "severity",
    "entities",
    "evidence_quote",
    "needs_review",
)


class NotReady(Exception):
    """Something is still unfinished. Export describes a finished run."""


def _dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        n = 0
        for row in rows:
            f.write(_dump(row) + "\n")
            n += 1
    return n


def boundary(db, run):
    """The classify session whose end is the checkpoint, or None.

    It is the first session that completed at least one original while a later session
    completed at least one more. A run that was never stopped has none.
    """
    done = dict(
        db.execute(
            "SELECT completed_session, COUNT(*) FROM reviews WHERE run=? AND status='completed' "
            "AND cache_source_id IS NULL GROUP BY completed_session",
            (run,),
        ).fetchall()
    )
    sessions = sorted(done)
    return sessions[0] if len(sessions) > 1 else None


def _records(db, run, label_config):
    for r in db.execute(
        "SELECT r.review_id, r.source_sha256, r.status, r.reason, r.cache_source_id, s.topic, s.intent, s.sentiment, "
        "s.severity, s.entities_json, s.evidence_quote, s.needs_review FROM reviews r "
        "LEFT JOIN results s ON s.run=r.run AND s.text_key=r.text_key WHERE r.run=? ORDER BY r.run_order",
        (run,),
    ):
        if r["status"] != "completed":
            # A quarantined copy carries no pointer: there is no valid result to point at.
            yield {
                "review_id": r["review_id"],
                "source_sha256": r["source_sha256"],
                "status": "quarantined",
                "reason": r["reason"],
            }
            continue
        assert r["topic"] is not None, (
            f"completed review {r['review_id']} has no saved result"
        )
        record = {
            "review_id": r["review_id"],
            "source_sha256": r["source_sha256"],
            "status": "completed",
            "topic": r["topic"],
            "intent": r["intent"],
            "sentiment": r["sentiment"],
            "severity": r["severity"],
            "entities": json.loads(r["entities_json"]),
            "evidence_quote": r["evidence_quote"],
            "needs_review": bool(r["needs_review"]),
            "label_config": label_config,
        }
        if r["cache_source_id"]:
            record["cache_source_id"] = r["cache_source_id"]
        yield record


def _calls(db, run, boundary_session):
    for c in db.execute("SELECT * FROM calls WHERE run=? ORDER BY rowid", (run,)):
        known = bool(c["usage_known"])
        call = {
            "request_id": c["request_id"],
            "role": c["role"],
            "review_ids": json.loads(c["review_ids_json"]),
            "model": c["model"],
            "outcome": c["outcome"],
            "label_config": c["label_config"],
            # The checker flags a missing count, so unknown usage is written as zero with a marker (spec item 13).
            "input_tokens": c["input_tokens"] if known else 0,
            "output_tokens": (c["output_tokens"] or 0) if known else 0,
            "usage_known": known,
        }
        if c["role"] == "enrich":
            call["phase"] = (
                "initial"
                if boundary_session is None or c["session_id"] <= boundary_session
                else "resume"
            )
        yield call


def _ranking(db, run):
    members = db.execute(
        "SELECT m.issue_id, m.review_id, s.intent, s.severity FROM membership m "
        "JOIN reviews r ON r.run=m.run AND r.review_id=m.review_id AND r.status='completed' "
        "JOIN results s ON s.run=r.run AND s.text_key=r.text_key WHERE m.run=? ORDER BY m.issue_id, m.review_id",
        (run,),
    ).fetchall()
    membership = [(m["issue_id"], m["review_id"]) for m in members]
    records = [
        {
            "review_id": m["review_id"],
            "status": "completed",
            "intent": m["intent"],
            "severity": m["severity"],
        }
        for m in members
    ]
    return membership, rank.rank(records, membership)


def _memo_problems(db, run, text):
    """Check the saved memo again, against the numbers as they are being exported."""
    pointer = db.execute(
        "SELECT input_json FROM artifacts WHERE key=?", (f"final-memo:{run}",)
    ).fetchone()
    saved = (
        db.execute(
            "SELECT input_json FROM artifacts WHERE key=?", (pointer["input_json"],)
        ).fetchone()
        if pointer
        else None
    )
    per_issue = memo.PER_ISSUE
    if saved:
        sizes = [
            len(quotes)
            for quotes in json.loads(saved["input_json"])["evidence"].values()
        ]
        per_issue = max([per_issue, *sizes])
    return memo.check(text, memo.evidence_pack(db, run, per_issue=per_issue))


def _gzip(path):
    """Replace a JSONL file with its gzip. The checker flags both forms present together."""
    target = Path(str(path) + ".gz")
    with open(path, "rb") as source, open(target, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as packed:
            shutil.copyfileobj(source, packed)
    path.unlink()
    return target


def _checker(python, checker_path, *args):
    done = subprocess.run(
        [python, str(checker_path), *map(str, args)], capture_output=True, text=True
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"the supplied checker failed on {args[0]}: {done.stderr.strip()[-500:]}"
        )


def export(
    db, run, out_dir, *, checker_path, input_path, gzip_over=50_000_000, size_limit=95_000_000,
    evidence_dir=None, work_dir=None, cap_usd=Decimal("25"), log=None, python=sys.executable,
):  # fmt: skip
    """Write the grading folder for a finished run, run the supplied checker, and return what it said."""
    say = log or (lambda *_: None)
    out_dir = Path(out_dir)
    if db.execute(
        "SELECT 1 FROM reviews WHERE run=? AND status='pending' LIMIT 1", (run,)
    ).fetchone():
        raise NotReady("reviews are still pending: finish or resume the run first")
    if db.execute(
        "SELECT 1 FROM calls WHERE run=? AND outcome='pending' LIMIT 1", (run,)
    ).fetchone():
        raise NotReady(
            "a call has no outcome yet: resume the run so it is closed first"
        )
    run_row = state.load_run(db, run)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(work_dir) if work_dir else out_dir.parent
    notes = []

    boundary_session = boundary(db, run)
    if boundary_session is None:
        notes.append(
            "no boundary: no session left an original unlabeled that a later session then labeled. "
            "The checker will flag the resume evidence. Stop a run once on purpose and resume it."
        )
        say(notes[-1])

    for name in GZIPPABLE:  # never leave a form behind from an earlier export
        for stale in (out_dir / name, out_dir / (name + ".gz")):
            stale.unlink(missing_ok=True)
    n_rows = _write_jsonl(
        out_dir / "records.jsonl", _records(db, run, run_row["label_config"])
    )
    calls = list(_calls(db, run, boundary_session))
    _write_jsonl(out_dir / "calls.jsonl", calls)
    unknown_usage = sum(not c["usage_known"] for c in calls)

    membership, ranking = _ranking(db, run)
    with open(out_dir / "membership.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(
            [("issue_id", "review_id"), *membership]
        )
    rank.write_csv(out_dir / "ranking.csv", ranking)

    memo_text = memo.final(db, run)
    cited = memo.cited_claims(memo_text, memo.claims(ranking)) if memo_text else []
    with open(out_dir / "claims.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=("claim_id", "issue_id", "metric", "value"),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(cited)
    memo_problems = _memo_problems(db, run, memo_text) if memo_text else []
    if not memo_text:
        notes.append(
            "no memo: claims.csv is empty and the checker will flag the missing role and claims"
        )
    for problem in memo_problems:
        say("memo no longer matches the export: " + problem)

    completed = [
        r["review_id"]
        for r in db.execute(
            "SELECT review_id FROM reviews WHERE run=? AND status='completed' ORDER BY run_order",
            (run,),
        )
    ]
    before = (
        [
            r["review_id"]
            for r in db.execute(
                "SELECT review_id FROM reviews WHERE run=? AND status='completed' AND completed_session<=? ORDER BY run_order",
                (run, boundary_session),
            )
        ]
        if boundary_session is not None
        else []
    )
    _write_json(out_dir / "checkpoint_before.json", {"completed_ids": before})
    _write_json(out_dir / "checkpoint_after.json", {"completed_ids": completed})
    _write_json(
        out_dir / "run.json",
        {
            "version": VERSION,
            "analysis_count": n_rows,
            "analysis_sha256": hashing.file_sha(input_path),
            "classification_input_fields": ["review_text"],
            "allow_multi_issue": False,
        },
    )
    _checker(
        python,
        checker_path,
        "profile",
        "--full",
        input_path,
        "--out",
        out_dir / "ingestion.json",
    )

    for name in GZIPPABLE:
        if (out_dir / name).stat().st_size > gzip_over:
            _gzip(out_dir / name)
    release_assets = sorted(
        p.name
        for p in out_dir.iterdir()
        if p.is_file() and p.stat().st_size > size_limit
    )
    for name in release_assets:
        say(
            f"{name} is over {size_limit} bytes: attach it as a release asset, GitHub will not take it in the repo"
        )

    reference, report_path = (
        work_dir / "local-reference.json",
        work_dir / "self-check.json",
    )
    _checker(
        python,
        checker_path,
        "reference",
        "--full",
        input_path,
        "--analysis",
        input_path,
        "--out",
        reference,
    )
    _checker(
        python,
        checker_path,
        "check",
        "--reference",
        reference,
        "--submission",
        out_dir,
        "--out",
        report_path,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    say(f"checker status: {report['status']}")
    for code, count in report["issue_counts"].items():
        say(f"  flag {code}: {count}")

    result = {
        "status": report["status"],
        "issue_counts": report["issue_counts"],
        "examples": report["examples"],
        "coverage": report["coverage"],
        "coverage_point": report["working_coverage_point_candidate"],
        "boundary_session": boundary_session,
        "notes": notes,
        "release_assets": release_assets,
        "memo_problems": memo_problems,
        "calls_with_unknown_usage": unknown_usage,
    }
    if evidence_dir:
        _evidence(
            db,
            run,
            run_row,
            Path(evidence_dir),
            out_dir,
            input_path,
            memo_text,
            result,
            before,
            completed,
            cap_usd,
        )
    return result


def _evidence(
    db,
    run,
    run_row,
    folder,
    out_dir,
    input_path,
    memo_text,
    result,
    before,
    completed,
    cap_usd,
):
    """The run evidence the brief asks for beside the grading folder, so a reader never needs the state file."""
    folder.mkdir(parents=True, exist_ok=True)
    call_rows = db.execute(
        "SELECT * FROM calls WHERE run=? ORDER BY rowid", (run,)
    ).fetchall()
    _write_jsonl(
        folder / "run_log.jsonl",
        (
            {
                **{k: c[k] for k in c.keys() if k != "review_ids_json"},
                "review_ids": json.loads(c["review_ids_json"]),
            }
            for c in call_rows
        ),
    )
    _write_jsonl(
        folder / "quarantine.jsonl",
        (
            dict(r)
            for r in db.execute(
                "SELECT review_id, reason, attempts FROM reviews WHERE run=? AND status='quarantined' ORDER BY run_order",
                (run,),
            )
        ),
    )
    _write_jsonl(
        folder / "verify_predictions.jsonl",
        (
            dict(r)
            for r in db.execute(
                "SELECT * FROM verify WHERE run=? ORDER BY review_id", (run,)
            )
        ),
    )
    _write_jsonl(
        folder / "artifacts.jsonl",
        (
            {"key": a["key"], "role": a["role"], "model": a["model"], "created_utc": a["created_utc"],
             "input": a["input_json"], "output": json.loads(a["output_json"])}
            for a in db.execute("SELECT * FROM artifacts WHERE run=? ORDER BY created_utc, key", (run,))
        ),
    )  # fmt: skip
    (folder / "memo.md").write_text(
        (memo_text or "No memo was written for this run.") + "\n", encoding="utf-8"
    )

    by_role = {}
    for c in call_rows:
        role = by_role.setdefault(
            c["role"],
            {
                "succeeded": 0,
                "failed": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "calls_with_unknown_usage": 0,
            },
        )
        role[c["outcome"]] += 1
        role["input_tokens"] += c["input_tokens"] or 0
        role["output_tokens"] += c["output_tokens"] or 0
        role["calls_with_unknown_usage"] += not c["usage_known"]
    spent = kept = Decimal(0)
    for row in db.execute(
        "SELECT * FROM ledger WHERE run=? AND kind IN ('actual','kept')", (run,)
    ):
        usd = (
            row["input_tokens"] * Decimal(row["usd_per_mtok_in"])
            + row["output_tokens"] * Decimal(row["usd_per_mtok_out"])
        ) / 1_000_000
        spent += usd
        kept += usd if row["kind"] == "kept" else 0
    _write_json(
        folder / "run_summary.json",
        {
            "run": run,
            "statuses": dict(
                db.execute(
                    "SELECT status, COUNT(*) FROM reviews WHERE run=? GROUP BY status",
                    (run,),
                ).fetchall()
            ),
            "quarantine_reasons": dict(
                db.execute(
                    "SELECT reason, COUNT(*) FROM reviews WHERE run=? AND status='quarantined' GROUP BY reason",
                    (run,),
                ).fetchall()
            ),
            "sessions": [
                {
                    "session_id": s["session_id"],
                    "stage": s["stage"],
                    "workers": s["workers"],
                    "started_utc": s["started_utc"],
                    "seconds": None
                    if s["ended_mono"] is None
                    else round(s["ended_mono"] - s["started_mono"], 3),
                    "ended_how": s["ended_how"],
                }
                for s in db.execute(
                    "SELECT * FROM sessions WHERE run=? ORDER BY session_id", (run,)
                )
            ],  # fmt: skip
            "calls": by_role,
            "spend": {
                "cap_usd": str(cap_usd),
                "jev_usd_this_run": str(spent),
                "of_which_reservations_kept_for_unknown_usage_usd": str(kept),
                "note": "Computed from the ledger at the rates stored on each row. Output tokens are counted at the rate in "
                "pipeline/billing.json; whether the provider bills them is settled against its usage page.",
            },
            "resume": {
                "boundary_session": result["boundary_session"],
                "completed_before": len(before),
                "completed_after": len(completed),
            },
            "accepted_guards": json.loads(run_row["configs_json"]).get(
                "accepted_guards", []
            ),
            "code_overrides": json.loads(run_row["configs_json"]).get(
                "code_overrides", []
            ),
            "checker": {
                k: result[k]
                for k in ("status", "issue_counts", "coverage", "coverage_point")
            },
            "notes": result["notes"],
        },
    )
    _write_json(
        folder / "run_manifest.json",
        {
            "run": run,
            "created_utc": run_row["created_utc"],
            "exported_utc": state.now_utc(),
            "input_file": Path(input_path).name,
            "input_sha256": hashing.file_sha(input_path),
            "seed": run_row["seed"],
            "verify_seed": run_row["verify_seed"],
            "verify_size": run_row["verify_size"],
            "sample_seed": run_row["sample_seed"],
            "code_commit": run_row["code_commit"],
            "code_hash": run_row["code_hash"],
            "label_config": run_row["label_config"],
            "content_hashes": json.loads(run_row["hashes_json"]),
            "stage_configs": {
                k: v
                for k, v in json.loads(run_row["configs_json"]).items()
                if k not in ("accepted_guards", "code_overrides")
            },
            "models": sorted({f"{c['role']}: {c['model']}" for c in call_rows}),
            "outputs": {
                p.name: hashing.file_sha(p)
                for p in sorted(out_dir.iterdir())
                if p.is_file()
            },
        },
    )
