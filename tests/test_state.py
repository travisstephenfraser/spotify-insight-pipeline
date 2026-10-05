import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pipeline import state
from tests import fixtures

GIT = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]


class TmpCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.path = self.dir / "state.sqlite"

    def connect(self):
        db = state.connect(self.path)
        self.addCleanup(db.close)
        return db

    def repo(self):
        """A small git repo shaped like this one: pipeline/ and prompts/, one commit."""
        root = self.dir / "repo"
        (root / "pipeline").mkdir(parents=True)
        (root / "prompts").mkdir()
        (root / "pipeline/a.py").write_text("X = 1\n")
        (root / "prompts/p.md").write_text("prompt\n")
        subprocess.run([*GIT, "init", "-q", str(root)], check=True)
        subprocess.run([*GIT, "-C", str(root), "add", "."], check=True)
        subprocess.run([*GIT, "-C", str(root), "commit", "-q", "-m", "first"], check=True)
        return root


class Schema(TmpCase):
    def test_reopening_keeps_data(self):
        db = self.connect()
        fixtures.new_run(db)
        db.close()
        db = self.connect()
        self.assertEqual(db.execute("SELECT run FROM runs").fetchone()["run"], "r1")

    def test_every_planned_table_exists(self):
        db = self.connect()
        names = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(
            names,
            {"runs", "sessions", "reviews", "results", "calls", "ledger", "verify", "issues", "membership", "artifacts"},
        )

    def test_write_ahead_mode(self):
        db = self.connect()
        self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_a_failed_transaction_leaves_nothing(self):
        db = self.connect()
        with self.assertRaises(RuntimeError):
            with state.tx(db):
                fixtures.new_run(db)
                raise RuntimeError("crash")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)


class Runs(TmpCase):
    def setUp(self):
        super().setUp()
        self.db = self.connect()
        fixtures.new_run(self.db)
        self.same = {k: fixtures.RUN_ARGS[k] for k in ("input_sha256", "seed", "code_hash", "hashes")}

    def test_create_run_twice_raises(self):
        with self.assertRaises(state.RunExists):
            fixtures.new_run(self.db)

    def test_unknown_run_raises(self):
        with self.assertRaises(state.NoSuchRun):
            state.check_resume(self.db, "nope", **self.same)

    def test_resume_passes_when_nothing_changed(self):
        state.check_resume(self.db, "r1", **self.same)

    def test_resume_names_each_difference(self):
        changed = {
            **self.same,
            "input_sha256": "b" * 64,
            "seed": "other-seed",
            "hashes": {**self.same["hashes"], "features": "9" * 64, "cutoff": "0.80"},
        }
        with self.assertRaises(state.ResumeRefused) as caught:
            state.check_resume(self.db, "r1", **changed)
        self.assertEqual(sorted(caught.exception.names), ["cutoff", "features", "input", "seed"])

    def test_a_hash_that_appears_or_disappears_is_named(self):
        hashes = dict(self.same["hashes"])
        del hashes["splitter"]
        hashes["prompt:new.md"] = "5" * 64
        with self.assertRaises(state.ResumeRefused) as caught:
            state.check_resume(self.db, "r1", **{**self.same, "hashes": hashes})
        self.assertEqual(sorted(caught.exception.names), ["prompt:new.md", "splitter"])

    def test_changed_code_is_refused_unless_allowed_by_its_hash(self):
        new = "e" * 64
        with self.assertRaises(state.ResumeRefused) as caught:
            state.check_resume(self.db, "r1", **{**self.same, "code_hash": new})
        self.assertEqual(caught.exception.names, ["code"])
        with self.assertRaises(state.ResumeRefused):
            state.check_resume(self.db, "r1", **{**self.same, "code_hash": new}, allow_code="f" * 64)
        state.check_resume(self.db, "r1", **{**self.same, "code_hash": new}, allow_code=new, code_commit="9" * 40)

    def test_an_allowed_code_change_is_logged_and_becomes_the_runs_code(self):
        new = "e" * 64
        state.check_resume(self.db, "r1", **{**self.same, "code_hash": new}, allow_code=new, code_commit="9" * 40)
        row = self.db.execute("SELECT * FROM runs WHERE run='r1'").fetchone()
        overrides = json.loads(row["configs_json"])["code_overrides"]
        self.assertEqual([(o["from"], o["to"]) for o in overrides], [("d" * 64, new)])
        self.assertEqual((row["code_hash"], row["code_commit"]), (new, "9" * 40))
        state.check_resume(self.db, "r1", **{**self.same, "code_hash": new})


class Fingerprint(TmpCase):
    def test_two_uncommitted_edits_give_two_different_hashes(self):
        root = self.repo()
        commit, h0, clean = state.code_fingerprint(root)
        self.assertTrue(clean)
        self.assertEqual(len(commit), 40)
        (root / "pipeline/a.py").write_text("X = 2\n")
        _, h1, clean1 = state.code_fingerprint(root)
        (root / "pipeline/a.py").write_text("X = 3\n")
        commit2, h2, _ = state.code_fingerprint(root)
        self.assertEqual(commit2, commit)
        self.assertFalse(clean1)
        self.assertEqual(len({h0, h1, h2}), 3)

    def test_a_renamed_file_changes_the_hash(self):
        root = self.repo()
        _, h0, _ = state.code_fingerprint(root)
        (root / "pipeline/a.py").rename(root / "pipeline/b.py")
        self.assertNotEqual(state.code_fingerprint(root)[1], h0)

    def test_a_new_prompt_file_makes_the_tree_dirty_but_keeps_the_code_hash(self):
        root = self.repo()
        _, h0, _ = state.code_fingerprint(root)
        (root / "prompts/new.md").write_text("x\n")
        _, h1, clean = state.code_fingerprint(root)
        self.assertEqual(h1, h0)
        self.assertFalse(clean)

    def test_a_real_run_needs_a_clean_tree_and_a_stand_in_run_does_not(self):
        root = self.repo()
        state.require_clean_tree(root, real=True)
        (root / "pipeline/a.py").write_text("X = 2\n")
        with self.assertRaises(state.DirtyTree):
            state.require_clean_tree(root, real=True)
        state.require_clean_tree(root, real=False)


class Sessions(TmpCase):
    def test_a_closed_session_keeps_its_clock(self):
        db = self.connect()
        clock = fixtures.FakeClock()
        sid = state.open_session(db, "r1", "classify", 4, clock)
        clock.advance(12.5)
        state.close_session(db, sid, "finished", clock)
        row = db.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()
        self.assertEqual((row["ended_mono"] - row["started_mono"], row["ended_how"], row["workers"]), (12.5, "finished", 4))

    def test_a_session_left_open_is_closed_as_crashed_at_its_last_heartbeat(self):
        db = self.connect()
        clock = fixtures.FakeClock()
        done = state.open_session(db, "r1", "classify", 1, clock)
        state.close_session(db, done, "stop_after", clock)
        sid = state.open_session(db, "r1", "classify", 1, clock)
        clock.advance(7)
        state.heartbeat(db, sid, clock)
        clock.advance(100)  # the process was killed here; nothing more was written
        self.assertEqual(state.close_crashed_sessions(db, "r1"), 1)
        row = db.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()
        self.assertEqual((row["ended_mono"] - row["started_mono"], row["ended_how"]), (7, "crashed"))
        kept = db.execute("SELECT ended_how FROM sessions WHERE session_id=?", (done,)).fetchone()
        self.assertEqual(kept["ended_how"], "stop_after")

    def test_a_crashed_session_with_no_heartbeat_ends_where_it_started(self):
        db = self.connect()
        clock = fixtures.FakeClock()
        sid = state.open_session(db, "r1", "verify", 1, clock)
        state.close_crashed_sessions(db, "r1")
        row = db.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()
        self.assertEqual(row["ended_mono"], row["started_mono"])


class Lock(TmpCase):
    def test_a_second_process_is_refused_with_the_holders_pid(self):
        first = state.RunLock(self.path)
        first.acquire()
        self.addCleanup(first.release)
        with self.assertRaises(state.Locked) as caught:
            state.RunLock(self.path).acquire()
        self.assertEqual(caught.exception.pid, os.getpid())

    def test_release_lets_the_next_one_in(self):
        first = state.RunLock(self.path)
        first.acquire()
        first.release()
        second = state.RunLock(self.path)
        second.acquire()
        second.release()

    def test_a_lock_left_by_a_dead_process_is_cleared_with_a_message(self):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        Path(str(self.path) + ".lock").write_text(str(dead.pid))
        err = io.StringIO()
        lock = state.RunLock(self.path)
        with contextlib.redirect_stderr(err):
            lock.acquire()
        self.addCleanup(lock.release)
        self.assertIn(str(dead.pid), err.getvalue())
        self.assertEqual(Path(str(self.path) + ".lock").read_text(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main()


class Durability(TmpCase):
    def test_the_default_waits_for_the_disk_on_every_commit(self):
        self.assertEqual(self.connect().execute("PRAGMA synchronous").fetchone()[0], 2)

    def test_a_test_can_ask_for_no_waiting(self):
        db = state.connect(self.path, synchronous="OFF")
        self.addCleanup(db.close)
        self.assertEqual(db.execute("PRAGMA synchronous").fetchone()[0], 0)
