#!/opt/homebrew/bin/python3
"""Red-team harness for check_submission.py. Standard library only. No network, no model calls.

Writes only inside the scratch folder. Imports row_sha from the checker without writing bytecode.
Usage:  /opt/homebrew/bin/python3 -B harness.py            (runs every case)
        /opt/homebrew/bin/python3 -B harness.py a5 a12     (runs cases whose name starts with a prefix)
"""

import sys

sys.dont_write_bytecode = True  # never create __pycache__ inside the project folder

import copy
import csv
import json
import shutil
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

SCRATCH = Path(__file__).resolve().parent
CHECKER_DIR = str(Path(__file__).resolve().parents[4] / "feed/Final Assignment - Spotify Reviews Dataset")
CHECKER = CHECKER_DIR + "/check_submission.py"
PY = "/opt/homebrew/bin/python3"
sys.path.insert(0, CHECKER_DIR)
from check_submission import row_sha  # noqa: E402

FIELDS = (
    "review_id",
    "review_text",
    "review_rating",
    "review_likes",
    "app_version",
    "review_timestamp",
)
ROWS = [
    (
        "r01",
        "App crashes every time I open it",
        "1",
        "3",
        "9.0.1",
        "2025-01-03 10:00:00",
    ),
    ("r02", "Great app", "5", "0", "9.0.1", "2025-01-04 11:00:00"),
    ("r03", "Too many ads now", "2", "1", "9.0.2", "2025-01-09 12:00:00"),
    ("r04", "Cannot log in", "1", "7", "", "2025-02-01 08:30:00"),
    ("r05", "", "3", "0", "9.0.2", "2025-02-02 09:00:00"),
    (
        "r06",
        "Downloads keep disappearing after update",
        "2",
        "4",
        "9.0.3",
        "2025-02-11 13:00:00",
    ),
    ("r07", "Please add a sleep timer", "4", "0", "9.0.3", "2025-02-15 14:00:00"),
    ("r08", "  Love the playlists  ", "5", "2", "9.0.3", "2025-03-01 15:00:00"),
    ("r09", "Great app", "5", "0", "", "2025-03-02 16:00:00"),
    ("r10", "I was charged twice this month", "1", "9", "9.0.4", "2025-03-05 17:00:00"),
    ("r11", "Too many ads now", "2", "0", "9.0.4", "2025-03-09 18:00:00"),
    (
        "r12",
        "Support never answered my ticket",
        "1",
        "1",
        "9.0.4",
        "2025-04-01 19:00:00",
    ),
    (
        "r13",
        "Uninstalling, the shuffle is broken",
        "1",
        "5",
        "9.0.5",
        "2025-04-03 20:00:00",
    ),
    ("r14", "Great app", "4", "0", "9.0.5", "2025-04-08 21:00:00"),
    (
        "r15",
        "Search cannot find my favorite artist",
        "2",
        "0",
        "9.0.5",
        "2025-05-01 07:00:00",
    ),
    ("r16", "asdf qwerty", "3", "0", "9.0.5", "2025-05-02 07:30:00"),
    ("r17", "", "1", "0", "", "2025-05-03 08:00:00"),
    ("r18", "Music stops when screen locks", "2", "6", "9.0.6", "2025-05-10 09:00:00"),
    ("r19", "Premium price went up again", "2", "2", "9.0.6", "2025-06-01 10:00:00"),
    ("r20", "Too many ads now", "1", "0", "9.0.6", "2025-06-02 11:00:00"),
    (
        "r21",
        "Lyrics are missing for many songs",
        "3",
        "0",
        "9.0.6",
        "2025-06-12 12:00:00",
    ),
    ("r22", "Best music app ever", "5", "1", "9.0.7", "2025-07-01 13:00:00"),
    ("r23", "   ", "4", "0", "9.0.7", "2025-07-02 14:00:00"),
    (
        "r24",
        "Offline mode does not work on the plane",
        "1",
        "8",
        "9.0.7",
        "2025-07-09 15:00:00",
    ),
    ("r25", "Cannot log in", "1", "0", "9.0.7", "2025-08-01 16:00:00"),
    ("r26", "The new layout is confusing", "2", "0", "9.0.8", "2025-08-04 17:00:00"),
    ("r27", "Great app", "5", "0", "9.0.8", "2025-08-20 18:00:00"),
    (
        "r28",
        "Cancel my subscription, too expensive",
        "1",
        "3",
        "9.0.8",
        "2025-09-01 19:00:00",
    ),
    (
        "r29",
        "Audio quality is poor on bluetooth",
        "2",
        "0",
        "9.0.9",
        "2025-09-05 20:00:00",
    ),
    (
        "r30",
        "Password reset email never arrives",
        "1",
        "4",
        "9.0.9",
        "2025-09-15 21:00:00",
    ),
]


def L(topic, intent, sentiment, severity, quote):
    return dict(
        topic=topic,
        intent=intent,
        sentiment=sentiment,
        severity=severity,
        entities=["Spotify"],
        evidence_quote=quote,
        needs_review=False,
    )


LAB = {
    "App crashes every time I open it": L(
        "playback", "complaint", -0.8, 4, "crashes every time"
    ),
    "Great app": L("other", "praise", 0.9, 1, "Great"),
    "Too many ads now": L("usability", "complaint", -0.5, 2, "Too many ads"),
    "Cannot log in": L("access", "complaint", -0.7, 4, "Cannot log in"),
    "Downloads keep disappearing after update": L(
        "downloads", "complaint", -0.6, 3, "keep disappearing"
    ),
    "Please add a sleep timer": L("usability", "request", 0.1, 1, "add a sleep timer"),
    "  Love the playlists  ": L("catalog", "praise", 0.8, 1, "playlists"),
    "I was charged twice this month": L(
        "billing", "complaint", -0.9, 5, "charged twice"
    ),
    "Support never answered my ticket": L(
        "support", "complaint", -0.7, 3, "never answered"
    ),
    "Uninstalling, the shuffle is broken": L(
        "playback", "cancellation", -0.8, 3, "shuffle is broken"
    ),
    "Search cannot find my favorite artist": L(
        "catalog", "complaint", -0.4, 3, "cannot find"
    ),
    "asdf qwerty": L("other", "unclear", 0.5, 1, "asdf"),
    "Music stops when screen locks": L("playback", "complaint", -0.5, 3, "Music stops"),
    "Premium price went up again": L("billing", "complaint", -0.4, 2, "price went up"),
    "Lyrics are missing for many songs": L(
        "catalog", "complaint", -0.3, 2, "Lyrics are missing"
    ),
    "Best music app ever": L("other", "praise", 0.95, 1, "Best music app"),
    "Offline mode does not work on the plane": L(
        "downloads", "complaint", -0.7, 4, "does not work"
    ),
    "The new layout is confusing": L("usability", "complaint", -0.4, 2, "confusing"),
    "Cancel my subscription, too expensive": L(
        "billing", "cancellation", -0.6, 2, "too expensive"
    ),
    "Audio quality is poor on bluetooth": L(
        "playback", "complaint", -0.5, 3, "quality is poor"
    ),
    "Password reset email never arrives": L(
        "access", "complaint", -0.7, 4, "never arrives"
    ),
}

INPUT = SCRATCH / "input.csv"
REF = SCRATCH / "reference.json"
ING = SCRATCH / "ingestion.json"


def cli(*args):
    r = subprocess.run(
        [PY, "-B", CHECKER, *map(str, args)], capture_output=True, text=True
    )
    if r.returncode:
        raise RuntimeError("checker CLI failed: " + r.stderr)
    return r.stdout


def setup():
    with INPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        w.writerows(ROWS)
    cli("reference", "--full", INPUT, "--analysis", INPUT, "--out", REF)
    cli("profile", "--full", INPUT, "--out", ING)


def source_rows():
    return [dict(zip(FIELDS, r)) for r in ROWS]


def enrich(
    req,
    ids,
    phase,
    lc="LC1",
    model="small-model",
    outcome="succeeded",
    tin=None,
    tout=None,
):
    return dict(
        request_id=req,
        role="enrich",
        review_ids=list(ids),
        model=model,
        phase=phase,
        outcome=outcome,
        label_config=lc,
        input_tokens=200 * len(ids) if tin is None else tin,
        output_tokens=120 * len(ids) if tout is None else tout,
    )


def build(sessions=2, original="first", lc="LC1", batch=5):
    """Clean state. sessions=2 -> batches 1-2 initial, 3-5 resume. sessions=5 -> one batch per session."""
    ref = json.loads(REF.read_text())
    rows = source_rows()
    groups = {}
    for row in rows:
        if row["review_text"].strip():
            groups.setdefault(row["review_text"], []).append(row["review_id"])
    origin = {}
    for text, rids in groups.items():
        o = rids[0] if original == "first" else rids[-1]
        for r in rids:
            origin[r] = None if r == o else o
    records = {}
    for row in rows:
        rid, text = row["review_id"], row["review_text"]
        if not text.strip():
            records[rid] = dict(
                review_id=rid,
                source_sha256=row_sha(row),
                status="quarantined",
                reason="empty_review_text",
            )
        else:
            rec = dict(
                review_id=rid,
                source_sha256=row_sha(row),
                status="completed",
                **copy.deepcopy(LAB[text]),
                label_config=lc,
            )
            if origin[rid]:
                rec["cache_source_id"] = origin[rid]
            records[rid] = rec
    originals = [
        r["review_id"]
        for r in rows
        if r["review_text"].strip() and origin[r["review_id"]] is None
    ]
    batches = [originals[i : i + batch] for i in range(0, len(originals), batch)]
    session_of = [1, 1, 2, 2, 2] if sessions == 2 else [1, 2, 3, 4, 5]
    calls, session1 = [], []
    for i, b in enumerate(batches):
        s = session_of[i]
        calls.append(
            enrich(f"req-enrich-{i + 1:03d}", b, "initial" if s == 1 else "resume", lc)
        )
        if s == 1:
            session1 += b
    for role in ("verify", "group", "memo"):
        calls.append(
            dict(
                request_id=f"req-{role}-001",
                role=role,
                review_ids=[],
                model="small-model",
                outcome="succeeded",
                input_tokens=500,
                output_tokens=100,
            )
        )
    completed = [rid for rid, r in records.items() if r["status"] == "completed"]
    membership = [
        ("ISS-" + r["topic"], rid)
        for rid, r in records.items()
        if r["status"] == "completed" and r["intent"] in ("complaint", "cancellation")
    ]
    return dict(
        run=dict(
            version="a5-audit-v1",
            analysis_count=len(ref["rows"]),
            analysis_sha256=ref["analysis_sha256"],
            classification_input_fields=["review_text"],
            allow_multi_issue=False,
        ),
        records=records,
        calls=calls,
        before=list(session1),
        after=completed,
        membership=membership,
        originals=originals,
        batches=batches,
        session_of=session_of,
    )


def ranking(state):
    agg = {}
    for iid, rid in state["membership"]:
        rec = state["records"].get(rid, {})
        if rec.get("status") == "completed" and rec.get("intent") in (
            "complaint",
            "cancellation",
        ):
            agg.setdefault(iid, []).append(rec["severity"])
    out = []
    for iid, sev in agg.items():
        mean = str(
            (Decimal(sum(sev)) / Decimal(len(sev))).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
        )
        out.append(
            dict(
                issue_id=iid,
                complaint_count=len(sev),
                severity_sum=sum(sev),
                mean_severity=mean,
                priority_score=sum(sev),
            )
        )
    out.sort(key=lambda x: (-x["priority_score"], x["issue_id"]))
    for n, row in enumerate(out, 1):
        row["rank"] = n
    return out


def write(folder, state):
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps(state["run"]))
    shutil.copy(ING, folder / "ingestion.json")
    with (folder / "records.jsonl").open("w", encoding="utf-8") as f:
        for rec in state["records"].values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with (folder / "calls.jsonl").open("w", encoding="utf-8") as f:
        for c in state["calls"]:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (folder / "checkpoint_before.json").write_text(
        json.dumps({"completed_ids": state["before"]})
    )
    (folder / "checkpoint_after.json").write_text(
        json.dumps({"completed_ids": state["after"]})
    )
    with (folder / "membership.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["issue_id", "review_id"])
        w.writerows(state["membership"])
    rk = ranking(state)
    cols = [
        "rank",
        "issue_id",
        "complaint_count",
        "severity_sum",
        "mean_severity",
        "priority_score",
    ]
    with (folder / "ranking.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for row in rk:
            w.writerow([row[c] for c in cols])
    with (folder / "claims.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["claim_id", "issue_id", "metric", "value"])
        for row in rk:
            w.writerow(
                [
                    f"C-{row['issue_id']}-count",
                    row["issue_id"],
                    "complaint_count",
                    row["complaint_count"],
                ]
            )
            w.writerow(
                [
                    f"C-{row['issue_id']}-mean",
                    row["issue_id"],
                    "mean_severity",
                    row["mean_severity"],
                ]
            )


RESULTS = []


def check(name, state, note=""):
    case = SCRATCH / "cases" / name
    write(case / "grading", state)
    out = case / "result.json"
    cli("check", "--reference", REF, "--submission", case / "grading", "--out", out)
    res = json.loads(out.read_text())
    RESULTS.append((name, res["status"], res["issue_counts"], note))
    print(
        f"{name:34s} status={res['status']:16s} issue_counts={json.dumps(res['issue_counts'])}  {note}"
    )
    return res


def call_with(state, req):
    return next(c for c in state["calls"] if c["request_id"] == req)


# ---------------------------------------------------------------- cases
CASES = {}


def case(fn):
    CASES[fn.__name__] = fn
    return fn


@case
def b0_baseline_2sessions():
    check(
        "b0_baseline_2sessions",
        build(),
        "baseline: before=r01,r02,r03,r04,r06,r07,r08,r10,r12,r13",
    )


# A1 ------------------------------------------------------------------
@case
def a1_i_two_initial_calls_id_in_before():
    s = build()
    s["calls"].append(enrich("req-x1", ["r01"], "initial"))
    check(
        "a1_i_two_initial_calls_id_in_before",
        s,
        "r01 in two succeeded initial calls, same LC",
    )


@case
def a1_ii_two_resume_calls_id_not_in_before():
    s = build()
    s["calls"].append(enrich("req-x1", ["r15"], "resume"))
    check(
        "a1_ii_two_resume_calls_id_not_in_before",
        s,
        "r15 in two succeeded resume calls, same LC",
    )


@case
def a1_iii_second_call_resume_id_in_before():
    s = build()
    s["calls"].append(enrich("req-x1", ["r01"], "resume"))
    check(
        "a1_iii_second_call_resume_id_in_before",
        s,
        "r01 (in before) gets 2nd call with phase resume",
    )


@case
def a1_iv_initial_then_resume_id_not_in_before():
    s = build()
    s["calls"].insert(0, enrich("req-x1", ["r15"], "initial"))
    check(
        "a1_iv_initial_then_resume_id_not_in_before",
        s,
        "r15 first call initial, second resume, not in before",
    )


# A2 ------------------------------------------------------------------
@case
def a2_i_two_models_two_configs_both_initial():
    s = build()
    s["records"]["r01"]["label_config"] = "LC2-strong"
    s["calls"].append(
        enrich("req-x1", ["r01"], "initial", lc="LC2-strong", model="strong-model")
    )
    check(
        "a2_i_two_models_two_configs_both_initial",
        s,
        "r01 record=LC2; calls LC1 (batch) + LC2",
    )


@case
def a2_ii_two_models_two_configs_both_resume():
    s = build()
    s["records"]["r15"]["label_config"] = "LC2-strong"
    s["calls"].append(
        enrich("req-x1", ["r15"], "resume", lc="LC2-strong", model="strong-model")
    )
    check(
        "a2_ii_two_models_two_configs_both_resume",
        s,
        "r15 (not in before) record=LC2; calls LC1 + LC2",
    )


@case
def a2_iii_two_configs_second_in_resume_id_in_before():
    s = build()
    s["records"]["r01"]["label_config"] = "LC2-strong"
    s["calls"].append(
        enrich("req-x1", ["r01"], "resume", lc="LC2-strong", model="strong-model")
    )
    check(
        "a2_iii_two_configs_second_in_resume_id_in_before",
        s,
        "r01 in before; LC1 initial then LC2 resume",
    )


@case
def a2_iv_whole_batch_relabelled():
    s = build()
    b = s["batches"][2]  # r15,r16,r18,r19,r21 (session 2, no cached copies)
    for rid in b:
        s["records"][rid]["label_config"] = "LC2-strong"
    s["calls"].append(
        enrich("req-x1", b, "resume", lc="LC2-strong", model="strong-model")
    )
    check(
        "a2_iv_whole_batch_relabelled",
        s,
        "5 IDs relabelled under LC2; one flag per ID expected",
    )


# A3 ------------------------------------------------------------------
@case
def a3_i_shared_config_models_differ_initial():
    s = build(lc="two-stage-v1:small-then-strong")
    s["calls"].append(
        enrich(
            "req-x1",
            ["r01"],
            "initial",
            lc="two-stage-v1:small-then-strong",
            model="strong-model",
        )
    )
    check(
        "a3_i_shared_config_models_differ_initial",
        s,
        "r01: small + strong calls, one shared LC, both initial",
    )


@case
def a3_ii_shared_config_models_differ_resume():
    s = build(lc="two-stage-v1:small-then-strong")
    s["calls"].append(
        enrich(
            "req-x1",
            ["r15"],
            "resume",
            lc="two-stage-v1:small-then-strong",
            model="strong-model",
        )
    )
    check(
        "a3_ii_shared_config_models_differ_resume",
        s,
        "r15 (not in before): both calls resume, shared LC",
    )


@case
def a3_iii_shared_config_second_resume_id_in_before():
    s = build(lc="two-stage-v1:small-then-strong")
    s["calls"].append(
        enrich(
            "req-x1",
            ["r01"],
            "resume",
            lc="two-stage-v1:small-then-strong",
            model="strong-model",
        )
    )
    check(
        "a3_iii_shared_config_second_resume_id_in_before",
        s,
        "r01 in before; strong call phase resume, shared LC",
    )


# A4 ------------------------------------------------------------------
@case
def a4_i_five_sessions():
    s = build(sessions=5)
    phases = [c["phase"] for c in s["calls"] if c["role"] == "enrich"]
    check(
        "a4_i_five_sessions",
        s,
        f"phases={phases}; before={s['before']}; after=all {len(s['after'])} completed",
    )


@case
def a4_ii_five_sessions_after_is_partial():
    s = build(sessions=5)
    s["after"] = s["before"] + s["batches"][1]
    check(
        "a4_ii_five_sessions_after_is_partial",
        s,
        "after = end of session 2 only (subset of completed)",
    )


# A5 ------------------------------------------------------------------
@case
def a5_i_relabel_in_resume_shared_config():
    s = build(sessions=5, lc="two-stage-v1")
    s["calls"].append(
        enrich("req-x1", ["r01"], "resume", lc="two-stage-v1", model="strong-model")
    )
    check(
        "a5_i_relabel_in_resume_shared_config",
        s,
        "5 sessions; strong-model resume call for r01 (in before), shared LC",
    )


@case
def a5_ii_relabel_in_resume_distinct_config():
    s = build(sessions=5)
    s["records"]["r01"]["label_config"] = "LC2-strong"
    s["calls"].append(
        enrich("req-x1", ["r01"], "resume", lc="LC2-strong", model="strong-model")
    )
    check(
        "a5_ii_relabel_in_resume_distinct_config",
        s,
        "5 sessions; r01 in before; LC2 resume call; record=LC2",
    )


@case
def a5_iii_same_call_but_phase_string_initial():
    s = build(sessions=5, lc="two-stage-v1")
    s["calls"].append(
        enrich("req-x1", ["r01"], "initial", lc="two-stage-v1", model="strong-model")
    )
    check(
        "a5_iii_same_call_but_phase_string_initial",
        s,
        "identical to a5_i except phase string = initial",
    )


@case
def a5_iv_relabel_in_resume_id_not_in_before():
    s = build(sessions=5, lc="two-stage-v1")
    s["calls"].append(
        enrich("req-x1", ["r15"], "resume", lc="two-stage-v1", model="strong-model")
    )
    check(
        "a5_iv_relabel_in_resume_id_not_in_before",
        s,
        "5 sessions; strong resume call for r15 (NOT in before)",
    )


# A6 ------------------------------------------------------------------
@case
def a6_a_original_not_first_in_file():
    s = build(original="last")
    cached = {
        rid: r["cache_source_id"]
        for rid, r in s["records"].items()
        if r.get("cache_source_id")
    }
    check("a6_a_original_not_first_in_file", s, f"cache map={cached}")


@case
def a6_b_cached_copies_in_before():
    s = build()
    s["before"] += ["r09", "r14", "r27", "r11", "r20", "r25"]
    check(
        "a6_b_cached_copies_in_before",
        s,
        "6 cached copies (originals r02,r03,r04 are initial) added to before",
    )


@case
def a6_c_copy_in_before_original_done_in_resume():
    s = build(original="last")
    orig = s["records"]["r02"]["cache_source_id"]
    phase = next(
        c["phase"]
        for c in s["calls"]
        if c["role"] == "enrich" and orig in c["review_ids"]
    )
    s["before"] += ["r02"]
    check(
        "a6_c_copy_in_before_original_done_in_resume",
        s,
        f"r02 cached from {orig} (call phase={phase}, in before={orig in s['before']})",
    )


@case
def a6_d_chain_of_aliases():
    s = build()
    s["records"]["r14"]["cache_source_id"] = "r09"  # r09 is itself a copy of r02
    check("a6_d_chain_of_aliases", s, "r14 -> r09 -> r02")


@case
def a6_e_copy_of_original_without_call():
    s = build()
    b = call_with(s, "req-enrich-001")
    b["review_ids"].remove("r02")
    b["input_tokens"], b["output_tokens"] = 800, 480
    s["before"].remove("r02")
    check(
        "a6_e_copy_of_original_without_call",
        s,
        "original r02 has no enrich call; copies r09,r14,r27 remain",
    )


# A7 ------------------------------------------------------------------
@case
def a7_i_dev_calls_same_config():
    s = build()
    s["calls"].insert(
        0, enrich("dev-001", ["r01", "r02", "r03", "r04", "r06"], "initial")
    )
    s["calls"].insert(1, enrich("dev-002", ["r15", "r16", "r18"], "initial"))
    check(
        "a7_i_dev_calls_same_config",
        s,
        "dev calls phase initial, LC1; IDs in before and not in before",
    )


@case
def a7_ii_dev_calls_same_config_incl_copy_and_empty():
    s = build()
    s["calls"].insert(0, enrich("dev-001", ["r01", "r09", "r05", "r22"], "initial"))
    check(
        "a7_ii_dev_calls_same_config_incl_copy_and_empty",
        s,
        "dev call lists cached copy r09, empty r05, resume-completed r22",
    )


@case
def a7_iii_dev_calls_different_config():
    s = build()
    s["calls"].insert(
        0,
        enrich("dev-001", ["r01", "r02", "r03", "r04", "r06"], "initial", lc="LC-dev"),
    )
    s["calls"].insert(
        1, enrich("dev-002", ["r15", "r16", "r18"], "initial", lc="LC-dev")
    )
    check(
        "a7_iii_dev_calls_different_config",
        s,
        "same as a7_i but dev label_config=LC-dev (8 IDs)",
    )


@case
def a7_iv_dev_calls_phase_resume():
    s = build()
    s["calls"].insert(
        0, enrich("dev-001", ["r01", "r02", "r03", "r04", "r06"], "resume")
    )
    check("a7_iv_dev_calls_phase_resume", s, "dev call marked resume, lists before IDs")


@case
def a7_v_dev_calls_phase_dev():
    s = build()
    s["calls"].insert(0, enrich("dev-001", ["r01", "r02"], "dev"))
    check("a7_v_dev_calls_phase_dev", s, "dev call with phase='dev'")


# A8 ------------------------------------------------------------------
@case
def a8_i_empty_ids_int_tokens():
    s = build()
    non = [
        (c["role"], c["review_ids"], c["input_tokens"], c["output_tokens"])
        for c in s["calls"]
        if c["role"] != "enrich"
    ]
    check("a8_i_empty_ids_int_tokens", s, f"baseline non-enrich calls={non}")


@case
def a8_ii_verify_real_ids_other_config():
    s = build()
    v = call_with(s, "req-verify-001")
    v["review_ids"] = ["r01", "r15", "r10"]
    v["label_config"] = "verify-cfg-v2"
    check(
        "a8_ii_verify_real_ids_other_config",
        s,
        "verify lists r01,r15,r10 with label_config=verify-cfg-v2",
    )


@case
def a8_iii_verify_all_ids_phase_resume():
    s = build()
    v = call_with(s, "req-verify-001")
    v["review_ids"] = [r[0] for r in ROWS]
    v["label_config"] = "verify-cfg-v2"
    v["phase"] = "resume"
    v["model"] = "strong-model"
    check(
        "a8_iii_verify_all_ids_phase_resume",
        s,
        "verify lists all 30 IDs (incl. before IDs), phase resume, other LC",
    )


@case
def a8_iv_non_enrich_zero_tokens():
    s = build()
    for role in ("verify", "group", "memo"):
        c = call_with(s, f"req-{role}-001")
        c["input_tokens"] = c["output_tokens"] = 0
    check("a8_iv_non_enrich_zero_tokens", s, "verify/group/memo tokens = 0")


# A9 ------------------------------------------------------------------
@case
def a9_i_local_request_id():
    s = build()
    call_with(s, "req-enrich-001")["request_id"] = "local-lmstudio-7f3c2a9e-0001"
    call_with(s, "req-enrich-004")["request_id"] = "x"
    check(
        "a9_i_local_request_id",
        s,
        "request_ids replaced by local strings ('local-lmstudio-...', 'x')",
    )


@case
def a9_ii_tokens_missing():
    s = build()
    c = call_with(s, "req-enrich-001")
    del c["input_tokens"], c["output_tokens"]
    check("a9_ii_tokens_missing", s, "one enrich call without token fields")


@case
def a9_iii_tokens_null():
    s = build()
    c = call_with(s, "req-enrich-001")
    c["input_tokens"] = c["output_tokens"] = None
    check("a9_iii_tokens_null", s, "one enrich call with null tokens")


@case
def a9_iv_tokens_null_on_memo():
    s = build()
    call_with(s, "req-memo-001")["output_tokens"] = None
    check("a9_iv_tokens_null_on_memo", s, "memo call output_tokens null")


@case
def a9_v_tokens_float():
    s = build()
    call_with(s, "req-enrich-001")["input_tokens"] = 1000.0
    check("a9_v_tokens_float", s, "input_tokens 1000.0 (float)")


@case
def a9_vi_request_id_missing():
    s = build()
    call_with(s, "req-enrich-001")["request_id"] = None
    check("a9_vi_request_id_missing", s, "request_id null")


# A10 -----------------------------------------------------------------
@case
def a10_i_nonempty_quarantined_clean():
    s = build()
    rec = s["records"]["r22"]
    s["records"]["r22"] = dict(
        review_id="r22",
        source_sha256=rec["source_sha256"],
        status="quarantined",
        reason="invalid_model_output_after_3_retries",
    )
    s["after"].remove("r22")
    b = call_with(s, "req-enrich-004")
    b["review_ids"].remove("r22")
    b["input_tokens"], b["output_tokens"] = 800, 480
    s["calls"].append(
        enrich("req-x1", ["r22"], "resume", outcome="failed", tin=200, tout=0)
    )
    check(
        "a10_i_nonempty_quarantined_clean",
        s,
        "r22 (praise, not in checkpoints/membership) quarantined with reason; failed call logged",
    )


@case
def a10_ii_nonempty_quarantined_left_in_after():
    s = build()
    rec = s["records"]["r22"]
    s["records"]["r22"] = dict(
        review_id="r22",
        source_sha256=rec["source_sha256"],
        status="quarantined",
        reason="invalid_model_output_after_3_retries",
    )
    check(
        "a10_ii_nonempty_quarantined_left_in_after",
        s,
        "same, but r22 still listed in checkpoint_after",
    )


# A11 -----------------------------------------------------------------
@case
def a11_i_sentiment_int():
    s = build()
    s["records"]["r16"]["sentiment"] = 0
    s["records"]["r22"]["sentiment"] = 1
    s["records"]["r01"]["sentiment"] = -1
    check("a11_i_sentiment_int", s, "sentiment ints: r16=0, r22=1, r01=-1")


@case
def a11_ii_entities_empty():
    s = build()
    for r in s["records"].values():
        if r["status"] == "completed":
            r["entities"] = []
    check("a11_ii_entities_empty", s, "entities=[] on all 27 completed records")


@case
def a11_iii_quote_is_whole_text():
    s = build()
    text = {r[0]: r[1] for r in ROWS}
    for rid, r in s["records"].items():
        if r["status"] == "completed":
            r["evidence_quote"] = text[rid]
    check(
        "a11_iii_quote_is_whole_text",
        s,
        "evidence_quote = entire review_text on all completed (r08 keeps its spaces)",
    )


@case
def a11_iv_quote_trimmed():
    s = build()
    s["records"]["r08"]["evidence_quote"] = "Love the playlists"
    check(
        "a11_iv_quote_trimmed",
        s,
        "r08 text='  Love the playlists  ', quote=trimmed text",
    )


@case
def a11_v_all_combined():
    s = build()
    text = {r[0]: r[1] for r in ROWS}
    for rid, r in s["records"].items():
        if r["status"] == "completed":
            r["entities"] = []
            r["evidence_quote"] = text[rid].strip()
            r["sentiment"] = 1 if r["sentiment"] > 0 else 0
    check(
        "a11_v_all_combined",
        s,
        "int sentiment 0/1 + entities [] + quote=trimmed whole text, all records",
    )


@case
def a11_vi_sentiment_bool():
    s = build()
    s["records"]["r22"]["sentiment"] = True
    check("a11_vi_sentiment_bool", s, "sentiment true (JSON bool)")


@case
def a11_vii_quote_case_changed():
    s = build()
    s["records"]["r01"]["evidence_quote"] = "app crashes every time"
    check("a11_vii_quote_case_changed", s, "quote differs from source only by case")


@case
def a11_viii_quote_whitespace_collapsed():
    s = build()
    s["records"]["r08"]["evidence_quote"] = " Love the playlists "
    s["records"]["r01"]["evidence_quote"] = "crashes  every time"
    check(
        "a11_viii_quote_whitespace_collapsed",
        s,
        "r01 quote has doubled space; r08 quote has single surrounding spaces (still a substring)",
    )


# A12 -----------------------------------------------------------------
@case
def a12_i_failed_initial_ids_in_before():
    s = build()
    s["calls"].insert(
        0,
        enrich(
            "req-f1",
            ["r01", "r02", "r03"],
            "initial",
            outcome="failed",
            tin=600,
            tout=0,
        ),
    )
    check(
        "a12_i_failed_initial_ids_in_before",
        s,
        "failed initial call lists r01,r02,r03 (in before), later succeeded",
    )


@case
def a12_ii_failed_resume_ids_not_in_before():
    s = build()
    s["calls"].append(
        enrich("req-f1", ["r15", "r16"], "resume", outcome="failed", tin=400, tout=0)
    )
    check(
        "a12_ii_failed_resume_ids_not_in_before",
        s,
        "failed resume call lists r15,r16 (not in before)",
    )


@case
def a12_iii_failed_resume_ids_in_before():
    s = build()
    s["calls"].append(
        enrich("req-f1", ["r01"], "resume", outcome="failed", tin=200, tout=0)
    )
    check(
        "a12_iii_failed_resume_ids_in_before",
        s,
        "failed resume call lists r01 (in before)",
    )


@case
def a12_iv_failed_call_no_usage():
    s = build()
    s["calls"].insert(
        0, enrich("req-f1", ["r01", "r02", "r03"], "initial", outcome="failed")
    )
    s["calls"][0]["input_tokens"] = s["calls"][0]["output_tokens"] = None
    check("a12_iv_failed_call_no_usage", s, "failed initial call with null usage")


@case
def a12_v_failed_call_other_config():
    s = build()
    s["calls"].insert(
        0,
        enrich(
            "req-f1",
            ["r01", "r02", "r03"],
            "initial",
            outcome="failed",
            lc="LC-other",
            tin=600,
            tout=0,
        ),
    )
    check(
        "a12_v_failed_call_other_config",
        s,
        "failed initial call with a different label_config",
    )


# Other traps ----------------------------------------------------------
@case
def t1_quarantined_ids_in_checkpoints():
    s = build()
    s["before"] += ["r05"]
    s["after"] += ["r05", "r17", "r23"]
    check(
        "t1_quarantined_ids_in_checkpoints",
        s,
        "empty-text quarantined IDs listed in completed_ids",
    )


@case
def t2_retry_reuses_request_id():
    s = build()
    s["calls"].insert(
        0,
        enrich(
            "req-enrich-001",
            s["batches"][0],
            "initial",
            outcome="failed",
            tin=1000,
            tout=0,
        ),
    )
    check(
        "t2_retry_reuses_request_id", s, "failed attempt and its retry share request_id"
    )


@case
def t3_call_lists_id_not_in_file():
    s = build()
    call_with(s, "req-enrich-003")["review_ids"].append("golden-0001")
    check(
        "t3_call_lists_id_not_in_file",
        s,
        "one succeeded batch also lists an ID absent from the input",
    )


@case
def t4_whitespace_row_other_reason():
    s = build()
    s["records"]["r23"]["reason"] = "whitespace_only"
    check(
        "t4_whitespace_row_other_reason",
        s,
        "whitespace-only row quarantined with reason 'whitespace_only'",
    )


@case
def t5_resume_completes_only_cached_copies():
    s = build()
    # every original is called in initial; the only IDs added after the checkpoint are cached copies
    for c in s["calls"]:
        if c["role"] == "enrich":
            c["phase"] = "initial"
    s["before"] = list(s["originals"])
    check(
        "t5_resume_completes_only_cached_copies",
        s,
        "all enrich calls initial; after-before = cached copies only",
    )


@case
def t6_cache_source_text_not_identical():
    s = build()
    # r22 points at r08 with identical label fields but a different source text
    for k in (
        "topic",
        "intent",
        "sentiment",
        "severity",
        "entities",
        "evidence_quote",
        "needs_review",
        "label_config",
    ):
        s["records"]["r22"][k] = copy.deepcopy(s["records"]["r08"][k])
    s["records"]["r22"]["evidence_quote"] = s["records"]["r08"]["evidence_quote"] = "e"
    s["records"]["r22"]["cache_source_id"] = "r08"
    check(
        "t6_cache_source_text_not_identical",
        s,
        "r22 cached from r08: identical labels, non-identical text",
    )


@case
def t7_enrich_call_without_phase_when_failed():
    s = build()
    c = enrich("req-f1", ["r01"], "initial", outcome="failed", tin=200, tout=0)
    del c["phase"]
    s["calls"].insert(0, c)
    check(
        "t7_enrich_call_without_phase_when_failed",
        s,
        "failed enrich call with no phase field",
    )


@case
def t8_before_id_original_relabelled_copies_follow():
    s = build()
    for rid in ("r02", "r09", "r14", "r27"):
        s["records"][rid]["label_config"] = "LC2-strong"
    s["calls"].append(
        enrich("req-x1", ["r02"], "resume", lc="LC2-strong", model="strong-model")
    )
    check(
        "t8_before_id_original_relabelled_copies_follow",
        s,
        "original r02 (in before) relabelled in resume under LC2; copies updated",
    )


@case
def a4_iii_five_sessions_cached_copies_in_before():
    s = build(sessions=5)
    s["before"] += ["r09", "r14", "r27", "r11", "r20", "r25"]
    check(
        "a4_iii_five_sessions_cached_copies_in_before",
        s,
        "5 sessions; before also lists cached copies of session-1 originals",
    )


@case
def a4_iv_five_sessions_checkpoints_list_quarantined():
    s = build(sessions=5)
    s["before"] += ["r05"]
    s["after"] += ["r05", "r17", "r23"]
    check(
        "a4_iv_five_sessions_checkpoints_list_quarantined",
        s,
        "5 sessions; checkpoints also list quarantined empty-text IDs",
    )


@case
def a4_v_five_sessions_session2_marked_initial():
    s = build(sessions=5)
    s["calls"][1]["phase"] = "initial"
    check(
        "a4_v_five_sessions_session2_marked_initial",
        s,
        "5 sessions; session-2 batch marked initial though its IDs are not in before",
    )


@case
def a4_vi_five_sessions_session1_marked_resume():
    s = build(sessions=5)
    s["calls"][0]["phase"] = "resume"
    check(
        "a4_vi_five_sessions_session1_marked_resume",
        s,
        "5 sessions; the session-1 batch marked resume",
    )


@case
def t9_memo_call_without_review_ids_key():
    s = build()
    del call_with(s, "req-memo-001")["review_ids"]
    check(
        "t9_memo_call_without_review_ids_key",
        s,
        "memo call omits review_ids instead of sending []",
    )


@case
def t10_one_bad_quote_on_praise_not_in_before():
    s = build()
    s["records"]["r22"]["evidence_quote"] = "best music app"
    check(
        "t10_one_bad_quote_on_praise_not_in_before",
        s,
        "r22 (praise, session 2) quote differs by case only",
    )


@case
def t11_first_model_call_logged_failed_then_second_config():
    s = build()
    b = s["batches"][2]
    for rid in b:
        s["records"][rid]["label_config"] = "LC2-strong"
    call_with(s, "req-enrich-003")["outcome"] = "failed"
    s["calls"].append(
        enrich("req-x1", b, "resume", lc="LC2-strong", model="strong-model")
    )
    check(
        "t11_first_model_call_logged_failed_then_second_config",
        s,
        "as a2_iv, but the LC1 call has outcome=failed",
    )


if __name__ == "__main__":
    setup()
    wanted = sys.argv[1:]
    for name, fn in CASES.items():
        if not wanted or any(name.startswith(w) for w in wanted):
            fn()
    (SCRATCH / "results.json").write_text(
        json.dumps(
            [
                dict(case=n, status=st, issue_counts=ic, note=note)
                for n, st, ic, note in RESULTS
            ],
            indent=2,
        )
    )
