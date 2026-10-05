"""THROWAWAY check, not pipeline code. No network, no model call.

Rebuilds the second independent reviewer's four checker claims from scratch, without
looking at the reviewer's own test code: a small made-up input, a small export that
follows the spec's rules, and the instructor's checker run on each variant.
Everything is written to a temporary folder outside the repository.
"""
import csv, importlib.util, json, shutil, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(tempfile.mkdtemp(prefix="checker-claims-"))
CHECKER = ROOT / "feed/Final Assignment - Spotify Reviews Dataset/check_submission.py"
spec = importlib.util.spec_from_file_location("chk", CHECKER)
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

FIELDS = list(chk.FIELDS)
ROWS = [
    ("a", "Music will not play."), ("b", "I cannot sign in."), ("c", "Music will not play."),
    ("d", "   "), ("e", "Great app."), ("f", "Songs stop after an update."),
]
src = HERE / "input.csv"
with open(src, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(FIELDS)
    for i, (rid, text) in enumerate(ROWS):
        w.writerow([rid, text, "1", "0", "", f"2023-01-0{i + 1} 00:00:00"])
ref = chk.reference(src, src)
sha = {rid: v["source_sha256"] for rid, v in ref["rows"].items()}
LC = "jev-x/prompt-v1/schema-v1/cut-0.70"

def rec(rid, topic, intent, sev, quote, **extra):
    return {"review_id": rid, "source_sha256": sha[rid], "status": "completed", "topic": topic, "intent": intent,
            "sentiment": -0.5 if intent != "praise" else 0.5, "severity": sev, "entities": [], "evidence_quote": quote,
            "needs_review": False, "label_config": LC, **extra}

def call(n, role, ids, phase=None, outcome="succeeded", **extra):
    c = {"request_id": f"r{n}", "role": role, "review_ids": ids, "model": "m", "outcome": outcome,
         "label_config": LC, "input_tokens": 10, "output_tokens": 5, **extra}
    if phase:
        c["phase"] = phase
    return c

def base():
    return {
        "records": [rec("a", "playback", "complaint", 4, "Music will not play."), rec("b", "access", "complaint", 4, "I cannot sign in."),
                    rec("c", "playback", "complaint", 4, "Music will not play.", cache_source_id="a"),
                    {"review_id": "d", "source_sha256": sha["d"], "status": "quarantined", "reason": "empty_review_text"},
                    rec("e", "other", "praise", 1, "Great app."), rec("f", "playback", "complaint", 3, "Songs stop after an update.")],
        "calls": [call(1, "enrich", ["a"], "initial"), call(2, "enrich", ["b"], "initial"), call(3, "enrich", ["e"], "resume"),
                  call(4, "enrich", ["f"], "resume"), call(5, "verify", ["a"]), call(6, "group", ["a", "b"]), call(7, "memo", [])],
        "before": ["a", "b", "c"], "after": ["a", "b", "c", "e", "f"],
        "claims": [("C1", "issue-playback", "complaint_count", None)],
    }

def write(folder, st):
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    chk.write_json(folder / "run.json", {"version": chk.VERSION, "analysis_count": len(ref["rows"]), "analysis_sha256": ref["analysis_sha256"],
                                         "classification_input_fields": ["review_text"], "allow_multi_issue": False})
    chk.write_json(folder / "ingestion.json", ref["ingestion"])
    (folder / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in st["records"]), encoding="utf-8")
    (folder / "calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in st["calls"]), encoding="utf-8")
    chk.write_json(folder / "checkpoint_before.json", {"completed_ids": st["before"]})
    chk.write_json(folder / "checkpoint_after.json", {"completed_ids": st["after"]})
    done = {r["review_id"]: r for r in st["records"] if r["status"] == "completed" and r["intent"] in ("complaint", "cancellation")}
    issues = {}
    for rid, r in done.items():
        issues.setdefault("issue-" + r["topic"], []).append(r["severity"])
    rows = sorted(({"issue_id": k, "complaint_count": len(v), "severity_sum": sum(v), "mean_severity": chk.mean_string(sum(v), len(v)),
                    "priority_score": sum(v)} for k, v in issues.items()), key=lambda x: (-x["priority_score"], x["issue_id"]))
    with open(folder / "membership.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(["issue_id", "review_id"])
        for rid, r in done.items():
            w.writerow(["issue-" + r["topic"], rid])
    with open(folder / "ranking.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"])
        for i, x in enumerate(rows, 1):
            w.writerow([i, x["issue_id"], x["complaint_count"], x["severity_sum"], x["mean_severity"], x["priority_score"]])
    by = {x["issue_id"]: x for x in rows}
    with open(folder / "claims.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(["claim_id", "issue_id", "metric", "value"])
        for cid, iid, metric, _ in st["claims"]:
            if iid in by:
                w.writerow([cid, iid, metric, by[iid][metric]])

def run(name, st):
    folder = HERE / "export"
    write(folder, st)
    out = chk.audit(folder, ref)
    print(f"{name:52s} status {out['status']:16s} flags {out['issue_counts'] or '{}'}  coverage {out['working_coverage_point_candidate']}")
    return out

c = run("0 control (stop with an original pending)", base())
assert c["status"] == "pass", c["examples"]

s = base()  # 1: every original done before the stop; only the copy finishes after it
s["calls"] = [call(1, "enrich", ["a"], "initial"), call(2, "enrich", ["b"], "initial"), call(3, "enrich", ["e"], "initial"),
              call(4, "enrich", ["f"], "initial"), call(5, "verify", ["a"]), call(6, "group", ["a", "b"]), call(7, "memo", [])]
s["before"], s["after"] = ["a", "b", "e", "f"], ["a", "b", "c", "e", "f"]
run("1 resume finishes only a copy", s)

s = base()  # 1b: originals pending at the stop, but the pending one ends quarantined
s["records"][5] = {"review_id": "f", "source_sha256": sha["f"], "status": "quarantined", "reason": "invalid_model_output"}
s["records"][4] = rec("e", "other", "praise", 1, "Great app.")
s["calls"] = [call(1, "enrich", ["a"], "initial"), call(2, "enrich", ["b"], "initial"), call(3, "enrich", ["e"], "initial"),
              call(4, "enrich", ["f"], "resume", outcome="failed"), call(5, "verify", ["a"]), call(6, "group", ["a", "b"]), call(7, "memo", [])]
s["before"], s["after"] = ["a", "b", "e"], ["a", "b", "c", "e"]
run("1b pending original at the stop ends quarantined", s)

s = base()  # 2: a failed attempt with no token counts
bad = call(8, "enrich", ["f"], "resume", outcome="failed"); del bad["input_tokens"], bad["output_tokens"]
s["calls"].insert(3, bad)
run("2 failed attempt, token counts left out", s)
s = base()
s["calls"].insert(3, call(8, "enrich", ["f"], "resume", outcome="failed", input_tokens=0, output_tokens=0, usage_known=False))
o = run("2b failed attempt, zeros plus usage_known false", s)
print(f"{'':52s} checker's token totals: in {o['reported_input_tokens']} out {o['reported_output_tokens']} (the marker field is ignored)")

s = base()  # 3: a nonempty review left quarantined
s["records"][5] = {"review_id": "f", "source_sha256": sha["f"], "status": "quarantined", "reason": "invalid_model_output"}
s["calls"][3] = call(4, "enrich", ["f"], "resume", outcome="failed")
s["after"] = ["a", "b", "c", "e"]
run("3 one nonempty review quarantined", s)

s = base()  # 4: an input whose reviews are all praise
s["records"] = [rec(r, "other", "praise", 1, t.strip()) if t.strip() else {"review_id": r, "source_sha256": sha[r], "status": "quarantined", "reason": "empty_review_text"} for r, t in ROWS]
s["records"][2]["cache_source_id"] = "a"
s["calls"] = [call(1, "enrich", ["a"], "initial"), call(2, "enrich", ["b"], "initial"), call(3, "enrich", ["e"], "resume"),
              call(4, "enrich", ["f"], "resume"), call(5, "verify", ["a"]), call(7, "memo", [])]
s["claims"] = []
run("4 no complaints, no naming call", s)
s["calls"].append(call(6, "group", []))
run("4b no complaints, but a naming call is logged", s)
