"""Write the pilot's evidence from the state file. This is the only step of the calculator that opens it.

After this, replay needs nothing but the files written here and the editable rate files.
"""

import csv
import json
from decimal import Decimal
from pathlib import Path

from pipeline import export, hashing, memo, state, verify

STAGES = ("classify", "verify", "group", "memo")
ROLE = {"classify": "enrich", "verify": "verify", "group": "group", "memo": "memo"}
PROVIDER = {"classify": "TypeSafe", "verify": "LM Studio (local)", "group": "LM Studio (local)", "memo": "LM Studio (local)"}
COLUMNS = (
    "run_id", "pass", "stage", "provider", "model", "config", "batch_size", "workers", "requests", "attempts",
    "succeeded", "failed", "input_tokens", "output_tokens", "calls_usage_unknown", "seconds", "note",
)  # fmt: skip


class BadPilot(Exception):
    """The two runs are not a clean cold and warm pair, so they are not saved as pilot evidence."""


def pilot_steps(db, cold, warm):
    """The steps a pilot still has to take, in order, read from the state file. Empty means only the evidence is left.

    Raises BadPilot when a run that exists cannot become part of a clean pilot, and says which new name to pass.
    """

    def exists(run):
        return db.execute("SELECT 1 FROM runs WHERE run=?", (run,)).fetchone() is not None

    def count(sql, *args):
        return db.execute(sql, args).fetchone()[0]

    steps = []
    if not exists(cold):
        steps += ["cold_start", "cold_resume"]
    else:
        pending = count("SELECT COUNT(*) FROM reviews WHERE run=? AND status='pending'", cold)
        originals = count("SELECT COUNT(*) FROM reviews WHERE run=? AND status='completed' AND cache_source_id IS NULL", cold)
        members = count("SELECT COUNT(*) FROM membership WHERE run=?", cold)
        whole = pending == 0 and not verify._todo(db, cold) and (memo.final(db, cold) is not None or (originals and not members and
                 count("SELECT COUNT(*) FROM sessions WHERE run=? AND stage='group'", cold)))  # fmt: skip
        if originals == 0:
            # Nothing completed yet, so there is no saved work to resume across. Start again with the planned stop.
            steps += ["cold_restart", "cold_resume"]
        elif not whole:
            steps.append("cold_resume")
        elif export.boundary(db, cold) is None:
            raise BadPilot(
                f"run {cold} finished without being stopped and resumed, so it has no resume evidence. "
                "Start a fresh pilot under new names: --cold NAME --warm NAME"
            )
    if not exists(warm):
        steps.append("warm")
    else:
        record = db.execute("SELECT output_json FROM artifacts WHERE key=?", (f"warm:{warm}",)).fetchone()
        calls = count("SELECT COUNT(*) FROM calls WHERE run=?", warm)
        if record is None or calls or json.loads(record["output_json"]).get("source_run") != cold:
            raise BadPilot(f"run {warm} exists and is not a clean warm pass of {cold}. Use a new name for it: --warm NAME")
    return steps


def _provider(stage, model):
    return "Anthropic" if str(model).startswith("claude-") else PROVIDER[stage]


def usage_rows(db, run, which):
    """One row per stage and one for the whole run. A stage's seconds are its session clock."""
    row = state.load_run(db, run)
    rows, total, requests_total = [], Decimal(0), 0
    for stage in STAGES:
        sessions = db.execute("SELECT * FROM sessions WHERE run=? AND stage=?", (run, stage)).fetchall()
        seconds = sum((Decimal(f"{s['ended_mono'] - s['started_mono']:.6f}") for s in sessions if s["ended_mono"] is not None), Decimal(0))
        calls = db.execute("SELECT * FROM calls WHERE run=? AND role=?", (run, ROLE[stage])).fetchall()
        succeeded = sum(c["outcome"] == "succeeded" for c in calls)
        if stage in ("classify", "verify"):
            requests = len({c["review_ids_json"] for c in calls})
        else:
            requests = succeeded or (1 if calls else 0)
        total += seconds
        requests_total += requests
        rows.append(
            {
                "run_id": run, "pass": which, "stage": stage, "provider": _provider(stage, calls[0]["model"]) if calls else "",
                "model": calls[0]["model"] if calls else "", "config": calls[0]["label_config"] if calls else "",
                "batch_size": 1, "workers": max((s["workers"] for s in sessions), default=0), "requests": requests,
                "attempts": len(calls), "succeeded": succeeded, "failed": len(calls) - succeeded,
                "input_tokens": sum(c["input_tokens"] or 0 for c in calls), "output_tokens": sum(c["output_tokens"] or 0 for c in calls),
                "calls_usage_unknown": sum(not c["usage_known"] for c in calls), "seconds": str(seconds), "note": "",
            }
        )  # fmt: skip
    name = Path(row["input_path"]).name
    sha = hashing.file_sha(row["input_path"]) if Path(row["input_path"]).exists() else row["input_sha256"]
    rows.append(
        {
            **{k: "" for k in COLUMNS}, "run_id": run, "pass": which, "stage": "end_to_end", "batch_size": 1, "workers": 0,
            "requests": requests_total, "attempts": sum(r["attempts"] for r in rows), "succeeded": sum(r["succeeded"] for r in rows),
            "failed": sum(r["failed"] for r in rows), "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows), "calls_usage_unknown": sum(r["calls_usage_unknown"] for r in rows),
            "seconds": str(total),
            "note": f"{name}, SHA-256 {sha}, label_config {row['label_config']}. Time is the sum of the run's sessions; idle time between a stop and a resume is left out",
        }
    )  # fmt: skip
    return rows


def _call_rows(db, run, which):
    reserved = dict(db.execute("SELECT request_id, input_tokens FROM ledger WHERE run=? AND kind='reserve'", (run,)).fetchall())
    stage_of = {role: stage for stage, role in ROLE.items()}
    for c in db.execute("SELECT * FROM calls WHERE run=? ORDER BY rowid", (run,)):
        known = bool(c["usage_known"])
        row = {
            "run_id": run, "pass": which, "request_id": c["request_id"], "role": c["role"], "stage": stage_of.get(c["role"], c["role"]),
            "review_ids": json.loads(c["review_ids_json"]), "model": c["model"], "config": c["label_config"], "outcome": c["outcome"],
            "input_tokens": c["input_tokens"] if known else 0, "output_tokens": (c["output_tokens"] or 0) if known else 0,
            "usage_known": known, "http_status": c["http_status"], "seconds": c["seconds"], "session_id": c["session_id"],
            "started_utc": c["started_utc"],
        }  # fmt: skip
        if c["request_id"] in reserved:
            row["request_bytes"] = reserved[c["request_id"]]  # the reservation is the request body's size in bytes
        yield row


def write(db, cold_run, warm_run, out_dir):
    """Save a finished cold run and its warm pass as pilot evidence. Raises BadPilot if they are not a clean pair."""
    out_dir = Path(out_dir)
    if cold_run == warm_run:
        raise BadPilot("the cold run and the warm run are the same run")
    for run in (cold_run, warm_run):
        if db.execute("SELECT 1 FROM reviews WHERE run=? AND status='pending' LIMIT 1", (run,)).fetchone():
            raise BadPilot(f"run {run} is not finished")
    warm_calls = db.execute("SELECT COUNT(*) FROM calls WHERE run=?", (warm_run,)).fetchone()[0]
    if warm_calls:
        raise BadPilot(f"the warm run made {warm_calls} calls; a warm pass makes none")
    roles = {r[0] for r in db.execute("SELECT DISTINCT role FROM calls WHERE run=? AND outcome='succeeded'", (cold_run,))}
    if roles != {"enrich", "verify", "group", "memo"}:
        raise BadPilot(f"the cold run did not go through every stage: succeeded calls only for {sorted(roles)}")
    status = "SELECT review_id, status FROM reviews WHERE run=? ORDER BY review_id"
    if db.execute(status, (cold_run,)).fetchall() != db.execute(status, (warm_run,)).fetchall():
        raise BadPilot("the warm run's results differ from the cold run's")

    cold = state.load_run(db, cold_run)
    with open(out_dir / "pilot_records.jsonl", "w", encoding="utf-8") as f:
        for record in export._records(db, cold_run, cold["label_config"]):
            f.write(json.dumps({"run_id": cold_run, **record}, ensure_ascii=False) + "\n")
    with open(out_dir / "pilot_calls.jsonl", "w", encoding="utf-8") as f:
        for row in _call_rows(db, cold_run, "cold"):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        marker = {"run_id": warm_run, "pass": "warm", "calls_made": 0, "record": f"no call of any role was made; every result came from run {cold_run}"}
        f.write(json.dumps(marker) + "\n")
    with open(out_dir / "usage.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(usage_rows(db, cold_run, "cold") + usage_rows(db, warm_run, "warm"))


def text_volume(full_csv, pilot_csv):
    """How much review text the full file and the pilot hold, in UTF-8 bytes. Code only."""

    def read(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            return [row["review_text"] for row in csv.DictReader(f, strict=True)]

    full, pilot = read(full_csv), read(pilot_csv)
    nonempty = [t for t in full if t.strip()]
    distinct = set(nonempty)
    return {
        "full_file_sha256": hashing.file_sha(full_csv),
        "full_rows": len(full),
        "full_nonempty_rows": len(nonempty),
        "full_nonempty_text_bytes": sum(len(t.encode("utf-8")) for t in nonempty),
        "full_distinct_texts": len(distinct),
        "full_distinct_text_bytes": sum(len(t.encode("utf-8")) for t in distinct),
        "pilot_rows": len(pilot),
        "pilot_text_bytes": sum(len(t.encode("utf-8")) for t in pilot),
    }
