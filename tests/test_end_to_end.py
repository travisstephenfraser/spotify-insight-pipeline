import contextlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from pipeline import classify, cli, jev, ledger, limits, standins, state
from tests import fixtures


def rows_60():
    rows = fixtures.synthetic_rows(60, empties=3, copies=6)
    for row, text in zip(rows[10:], fixtures.AWKWARD, strict=False):
        row["review_text"] = text
    return rows


class CliCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.state = self.dir / "state.sqlite"
        self.csv = self.dir / "input.csv"
        fixtures.write_csv(self.csv, rows_60())

    def cli(self, *args):
        """Run one command in this process. Returns (exit code, everything it printed)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main([*map(str, args), "--state", str(self.state)])
        return code, out.getvalue()

    def db(self):
        db = state.connect(self.state, synchronous="OFF")
        self.addCleanup(db.close)
        return db


class EndToEnd(CliCase):
    def test_a_stopped_run_resumes_exports_and_passes_the_supplied_checker(self):
        code, text = self.cli("run", "--run", "e2e", "--new", "--input", self.csv, "--standin", "--stop-after", "20", "--verify-size", "15")
        self.assertEqual(code, 3, text)
        self.assertIn("stop_after", text)
        code, text = self.cli("run", "--run", "e2e", "--standin")
        self.assertEqual(code, 0, text)
        self.assertIn("export", text)

        out = self.dir / "grading"
        code, text = self.cli("export", "--run", "e2e", "--out", out, "--evidence", self.dir / "evidence")
        self.assertEqual(code, 0, text)
        self.assertIn("checker status: pass", text)
        report = json.loads((self.dir / "self-check.json").read_text())
        self.assertEqual((report["status"], report["issue_counts"]), ("pass", {}))
        self.assertEqual(report["coverage"]["labelable_completion_fraction"], 1.0)
        self.assertEqual(report["coverage"]["accounted_fraction"], 1.0)
        self.assertEqual((report["coverage"]["expected"], report["coverage"]["quarantined"]), (60, 3))
        self.assertTrue((self.dir / "evidence" / "memo.md").read_text().startswith("# Decision memo"))

        first = (out / "ranking.csv").read_bytes()
        for _ in range(2):
            code, text = self.cli("rank", "--grading", out)
            self.assertEqual(code, 0, text)
            self.assertEqual((out / "ranking.csv").read_bytes(), first)

    def test_new_on_a_run_that_exists_is_refused(self):
        self.cli("run", "--run", "e2e", "--new", "--input", self.csv, "--standin", "--stop-after", "5")
        code, text = self.cli("run", "--run", "e2e", "--new", "--input", self.csv, "--standin")
        self.assertEqual(code, 2)
        self.assertIn("exists", text)

    def test_status_shows_where_a_stopped_run_stands(self):
        self.cli("run", "--run", "e2e", "--new", "--input", self.csv, "--standin", "--stop-after", "20")
        code, text = self.cli("status", "--run", "e2e")
        self.assertEqual(code, 0)
        self.assertIn("pending", text)
        self.assertIn("stop_after", text)

    def test_export_of_an_unfinished_run_is_refused(self):
        self.cli("run", "--run", "e2e", "--new", "--input", self.csv, "--standin", "--stop-after", "5")
        code, text = self.cli("export", "--run", "e2e", "--out", self.dir / "grading")
        self.assertEqual(code, 2)
        self.assertIn("pending", text)


class Interrupted(CliCase):
    def test_ctrl_c_stops_cleanly_and_the_same_command_finishes_the_run(self):
        log1, log2 = self.dir / "sent1.log", self.dir / "sent2.log"
        base = [sys.executable, "-m", "pipeline", "run", "--run", "sig", "--state", str(self.state), "--standin"]
        child = subprocess.Popen(
            [*base, "--new", "--input", str(self.csv), "--verify-size", "15", "--standin-latency", "0.05", "--standin-log", str(log1)],
            cwd=fixtures.ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )  # fmt: skip
        deadline = time.time() + 30
        while time.time() < deadline and (not log1.exists() or len(log1.read_text().splitlines()) < 8):
            time.sleep(0.02)
        child.send_signal(signal.SIGINT)
        output, _ = child.communicate(timeout=30)
        self.assertEqual(child.returncode, 3, output)
        self.assertIn("interrupted", output)

        db = self.db()
        done = {r["review_text"] for r in db.execute("SELECT review_text FROM reviews WHERE status='completed'")}
        self.assertTrue(done)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM calls WHERE outcome='pending'").fetchone()[0], 0)
        code, text = self.cli("run", "--run", "sig", "--standin", "--standin-log", log2)
        self.assertEqual(code, 0, text)
        resent = {json.loads(line) for line in log2.read_text().splitlines()}
        self.assertFalse(done & resent)
        code, text = self.cli("export", "--run", "sig", "--out", self.dir / "grading")
        self.assertIn("checker status: pass", text)


class PilotReplay(CliCase):
    def test_the_100_pilot_reviews_replayed_give_the_ranking_recorded_on_2026_10_04(self):
        """Known answer from outside this code: CLAUDE.md records 52 complaints or cancellations among Jev's
        saved answers, with usability 38, other 29, playback 22 and billing 20 by severity sum."""
        pilot = fixtures.DATA / "cost_100.csv"
        code, text = self.cli("run", "--run", "pilot", "--new", "--input", pilot, "--standin", "--stop-after", "50")
        self.assertEqual(code, 3, text)
        code, text = self.cli("run", "--run", "pilot", "--standin")
        self.assertEqual(code, 0, text)
        self.assertIn("52 members", text)
        out = self.dir / "grading"
        code, text = self.cli("export", "--run", "pilot", "--out", out)
        self.assertEqual(code, 0, text)
        lines = (out / "ranking.csv").read_text().splitlines()[1:5]
        self.assertEqual(
            [(line.split(",")[1], line.split(",")[3]) for line in lines],
            [("issue-usability", "38"), ("issue-other", "29"), ("issue-playback", "22"), ("issue-billing", "20")],
        )


class PromptFile(CliCase):
    def test_a_run_is_created_with_the_wording_it_names_and_resumes_with_it(self):
        code, text = self.cli("run", "--run", "v2", "--new", "--input", self.csv, "--standin", "--stop-after", "5", "--verify-size", "15", "--prompt-file", "enrich-v2.json")
        self.assertEqual(code, 3, text)
        row = self.db().execute("SELECT * FROM runs WHERE run='v2'").fetchone()
        self.assertEqual(row["label_config"], "jev-1.13.0/prompt-v2/schema-v1/cut-0.70")
        self.assertIn("prompt:enrich-v2.json", json.loads(row["hashes_json"]))
        code, text = self.cli("run", "--run", "v2", "--standin")
        self.assertEqual(code, 0, text)
        configs = {c["label_config"] for c in self.db().execute("SELECT label_config FROM calls WHERE run='v2' AND role='enrich'")}
        self.assertEqual(configs, {"jev-1.13.0/prompt-v2/schema-v1/cut-0.70"})


class StandInGuard(CliCase):
    def test_two_stand_ins_that_always_agree_trip_the_agreement_guard_and_it_can_be_accepted_by_name(self):
        code, text = self.cli("run", "--run", "g", "--new", "--input", self.csv, "--standin")
        self.assertEqual(code, 4, text)
        self.assertIn("verifier_agreement_100", text)
        code, text = self.cli("run", "--run", "g", "--standin", "--accept-guard", "verifier_agreement_100")
        self.assertEqual(code, 0, text)


class Warm(CliCase):
    def cold(self):
        self.cli("run", "--run", "cold", "--new", "--input", self.csv, "--standin", "--verify-size", "15")

    def test_a_warm_pass_makes_no_call_of_any_role_and_says_so(self):
        self.cold()
        log = self.dir / "warm.log"
        code, text = self.cli("run", "--run", "warm", "--new", "--input", self.csv, "--standin", "--verify-size", "15", "--warm-from", "cold", "--standin-log", log)
        self.assertEqual(code, 0, text)
        db = self.db()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM calls WHERE run='warm'").fetchone()[0], 0)
        self.assertFalse(log.exists() and log.read_text().strip())
        record = json.loads(db.execute("SELECT output_json FROM artifacts WHERE key='warm:warm'").fetchone()[0])
        self.assertEqual((record["calls_made"], record["source_run"]), (0, "cold"))
        same = "SELECT status, reason, COUNT(*) FROM reviews WHERE run=? GROUP BY 1, 2 ORDER BY 1, 2"
        self.assertEqual([tuple(r) for r in db.execute(same, ("warm",))], [tuple(r) for r in db.execute(same, ("cold",))])
        stages = {r["stage"]: r for r in db.execute("SELECT * FROM sessions WHERE run='warm'")}
        self.assertEqual(set(stages), {"classify", "verify", "group", "memo"})
        self.assertTrue(all(s["ended_mono"] is not None and s["ended_mono"] >= s["started_mono"] for s in stages.values()))
        self.assertIn("0 calls", text)

    def test_a_warm_pass_is_refused_when_a_setting_differs(self):
        self.cold()
        code, text = self.cli("run", "--run", "warm", "--new", "--input", self.csv, "--standin", "--verify-size", "15", "--warm-from", "cold", "--cutoff", "0.8")
        self.assertEqual(code, 2)
        self.assertIn("cutoff", text)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM runs WHERE run='warm'").fetchone()[0], 0)

    def test_a_warm_pass_from_an_unfinished_run_is_refused(self):
        self.cli("run", "--run", "cold", "--new", "--input", self.csv, "--standin", "--stop-after", "5")
        code, text = self.cli("run", "--run", "warm", "--new", "--input", self.csv, "--standin", "--warm-from", "cold")
        self.assertEqual(code, 2)
        self.assertIn("not finished", text)


class Refusals(CliCase):
    def test_a_real_run_without_go_says_what_it_would_spend_and_starts_nothing(self):
        code, text = self.cli("run", "--run", "real", "--new", "--input", self.csv)
        self.assertEqual(code, 0, text)
        self.assertIn("--go", text)
        self.assertIn("$", text)
        self.assertIn("estimate", text)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)

    def test_resuming_after_a_prompt_file_changed_is_refused_and_names_the_file(self):
        prompts = self.dir / "prompts"
        shutil.copytree(fixtures.ROOT / "prompts", prompts)
        self.cli("run", "--run", "p", "--new", "--input", self.csv, "--standin", "--stop-after", "5", "--prompts", prompts)
        path = prompts / jev.PROMPT_FILE
        before = path.read_text()
        path.write_text(before.replace("writer", "author", 1))
        self.assertNotEqual(path.read_text(), before)
        code, text = self.cli("run", "--run", "p", "--standin", "--prompts", prompts)
        self.assertEqual(code, 2)
        self.assertIn(f"prompt:{jev.PROMPT_FILE}", text)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)

    def test_a_second_process_on_the_same_state_file_is_refused(self):
        """Review Focus 3."""
        lock = state.RunLock(self.state)
        lock.acquire()
        self.addCleanup(lock.release)
        code, text = self.cli("run", "--run", "x", "--new", "--input", self.csv, "--standin")
        self.assertEqual(code, 2)
        self.assertIn(str(os.getpid()), text)

    def test_the_lock_is_released_when_a_command_ends(self):
        self.cli("run", "--run", "x", "--new", "--input", self.csv, "--standin", "--stop-after", "5")
        self.assertFalse(Path(str(self.state) + ".lock").exists())

    def test_a_stand_in_run_and_a_real_run_never_share_a_state_file(self):
        self.cli("run", "--run", "x", "--new", "--input", self.csv, "--standin", "--stop-after", "5")
        code, text = self.cli("run", "--run", "y", "--new", "--input", self.csv, "--go")
        self.assertEqual(code, 2)
        self.assertIn("stand-in", text)

    def stuck(self):
        """A run left `stuck` by a review whose requests keep failing, built through the stages."""
        db = fixtures.prepared_db(self.dir / "s", fixtures.synthetic_rows(12, empties=0, copies=0))
        target = db.execute("SELECT * FROM reviews ORDER BY run_order").fetchone()
        out = classify.run(
            db, "r1", standins.ReplayJev(script={target["review_text"]: ["temporary"] * 8}),
            ledger=ledger.Ledger(db, fixtures.write_billing(self.dir / "s" / "billing.json"), cap_usd=Decimal("25")),
            limiter=limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9),
            setup=jev.load_setup(fixtures.ROOT / "prompts", 0.7), backoff=(0, 0, 0),
        )  # fmt: skip
        db.close()
        self.assertEqual(out.ended_how, "stuck")
        self.state = self.dir / "s" / "state.sqlite"
        return target["review_id"]

    def test_quarantine_stuck_without_yes_changes_nothing(self):
        target = self.stuck()
        code, text = self.cli("quarantine-stuck", "--run", "r1", "--reason", "api_failure_after_retries")
        self.assertEqual(code, 0)
        self.assertIn("1 review", text)
        self.assertIn("--yes", text)
        self.assertEqual(self.db().execute("SELECT status FROM reviews WHERE review_id=?", (target,)).fetchone()[0], "pending")

    def test_quarantine_stuck_with_yes_quarantines_only_the_reviews_that_kept_failing(self):
        target = self.stuck()
        code, _ = self.cli("quarantine-stuck", "--run", "r1", "--reason", "api_failure_after_retries", "--yes")
        self.assertEqual(code, 0)
        rows = self.db().execute("SELECT review_id, status, reason FROM reviews WHERE status='quarantined'").fetchall()
        self.assertEqual([tuple(r) for r in rows], [(target, "quarantined", "api_failure_after_retries")])


class CleanClone(unittest.TestCase):
    def copy(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        clone = Path(tmp.name) / "clone"
        listed = subprocess.run(
            ["git", "-C", str(fixtures.ROOT), "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        for name in listed:
            source = fixtures.ROOT / name
            if source.is_file():
                (clone / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, clone / name)
        return clone

    def test_only_the_blank_example_env_file_is_tracked(self):
        tracked = subprocess.run(
            ["git", "-C", str(fixtures.ROOT), "ls-files", "--", ".env", ".env.*"], capture_output=True, text=True, check=True
        ).stdout.split()
        self.assertEqual(tracked, [".env.example"])

    @unittest.skipIf(os.environ.get("IN_CLEAN_CLONE") == "1", "already inside the clean-clone check")
    def test_a_fresh_copy_with_no_env_file_can_rank_and_run_its_tests(self):
        clone = self.copy()
        self.assertFalse((clone / ".env").exists())
        self.assertFalse((clone / "runs" / "state.sqlite").exists())
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")} | {"IN_CLEAN_CLONE": "1"}
        tests = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_hashing", "tests.test_rank", "tests.test_labels", "tests.test_export"],
            cwd=clone, env=env, capture_output=True, text=True,
        )  # fmt: skip
        self.assertEqual(tests.returncode, 0, tests.stderr[-2000:])
        with tempfile.TemporaryDirectory() as tmp:
            db, csv_path = fixtures.full_run(Path(tmp) / "a")
            try:
                from pipeline import export

                grading = Path(tmp) / "a" / "grading"
                export.export(db, "r1", grading, checker_path=fixtures.CHECKER, input_path=csv_path)
            finally:
                db.close()
            first = (grading / "ranking.csv").read_bytes()
            ranked = subprocess.run([sys.executable, "-m", "pipeline", "rank", "--grading", str(grading)], cwd=clone, env=env, capture_output=True, text=True)
            self.assertEqual(ranked.returncode, 0, ranked.stderr[-2000:])
            self.assertEqual((grading / "ranking.csv").read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
