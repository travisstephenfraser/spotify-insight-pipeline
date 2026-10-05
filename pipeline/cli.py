"""The command line: run the stages in order, look at a run, export it, rebuild the ranking.

  python3 -m pipeline run --run NAME --new --input PATH.csv     start a run
  python3 -m pipeline run --run NAME                            resume it; the same command each time
  python3 -m pipeline status --run NAME
  python3 -m pipeline export --run NAME
  python3 -m pipeline rank                                      ranking from committed files, no model

A run that calls real models starts only with --go. --standin runs every stage with the
stand-ins, with no network and no cost.
"""

import argparse
import json
import os
import re
import signal
import sys
import threading
from decimal import Decimal
from pathlib import Path

from pipeline import classify, export, gemma, group, hashing, jev, ledger, limits, memo, prepare, rank, standins, state, verify

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runs/state.sqlite"
STANDIN_STATE = ROOT / "runs/standin.sqlite"  # stand-in runs never share the ledger that guards real money
CHECKER = ROOT / "feed/Final Assignment - Spotify Reviews Dataset/check_submission.py"
PROBE_ANSWERS = ROOT / "experiments/2026-10-04/tool-choice/simple.jsonl"
SEED = "berkeley-fall-2026-assignment-5-v1"  # manifest.json, samples.seed
VERIFY_SEED, SAMPLE_SEED = "verify-v1", "sample-v1"
USD_PER_REVIEW = Decimal("0.000039")  # $0.0039 per 100 pilot reviews, measured on 2026-10-04
OPENING_SPEND = (Decimal("0.0485"), Decimal("0.005"))  # Jev probes before the ledger existed: measured, estimated
OK, FAILED_CHECK, REFUSED, NOT_FINISHED, GUARD = 0, 1, 2, 3, 4


class Refused(Exception):
    """The command cannot go ahead as asked. The message says why and what to do."""


def _env_key(name):
    """A key from the environment, or from .env beside the code. Its value is never printed."""
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(rf"\s*(?:export\s+)?{name}\s*=\s*(.+)$", line)
            if m and m.group(1).strip().strip("'\""):
                return m.group(1).strip().strip("'\"")
    raise Refused(f"{name} is not set in the environment or in .env")


def _is_standin(row):
    return bool(json.loads(row["configs_json"]).get("standin"))


def _one_kind_per_state_file(db, standin):
    """Stand-in charges are made up. They must never sit in the ledger that guards real money."""
    for row in db.execute("SELECT * FROM runs"):
        if _is_standin(row) != standin:
            other = "stand-in" if _is_standin(row) else "real"
            raise Refused(f"this state file already holds a {other} run ({row['run']}); use another --state for this one")


def _clients(a, real):
    if not real:
        answers = PROBE_ANSWERS if PROBE_ANSWERS.exists() else None
        return (
            standins.ReplayJev(answers, latency=a.standin_latency, log_path=a.standin_log),
            standins.StandinGemma(log_path=a.standin_log),
            limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9),
        )
    return jev.Client(_env_key("TYPESAFE_API_KEY")), gemma.Client(), limits.Limiter(requests_per_second=75, tokens_per_second=100_000)


def _would_spend(db, a, requests):
    led = ledger.Ledger(db, a.billing, cap_usd=Decimal(a.cap))
    print(f"This would send about {requests} requests to Jev, one for each distinct text not yet labeled.")
    print(f"Cost: about ${requests * USD_PER_REVIEW:.4f} (estimate, from $0.0039 per 100 reviews measured on the pilot).")
    print(f"Spent so far: ${led.spent_usd():.4f} of the ${a.cap} cap.")
    print("Nothing was started. Add --go to run it.")
    return OK


def _warm_source(db, a, setup, input_sha):
    """The finished run a warm pass copies from, checked to be the same setup in every respect."""
    try:
        source = state.load_run(db, a.warm_from)
    except state.NoSuchRun:
        raise Refused(f"there is no run named {a.warm_from} to take results from") from None
    unfinished = db.execute("SELECT 1 FROM reviews WHERE run=? AND status='pending' LIMIT 1", (a.warm_from,)).fetchone()
    members = db.execute("SELECT 1 FROM membership WHERE run=? LIMIT 1", (a.warm_from,)).fetchone()
    if unfinished or (members and memo.final(db, a.warm_from) is None):
        raise Refused(f"run {a.warm_from} is not finished, so there is nothing whole to take")
    saved, now = json.loads(source["hashes_json"]), setup.hashes()
    differs = sorted(k for k in saved.keys() | now.keys() if saved.get(k) != now.get(k))
    differs += [name for name, same in (("input", source["input_sha256"] == input_sha), ("verify size", source["verify_size"] == a.verify_size), ("seed", source["seed"] == a.seed)) if not same]
    if differs:
        raise Refused(f"a warm pass needs the same setup as run {a.warm_from}; this differs: {', '.join(differs)}")
    return source


def _warm(db, a, gemma_client):
    """The cost pilot's warm pass: take every result from a finished run and make no call of any role."""
    import time

    clock, run, source = time.monotonic, a.run, a.warm_from
    session = state.open_session(db, run, "classify", 1, clock)
    with state.tx(db):
        db.execute(
            "INSERT INTO results SELECT ?, text_key, topic, intent, severity, sentiment, entities_json, evidence_quote, "
            "needs_review, min_top_probability, raw_json, model FROM results WHERE run=?",
            (run, source),
        )
        db.execute(
            "UPDATE reviews SET status=s.status, reason=s.reason, completed_session=CASE WHEN s.status='completed' THEN ? END "
            "FROM (SELECT review_id, status, reason FROM reviews WHERE run=?) AS s WHERE reviews.run=? AND reviews.review_id=s.review_id",
            (session, source, run),
        )
    state.close_session(db, session, "finished", clock)
    session = state.open_session(db, run, "verify", 1, clock)
    db.execute(
        "INSERT INTO verify SELECT ?, review_id, outcome, topic, intent, severity, reason, NULL FROM verify WHERE run=?", (run, source)
    )
    state.close_session(db, session, "finished", clock)
    group.assign(db, run)
    named = group.name_issues(db, run, gemma_client, warm_from=source)
    if named.ended_how == "finished":
        session = state.open_session(db, run, "memo", 1, clock)
        memo.write(db, run, gemma_client, warm_from=source)
        state.close_session(db, session, "finished", clock)
    elif named.ended_how != "no_complaints":
        print(f"warm pass: naming did not finish ({named.ended_how}). {named.message} This is not a clean warm pass.")
        return NOT_FINISHED
    calls = db.execute("SELECT COUNT(*) FROM calls WHERE run=?", (run,)).fetchone()[0]
    db.execute(
        "INSERT OR REPLACE INTO artifacts (key, run, role, input_json, output_json, model, created_utc) VALUES (?,?,?,?,?,?,?)",
        (f"warm:{run}", run, "warm", source, json.dumps({"calls_made": calls, "source_run": source}), "none", state.now_utc()),
    )
    if calls:
        print(f"warm pass: {calls} calls were made, so something differs from run {source}. This is not a clean warm pass.")
        return NOT_FINISHED
    print(f"warm pass: 0 calls of any role; every result was taken from run {source}")
    return OK


def _stages(db, a, setup, labeler, gemma_client, limiter):
    stop = threading.Event()

    def on_interrupt(signum, frame):
        print("\nstopping: no new work, requests in flight will finish and be saved. Run the same command to resume.", flush=True)
        stop.set()

    try:
        signal.signal(signal.SIGINT, on_interrupt)
    except ValueError:  # not the main thread, as in a test
        pass
    cap = Decimal(a.cap)
    led = ledger.Ledger(db, a.billing, cap_usd=cap)
    if not a.standin and not db.execute("SELECT 1 FROM ledger WHERE kind='opening'").fetchone():
        led.opening(*OPENING_SPEND)
    guards = tuple(a.accept_guard or ())
    try:
        out = classify.run(
            db, a.run, labeler, ledger=led, limiter=limiter, setup=setup, workers=a.workers, max_hours=a.max_hours,
            stop_after=a.stop_after, stop_event=stop, accept_guards=guards,
        )  # fmt: skip
        print(
            f"classify: {out.ended_how}; completed {out.completed}, pending {out.pending}, quarantined {out.quarantined}; "
            f"spent ${led.spent_usd():.4f} of ${cap}"
        )
        if out.ended_how != "finished":
            if out.ended_how == "outage":
                print("Many requests in a row failed with no success between, so nothing new was sent. Check the network and the provider, then run the same command.")
            if out.stuck:
                print(f"{len(out.stuck)} review(s) kept failing and are still pending. See: python3 -m pipeline status --run {a.run}")
            return NOT_FINISHED
        checked = verify.run(db, a.run, gemma_client, max_hours=a.max_hours, stop_event=stop, accept_guards=guards)
        print(f"verify: {checked.ended_how}; predicted {checked.predicted}, failed {checked.failed}, left {checked.remaining}. {checked.message}".rstrip())
        if checked.ended_how != "finished":
            return NOT_FINISHED
        report = verify.report(db, a.run)
        agree = report["agreement"]
        print(
            f"verify report: sample {report['sample']}, predictions {report['predictions']}, verify failures {report['verify_failures']}, "
            f"not labeled by Jev {report['jev_unlabeled']}; all three fields agree on {agree['all_three']} of {agree['pairs']} pairs"
        )
    except classify.GuardFailed as e:
        print(f"stopped: {e}")
        return GUARD

    members = group.assign(db, a.run)
    named = group.name_issues(db, a.run, gemma_client)
    print(f"group: {named.ended_how}; {members} members, {named.named} named, {named.cached} reused, {named.fallbacks} fell back. {named.message}".rstrip())
    if named.ended_how == "no_complaints":
        print("No ranking and no memo for this input. The supplied checker cannot pass an input with no complaints.")
        return OK
    if named.ended_how != "finished":
        return NOT_FINISHED
    try:
        memo.write(db, a.run, gemma_client)
    except (memo.MemoFailed, gemma.ServerProblem) as e:
        print(f"memo: not written. {e}")
        return NOT_FINISHED
    print("memo: written and checked")
    print(f"All stages finished. Next: python3 -m pipeline export --run {a.run}")
    return OK


def cmd_run(db, a):
    real = not a.standin
    if not 1 <= a.workers <= classify.MAX_WORKERS:
        raise Refused(f"--workers takes 1 to {classify.MAX_WORKERS}: the design allows at most {classify.MAX_WORKERS} requests at once")
    commit, code_hash, _ = state.code_fingerprint(ROOT)
    exists = db.execute("SELECT 1 FROM runs WHERE run=?", (a.run,)).fetchone()
    if a.new:
        if exists:
            raise Refused(f"run {a.run} exists; drop --new to resume it")
        if not a.input:
            raise Refused("--new needs --input PATH.csv")
        setup = jev.load_setup(a.prompts, 0.70 if a.cutoff is None else a.cutoff, prompt_name=a.prompt_file or "enrich-v1.json")
        if real and not a.go:
            rows = prepare.read_rows(a.input)
            return _would_spend(db, a, len({r["review_text"] for r in rows if r["review_text"].strip()}))
        _one_kind_per_state_file(db, a.standin)
        input_sha = hashing.file_sha(a.input)
        if a.warm_from:
            _warm_source(db, a, setup, input_sha)
        if real:
            state.require_clean_tree(ROOT, real=True)
        labeler, gemma_client, limiter = _clients(a, real)
        with state.tx(db):
            state.create_run(
                db, a.run, input_path=str(Path(a.input).resolve()), input_sha256=input_sha, seed=a.seed,
                verify_seed=VERIFY_SEED, verify_size=a.verify_size, sample_seed=SAMPLE_SEED, code_commit=commit,
                code_hash=code_hash, label_config=setup.label_config, hashes=setup.hashes(),
                configs={"standin": a.standin, "warm_from": a.warm_from, "prompt_file": setup.prompt_file.name},
            )  # fmt: skip
            counts = prepare.prepare(db, a.run, a.input, seed=a.seed, verify_seed=VERIFY_SEED, verify_size=a.verify_size)
        print(
            f"prepared {counts['rows']} rows: {counts['empty']} empty, {counts['distinct_texts']} distinct texts, "
            f"{counts['copies']} copies, verify sample {counts['verify_sample']}"
            + ("" if counts["supplied_file"] else "; not the supplied file, so its known-count checks were skipped")
        )
        if a.warm_from:
            return _warm(db, a, gemma_client)
    else:
        row = state.load_run(db, a.run)
        if _is_standin(row) != a.standin:
            raise Refused(f"run {a.run} is a {'stand-in' if _is_standin(row) else 'real'} run; resume it the same way it was started")
        saved_cutoff = float(json.loads(row["hashes_json"])["cutoff"])
        saved_prompt = json.loads(row["configs_json"]).get("prompt_file", "enrich-v1.json")
        setup = jev.load_setup(a.prompts, saved_cutoff if a.cutoff is None else a.cutoff, prompt_name=a.prompt_file or saved_prompt)
        if real and not a.go:
            left = db.execute("SELECT COUNT(*) FROM reviews WHERE run=? AND status='pending' AND cache_source_id IS NULL", (a.run,)).fetchone()[0]
            return _would_spend(db, a, left)
        if not Path(row["input_path"]).exists():
            raise Refused(f"the input file is gone: {row['input_path']}")
        if real:
            state.require_clean_tree(ROOT, real=True)
        state.check_resume(
            db, a.run, input_sha256=hashing.file_sha(row["input_path"]), seed=row["seed"], code_hash=code_hash,
            hashes=setup.hashes(), allow_code=a.allow_code, code_commit=commit,
        )  # fmt: skip
        labeler, gemma_client, limiter = _clients(a, real)
    return _stages(db, a, setup, labeler, gemma_client, limiter)


def cmd_status(db, a):
    row = state.load_run(db, a.run)
    counts = dict(db.execute("SELECT status, COUNT(*) FROM reviews WHERE run=? GROUP BY status", (a.run,)).fetchall())
    print(f"run {a.run} ({'stand-in' if _is_standin(row) else 'real'}), {row['label_config']}, input {Path(row['input_path']).name}")
    print("reviews: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for s in db.execute("SELECT * FROM sessions WHERE run=? ORDER BY session_id", (a.run,)):
        seconds = "running or crashed" if s["ended_mono"] is None else f"{s['ended_mono'] - s['started_mono']:.1f} s"
        print(f"  session {s['session_id']}: {s['stage']}, {s['ended_how'] or 'open'}, {seconds}, {s['workers']} worker(s)")
    stuck = db.execute("SELECT COUNT(*) FROM reviews WHERE run=? AND status='pending' AND attempts>0 AND cache_source_id IS NULL", (a.run,)).fetchone()[0]
    if stuck:
        print(f"{stuck} review(s) are pending after failed rounds. If they keep failing: python3 -m pipeline quarantine-stuck --run {a.run} --reason api_failure_after_retries")
    led = ledger.Ledger(db, a.billing, cap_usd=Decimal(a.cap))
    print(f"Jev spend in this state file: ${led.spent_usd():.4f} spent, ${led.reserved_usd():.4f} reserved, cap ${a.cap}")
    return OK


def cmd_quarantine_stuck(db, a):
    state.load_run(db, a.run)
    stuck = [
        r["review_id"]
        for r in db.execute(
            "SELECT review_id FROM reviews WHERE run=? AND status='pending' AND attempts>0 AND cache_source_id IS NULL ORDER BY run_order",
            (a.run,),
        )
    ]
    if not a.yes:
        print(f"{len(stuck)} review(s) kept failing and would be quarantined with reason {a.reason}, with their copies.")
        print("Nothing was changed. This lowers coverage; it is your call. Add --yes to do it.")
        return OK
    with state.tx(db):
        for review_id in stuck:
            state.quarantine(db, a.run, review_id, a.reason)
    print(f"quarantined {len(stuck)} review(s) with reason {a.reason}, with their copies")
    return OK


def cmd_export(db, a):
    row = state.load_run(db, a.run)
    result = export.export(
        db, a.run, a.out, checker_path=a.checker, input_path=row["input_path"], evidence_dir=a.evidence,
        cap_usd=Decimal(a.cap), log=print,
    )  # fmt: skip
    cov = result["coverage"]
    print(f"coverage: {cov['valid_completed']} classified, {cov['quarantined']} quarantined, of {cov['expected']} rows")
    if result["calls_with_unknown_usage"]:
        print(f"{result['calls_with_unknown_usage']} call(s) have unknown usage and are exported with zeros and usage_known false: the usage totals are incomplete")
    return OK if result["status"] == "pass" else FAILED_CHECK


def cmd_adjust(db, a):
    """A correction to the spend ledger, found by comparing it with the provider's usage page."""
    try:
        amount = Decimal(a.usd)
    except ArithmeticError:
        raise Refused("--usd takes a dollar amount such as 0.25 or -0.10") from None
    if not amount.is_finite():
        raise Refused("--usd takes a dollar amount such as 0.25 or -0.10")
    led = ledger.Ledger(db, a.billing, cap_usd=Decimal(a.cap))
    led.adjust(amount, a.note)
    print(f"ledger adjusted by ${amount:.4f} ({a.note}). Spent now: ${led.spent_usd():.4f} of ${a.cap}")
    return OK


def cmd_memo(db, a):
    """Check a memo edited by hand against the run's numbers; with --save, make it the run's memo."""
    state.load_run(db, a.run)
    text = Path(a.file).read_text(encoding="utf-8")
    problems = memo.recheck(db, a.run, text)
    if problems:
        print(f"the memo does not pass the check ({len(problems)} problems):")
        for problem in problems:
            print(f"  - {problem}")
        return FAILED_CHECK
    if a.save:
        memo.save_edited(db, a.run, text)
        print(f"the memo passes the check and is now the memo of run {a.run}")
    else:
        print("the memo passes the check. Nothing was saved (add --save).")
    return OK


def cmd_nested(db, a):
    """The gate check that reviews seen at two gates kept their labels (spec item 25)."""
    if a.run == a.against:
        raise Refused("a run compared with itself always agrees; name the earlier, smaller run with --against")
    state.load_run(db, a.run)
    state.load_run(db, a.against)
    compared, differ = classify.nested_differences(db, a.run, a.against)
    if not compared:
        raise Refused(f"runs {a.run} and {a.against} have no completed review in common, so there is nothing to compare")
    if differ:
        print(f"{len(differ)} of {compared} reviews labeled in both runs changed between {a.against} and {a.run}:")
        for review_id, fields in differ:
            print(f"  {review_id}: {', '.join(fields)}")
        print("This stops the gate. Jev's documents say identical requests can return different answers; it is your call.")
        return GUARD
    print(f"{compared} reviews are labeled in both runs and every one kept its labels")
    return OK


def cmd_rank(a):
    rows = rank.from_files(a.grading)
    print(f"ranking.csv rebuilt from {a.grading}: {len(rows)} issues")
    return OK


def state_path(a):
    """The state file a command uses: the one named, else the stand-in file for a stand-in run, else the real one."""
    if a.state:
        return a.state
    return str(STANDIN_STATE if getattr(a, "standin", False) else STATE)


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", help="the state file (default runs/state.sqlite; runs/standin.sqlite for a --standin run)")
    common.add_argument("--billing", default=str(ROOT / "pipeline/billing.json"))
    common.add_argument("--cap", default="25", help="the cap on total Jev spend in dollars")
    p = argparse.ArgumentParser(prog="python3 -m pipeline", description=(__doc__ or "").split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", parents=[common], help="start a run or resume one")
    r.add_argument("--run", required=True)
    r.add_argument("--new", action="store_true", help="create the run; needs --input")
    r.add_argument("--input")
    r.add_argument("--stop-after", type=int, help="stop classify after this many new completions, with work pending")
    r.add_argument("--max-hours", type=float)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--cutoff", type=float, help="needs_review cut-off; part of label_config (default 0.70)")
    r.add_argument("--verify-size", type=int, default=5000)
    r.add_argument("--seed", default=SEED)
    r.add_argument("--warm-from", help="take every result from this finished run and make no call (the cost pilot's warm pass)")
    r.add_argument("--standin", action="store_true", help="run with the stand-in models: no network, no cost")
    r.add_argument("--go", action="store_true", help="really call the models; without it a real run only says what it would spend")
    r.add_argument("--allow-code", help="resume although the code changed, naming the new code hash")
    r.add_argument("--accept-guard", action="append", help="accept a named guard on an input that is not a supplied file")
    r.add_argument("--prompts", default=str(ROOT / "prompts"))
    r.add_argument("--prompt-file", help="the enrich wording, a file in the prompts folder (default enrich-v1.json); part of label_config")
    r.add_argument("--standin-latency", type=float, default=0.0, help=argparse.SUPPRESS)
    r.add_argument("--standin-log", help=argparse.SUPPRESS)

    s = sub.add_parser("status", parents=[common], help="where a run stands")
    s.add_argument("--run", required=True)

    q = sub.add_parser("quarantine-stuck", parents=[common], help="quarantine reviews whose requests kept failing")
    q.add_argument("--run", required=True)
    q.add_argument("--reason", required=True)
    q.add_argument("--yes", action="store_true")

    e = sub.add_parser("export", parents=[common], help="write grading/ and the run evidence, then run the supplied checker")
    e.add_argument("--run", required=True)
    e.add_argument("--out", default=str(ROOT / "grading"))
    e.add_argument("--evidence", help="also write the run evidence to this folder")
    e.add_argument("--checker", default=str(CHECKER))

    j = sub.add_parser("adjust", parents=[common], help="correct the spend ledger after reading the provider's usage page")
    j.add_argument("--usd", required=True, help="dollars to add (negative to take away)")
    j.add_argument("--note", required=True, help="why: what the usage page showed")

    m = sub.add_parser("memo", parents=[common], help="check a memo edited by hand; --save makes it the run's memo")
    m.add_argument("--run", required=True)
    m.add_argument("--file", required=True)
    m.add_argument("--save", action="store_true")

    n = sub.add_parser("nested", parents=[common], help="check that reviews labeled in two runs kept their labels")
    n.add_argument("--run", required=True)
    n.add_argument("--against", required=True, help="the earlier, smaller run")

    k = sub.add_parser("rank", parents=[common], help="rebuild ranking.csv from committed files; no model, no state file")
    k.add_argument("--grading", default=str(ROOT / "grading"))
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    if a.command == "rank":
        return cmd_rank(a)
    a.state = state_path(a)
    lock = state.RunLock(a.state)
    try:
        lock.acquire()
    except state.Locked as e:
        print(f"refused: {e}. One process at a time.")
        return REFUSED
    try:
        db = state.connect(a.state)
        try:
            handler = {"run": cmd_run, "status": cmd_status, "quarantine-stuck": cmd_quarantine_stuck, "export": cmd_export, "adjust": cmd_adjust, "memo": cmd_memo, "nested": cmd_nested}[a.command]
            return handler(db, a)
        except (Refused, state.ResumeRefused, state.NoSuchRun, state.DirtyTree, prepare.BadInput, prepare.GuardFailed, export.NotReady, ValueError) as e:
            what = f"there is no run named {e}" if isinstance(e, state.NoSuchRun) else str(e)
            print(f"refused: {what}")
            if isinstance(e, state.ResumeRefused) and "code" in e.names:
                # The run refuses code it was not started with. Its owner may allow the new code by its hash.
                print(f"If the change is meant, resume with: --allow-code {state.code_fingerprint(ROOT)[1]}")
            return REFUSED
        finally:
            db.close()
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
