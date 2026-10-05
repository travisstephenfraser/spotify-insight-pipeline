"""Tests added in the fix pass after the final whole-branch review. Each names the finding it pins."""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from pipeline import classify, cli, gemma, group, jev, ledger, limits, memo, standins, state, verify
from tests import fixtures


def run_cli(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main([str(a) for a in args])
    return code, out.getvalue()


class TmpCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.state = self.dir / "state.sqlite"
        self.csv = self.dir / "input.csv"
        fixtures.write_csv(self.csv, fixtures.synthetic_rows(40, empties=2, copies=4))

    def cli(self, *args):
        return run_cli(*args, "--state", self.state)

    def db(self):
        db = state.connect(self.state, synchronous="OFF")
        self.addCleanup(db.close)
        return db

    def calls(self, run, role):
        return self.db().execute("SELECT * FROM calls WHERE run=? AND role=? ORDER BY rowid", (run, role)).fetchall()


class Finding1CacheIsPerRun(TmpCase):
    """A second run on the same file must make its own naming and memo calls: each run starts cold."""

    def test_a_second_run_on_the_same_file_makes_its_own_group_and_memo_calls(self):
        for name in ("first", "second"):
            code, text = self.cli("run", "--run", name, "--new", "--input", self.csv, "--standin", "--verify-size", "15")
            self.assertEqual(code, 0, text)
        for role in ("group", "memo"):
            first, second = self.calls("first", role), self.calls("second", role)
            self.assertTrue(first and second, role)
            self.assertEqual(len(second), len(first))
            self.assertEqual({c["outcome"] for c in second}, {"succeeded"})
        self.assertIn("0 reused", text)

    def test_a_warm_pass_still_reuses_its_source_runs_names_and_memo(self):
        self.cli("run", "--run", "cold", "--new", "--input", self.csv, "--standin", "--verify-size", "15")
        code, text = self.cli("run", "--run", "warm", "--new", "--input", self.csv, "--standin", "--verify-size", "15", "--warm-from", "cold")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM calls WHERE run='warm'").fetchone()[0], 0)
        self.assertEqual(memo.final(self.db(), "warm"), memo.final(self.db(), "cold"))

    def test_a_run_reuses_its_own_names_on_a_second_call(self):
        db = fixtures.grouped_db(self.dir / "a")
        self.addCleanup(db.close)
        again = standins.StandinGemma()
        out = group.name_issues(db, "r1", again)
        self.assertEqual((again.calls, out.named), ([], 0))
        self.assertGreater(out.cached, 0)

    def test_each_runs_artifacts_are_its_own(self):
        for name in ("first", "second"):
            self.cli("run", "--run", name, "--new", "--input", self.csv, "--standin", "--verify-size", "15")
        counts = dict(self.db().execute("SELECT run, COUNT(*) FROM artifacts WHERE role IN ('group','memo') GROUP BY run").fetchall())
        self.assertEqual(counts["first"], counts["second"])
        self.assertGreater(counts["second"], 1)


class NeverAnswers:
    """A labeler for an outage. `sent` says whether a request left the machine before it failed."""

    def __init__(self, sent):
        self.sent, self.calls = sent, 0

    def label(self, text, request):
        self.calls += 1
        raise jev.Temporary("no route to host" if not self.sent else "timed out", sent=self.sent)


class ClassifyCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.db = fixtures.prepared_db(self.dir, fixtures.synthetic_rows(40, empties=0, copies=0))
        self.addCleanup(self.db.close)
        self.billing = fixtures.write_billing(self.dir / "billing.json")

    def go(self, labeler, **options):
        return classify.run(
            self.db, "r1", labeler, ledger=ledger.Ledger(self.db, self.billing, cap_usd=Decimal("25")),
            limiter=limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9),
            setup=jev.load_setup(fixtures.ROOT / "prompts", 0.7), backoff=(0, 0, 0), **options,
        )  # fmt: skip

    def spend(self):
        led = ledger.Ledger(self.db, self.billing)
        return led.spent_usd(), led.reserved_usd()


class Finding3Outage(ClassifyCase):
    """An outage must not walk through the file booking a failed call for every review."""

    def test_a_run_of_failures_with_no_success_stops_admitting_new_reviews(self):
        labeler = NeverAnswers(sent=False)
        out = self.go(labeler)
        self.assertEqual(out.ended_how, "outage")
        self.assertLessEqual(labeler.calls, 8)
        self.assertEqual((out.completed, out.quarantined, out.pending), (0, 0, 40))
        row = self.db.execute("SELECT ended_how FROM sessions WHERE session_id=?", (out.session_id,)).fetchone()
        self.assertEqual(row["ended_how"], "outage")

    def test_with_sixteen_workers_an_outage_costs_at_most_a_few_dozen_calls(self):
        labeler = NeverAnswers(sent=False)
        out = self.go(labeler, workers=16)
        self.assertEqual(out.ended_how, "outage")
        self.assertLessEqual(labeler.calls, 16 * 4)

    def test_a_request_that_never_left_the_machine_costs_nothing(self):
        self.go(NeverAnswers(sent=False))
        self.assertEqual(self.spend(), (0, 0))
        calls = self.db.execute("SELECT outcome, usage_known, input_tokens FROM calls").fetchall()
        self.assertEqual({tuple(c) for c in calls}, {("failed", 0, None)})

    def test_a_request_that_was_sent_and_got_no_usage_keeps_its_reservation(self):
        self.go(NeverAnswers(sent=True))
        spent, reserved = self.spend()
        self.assertGreater(spent, 0)
        self.assertEqual(reserved, 0)

    def test_a_success_in_between_keeps_the_run_going(self):
        texts = [r["review_text"] for r in self.db.execute("SELECT review_text FROM reviews ORDER BY run_order")]
        script = {t: ["temporary", "temporary", "temporary"] for t in texts[::2]}
        out = self.go(standins.ReplayJev(script=script))
        self.assertEqual((out.ended_how, out.completed), ("finished", 40))

    def test_the_outage_is_over_when_the_same_command_is_run_again(self):
        self.go(NeverAnswers(sent=False))
        out = self.go(standins.ReplayJev())
        self.assertEqual((out.ended_how, out.completed), ("finished", 40))


class Finding4RejectedRequest(ClassifyCase):
    """A request the server refuses for one review must not stop every other review for good."""

    def test_a_review_whose_request_is_refused_is_set_aside_and_the_rest_complete(self):
        target = self.db.execute("SELECT * FROM reviews ORDER BY run_order").fetchone()
        labeler = standins.ReplayJev(script={target["review_text"]: ["rejected"] * 5})
        out = self.go(labeler)
        self.assertEqual((out.ended_how, out.completed, out.pending), ("stuck", 39, 1))
        self.assertEqual(out.stuck, [target["review_id"]])
        row = self.db.execute("SELECT status, attempts FROM reviews WHERE review_id=?", (target["review_id"],)).fetchone()
        self.assertEqual((row["status"], row["attempts"]), ("pending", 2))
        self.assertEqual(labeler.sent.count(target["review_text"]), 2)  # once in each round, no retries in between
        mine = self.db.execute("SELECT outcome, http_status FROM calls WHERE review_ids_json=?", (json.dumps([target["review_id"]]),)).fetchall()
        self.assertEqual([tuple(c) for c in mine], [("failed", 400), ("failed", 400)])

    def test_when_every_request_is_refused_the_run_stops_after_a_few(self):
        texts = [r["review_text"] for r in self.db.execute("SELECT review_text FROM reviews")]
        labeler = standins.ReplayJev(script={t: ["rejected"] * 5 for t in texts})
        out = self.go(labeler)
        self.assertEqual(out.ended_how, "outage")
        self.assertLessEqual(len(labeler.sent), 8)


class HttpCase(unittest.TestCase):
    def serve(self, status, body, delay=0.0):
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if delay:
                    time.sleep(delay)
                data = body.encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/v1/systemone", server

    def ask(self, client):
        request = jev.build_request("Bad app.", jev.load_setup(fixtures.ROOT / "prompts", 0.7).prompt)
        return client.label("Bad app.", request)


KEY = "fake-key-for-tests-0123456789"


class JevClientFixes(HttpCase):
    def test_a_refusal_of_one_request_is_rejected_not_fatal(self):
        for status in (400, 404, 413, 422):
            url, _ = self.serve(status, json.dumps({"error": "bad request"}))
            with self.subTest(status=status), self.assertRaises(jev.Rejected) as caught:
                self.ask(jev.Client(KEY, url=url, timeout=5))
            self.assertEqual(caught.exception.status, status)

    def test_a_refusal_of_the_key_or_the_account_is_still_fatal(self):
        for status in (401, 402, 403):
            url, _ = self.serve(status, json.dumps({"error": "no"}))
            with self.subTest(status=status), self.assertRaises(jev.Fatal):
                self.ask(jev.Client(KEY, url=url, timeout=5))

    def test_a_refused_connection_was_never_sent_and_a_timeout_may_have_been(self):
        url, server = self.serve(200, "{}")
        server.shutdown()
        server.server_close()
        with self.assertRaises(jev.Temporary) as refused:
            self.ask(jev.Client(KEY, url=url, timeout=5))
        self.assertIs(refused.exception.sent, False)
        slow, _ = self.serve(200, "{}", delay=1.0)
        with self.assertRaises(jev.Temporary) as timed_out:
            self.ask(jev.Client(KEY, url=slow, timeout=0.2))
        self.assertIs(timed_out.exception.sent, True)

    def test_a_key_that_straddles_the_cut_of_a_long_error_is_still_removed(self):
        """Finding 12: scrub first, then cut."""
        body = "x" * 290 + f" Bearer {KEY} trailing text"
        url, _ = self.serve(500, body)
        with self.assertRaises(jev.Temporary) as caught:
            self.ask(jev.Client(KEY, url=url, timeout=5))
        self.assertNotIn(KEY[:12], str(caught.exception))

    def test_an_unexpected_error_inside_the_client_comes_out_fatal_and_without_the_key(self):
        url, _ = self.serve(200, "{}")
        with mock.patch("urllib.request.urlopen", side_effect=RuntimeError(f"proxy said Bearer {KEY}")):
            with self.assertRaises(jev.Fatal) as caught:
                self.ask(jev.Client(KEY, url=url, timeout=5))
        self.assertNotIn(KEY, str(caught.exception))
        self.assertIn("RuntimeError", str(caught.exception))


class CliFixes(TmpCase):
    def test_a_cut_off_with_more_than_two_decimals_is_refused(self):
        """Finding 14: label_config holds two decimals, so the cut-off itself may hold no more."""
        with self.assertRaises(ValueError):
            jev.load_setup(fixtures.ROOT / "prompts", 0.704)
        code, text = self.cli("run", "--run", "c", "--new", "--input", self.csv, "--standin", "--cutoff", "0.704")
        self.assertEqual(code, 2)
        self.assertIn("two decimals", text)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)

    def test_more_than_sixteen_workers_is_refused(self):
        code, text = self.cli("run", "--run", "w", "--new", "--input", self.csv, "--standin", "--workers", "17")
        self.assertEqual(code, 2)
        self.assertIn("16", text)

    def test_a_refusal_over_changed_code_says_how_to_allow_it(self):
        self.cli("run", "--run", "k", "--new", "--input", self.csv, "--standin", "--stop-after", "5", "--verify-size", "15")
        with mock.patch.object(state, "code_fingerprint", return_value=("c" * 40, "f" * 64, True)):
            code, text = self.cli("run", "--run", "k", "--standin")
        self.assertEqual(code, 2)
        self.assertIn("--allow-code " + "f" * 64, text)

    def test_a_correction_from_the_usage_page_is_one_command(self):
        code, text = self.cli("adjust", "--usd", "0.25", "--note", "usage page shows output tokens billed")
        self.assertEqual(code, 0, text)
        rows = self.db().execute("SELECT kind, usd_fixed, note FROM ledger").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("adjust", "0.25", "usage page shows output tokens billed")])
        self.assertIn("0.2500", text)

    def test_an_adjustment_that_is_not_an_amount_is_refused_and_nothing_is_written(self):
        code, text = self.cli("adjust", "--usd", "a quarter", "--note", "typo")
        self.assertEqual(code, 2)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM ledger WHERE kind='adjust'").fetchone()[0], 0)

    def test_an_adjustment_needs_a_note(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["adjust", "--usd", "0.25", "--state", str(self.state)])


class StagedCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def prompt_copy(self, name, edit="\nBe brief."):
        path = self.dir / name
        path.write_text((fixtures.ROOT / "prompts" / name).read_text(encoding="utf-8") + edit, encoding="utf-8")
        return path


class Finding5PromptsShapeTheirStage(StagedCase):
    """A changed prompt must never be answered from an answer made under the old one."""

    def test_an_edited_memo_prompt_gets_a_new_memo_not_the_saved_one(self):
        db = fixtures.grouped_db(self.dir / "a")
        self.addCleanup(db.close)
        first = standins.StandinGemma()
        memo.write(db, "r1", first)
        again = standins.StandinGemma()
        memo.write(db, "r1", again, prompt_path=self.prompt_copy("memo-v1.md"))
        self.assertEqual((len(first.calls), len(again.calls)), (1, 1))
        configs = [c["label_config"] for c in db.execute("SELECT label_config FROM calls WHERE role='memo' ORDER BY rowid")]
        self.assertEqual(len(set(configs)), 2)

    def test_an_edited_naming_prompt_gets_new_names(self):
        db, _ = fixtures.classified_db(self.dir / "a")
        self.addCleanup(db.close)
        group.assign(db, "r1")
        group.name_issues(db, "r1", standins.StandinGemma())
        again = standins.StandinGemma()
        out = group.name_issues(db, "r1", again, prompt_path=self.prompt_copy("group-v1.md"))
        self.assertEqual(out.cached, 0)
        self.assertGreater(len(again.calls), 0)

    def test_the_verify_prompt_cannot_change_partway_through_a_sample(self):
        db, _ = fixtures.classified_db(self.dir / "a")
        self.addCleanup(db.close)
        clock = fixtures.FakeClock()

        class AnHourEach(standins.StandinGemma):
            def ask(self, *args, **kwargs):
                clock.advance(3600)
                return super().ask(*args, **kwargs)

        self.assertEqual(verify.run(db, "r1", AnHourEach(), clock=clock, max_hours=2.5).ended_how, "time_box")
        fake = standins.StandinGemma()
        out = verify.run(db, "r1", fake, prompt_path=self.prompt_copy("verify-v1.md"))
        self.assertEqual((out.ended_how, fake.calls), ("prompt_changed", []))
        self.assertIn("verify", out.message)
        self.assertEqual(verify.run(db, "r1", standins.StandinGemma()).ended_how, "finished")

    def test_each_stage_names_its_prompts_content_in_its_config(self):
        fake = standins.StandinGemma()
        a = verify.config(fake, fixtures.ROOT / "prompts/verify-v1.md")
        b = verify.config(fake, self.prompt_copy("verify-v1.md"))
        self.assertNotEqual(a, b)
        self.assertNotEqual(memo.config(fake, 5, fixtures.ROOT / "prompts/memo-v1.md"), memo.config(fake, 5, self.prompt_copy("memo-v1.md")))
        self.assertNotEqual(group.config(fake, 30, fixtures.ROOT / "prompts/group-v1.md"), group.config(fake, 30, self.prompt_copy("group-v1.md")))


class EditedMemo(TmpCase):
    """Spec 6.6: a memo Travis edits by hand goes through the same code check."""

    def finished(self):
        code, text = self.cli("run", "--run", "m", "--new", "--input", self.csv, "--standin", "--verify-size", "15")
        self.assertEqual(code, 0, text)
        return memo.final(self.db(), "m")

    def test_a_good_edit_passes_the_check_and_becomes_the_runs_memo(self):
        original = self.finished()
        edited = self.dir / "memo.md"
        edited.write_text(original.replace("# Decision memo", "# Decision memo, edited"), encoding="utf-8")
        code, text = self.cli("memo", "--run", "m", "--file", edited, "--save")
        self.assertEqual(code, 0, text)
        self.assertTrue(memo.final(self.db(), "m").startswith("# Decision memo, edited"))

    def test_an_edit_that_breaks_a_number_is_refused_and_nothing_is_saved(self):
        original = self.finished()
        edited = self.dir / "memo.md"
        edited.write_text(original + "\nAbout 99999 people are affected.", encoding="utf-8")
        code, text = self.cli("memo", "--run", "m", "--file", edited, "--save")
        self.assertEqual(code, 1)
        self.assertIn("99999", text)
        self.assertEqual(memo.final(self.db(), "m"), original)

    def test_without_save_the_check_changes_nothing(self):
        original = self.finished()
        edited = self.dir / "memo.md"
        edited.write_text(original.replace("# Decision memo", "# Edited"), encoding="utf-8")
        code, text = self.cli("memo", "--run", "m", "--file", edited)
        self.assertEqual(code, 0, text)
        self.assertEqual(memo.final(self.db(), "m"), original)


class Finding6GateChecks(TmpCase):
    def two_runs(self):
        small = self.dir / "small.csv"
        rows = fixtures.synthetic_rows(40, empties=2, copies=4)
        fixtures.write_csv(small, rows[:12])
        self.cli("run", "--run", "gate-small", "--new", "--input", small, "--standin", "--verify-size", "5")
        self.cli("run", "--run", "gate-big", "--new", "--input", self.csv, "--standin", "--verify-size", "15")

    def test_reviews_in_both_runs_that_keep_their_labels_pass_the_nested_check(self):
        self.two_runs()
        code, text = self.cli("nested", "--run", "gate-big", "--against", "gate-small")
        self.assertEqual(code, 0, text)
        self.assertIn("12 reviews", text)

    def test_a_review_whose_label_changed_between_runs_stops_the_gate_and_is_listed(self):
        self.two_runs()
        db = self.db()
        row = db.execute("SELECT review_id, text_key FROM reviews WHERE run='gate-small' AND status='completed' ORDER BY run_order").fetchone()
        db.execute("UPDATE results SET severity = CASE severity WHEN 5 THEN 4 ELSE severity + 1 END WHERE run='gate-big' AND text_key=?", (row["text_key"],))
        code, text = self.cli("nested", "--run", "gate-big", "--against", "gate-small")
        self.assertEqual(code, 4)
        self.assertIn(row["review_id"], text)
        self.assertIn("severity", text)

    def test_a_run_compared_with_itself_is_refused(self):
        """Every label equals itself, so this would read as a pass and prove nothing."""
        self.two_runs()
        code, text = self.cli("nested", "--run", "gate-big", "--against", "gate-big")
        self.assertEqual(code, 2)
        self.assertIn("itself", text)

    def test_runs_with_no_review_in_common_are_refused(self):
        self.two_runs()
        other = self.dir / "other.csv"
        rows = fixtures.synthetic_rows(6, empties=0, copies=0)
        for r in rows:
            r["review_id"] = "other-" + r["review_id"]
        fixtures.write_csv(other, rows)
        self.cli("run", "--run", "elsewhere", "--new", "--input", other, "--standin")
        code, text = self.cli("nested", "--run", "elsewhere", "--against", "gate-small")
        self.assertEqual(code, 2)

    def test_the_verify_reports_four_counts_are_printed_and_saved(self):
        code, text = self.cli("run", "--run", "v", "--new", "--input", self.csv, "--standin", "--verify-size", "15")
        self.assertIn("verify report: sample 15, predictions 15, verify failures 0, not labeled by Jev 0", text)
        self.cli("export", "--run", "v", "--out", self.dir / "grading", "--evidence", self.dir / "evidence")
        saved = json.loads((self.dir / "evidence" / "verify_report.json").read_text())
        self.assertEqual((saved["sample"], saved["predictions"], saved["verify_failures"], saved["jev_unlabeled"]), (15, 15, 0, 0))
        self.assertIn("agreement", saved)


class SmallerFixes(StagedCase):
    def test_a_request_the_model_server_refuses_is_one_invalid_answer_not_a_dead_stage(self):
        """Minor 8: a review the server rejects (too long for its context) must not stall verify for good."""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(self.server.status)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client = gemma.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}/v1", timeout=5)
        for status, error in ((400, gemma.InvalidOutput), (413, gemma.InvalidOutput), (422, gemma.InvalidOutput), (500, gemma.ServerProblem), (404, gemma.ServerProblem)):
            server.status = status
            with self.subTest(status=status), self.assertRaises(error):
                client.ask("s", "u", verify.SCHEMA, max_tokens=10)

    def test_a_memo_call_left_open_by_a_kill_is_closed_even_when_the_memo_is_already_saved(self):
        """Minor 10: an open call would make export refuse for good."""
        db = fixtures.grouped_db(self.dir / "a")
        self.addCleanup(db.close)
        memo.write(db, "r1", standins.StandinGemma())
        session = state.open_session(db, "r1", "memo", 1, fixtures.FakeClock())
        state.begin_attempt(db, None, request_id="orphan", run="r1", role="memo", review_ids=[], model="m", label_config="c", session_id=session, reserve_tokens=0)
        memo.write(db, "r1", standins.StandinGemma())
        self.assertEqual(db.execute("SELECT outcome FROM calls WHERE request_id='orphan'").fetchone()[0], "failed")

    def test_a_warm_pass_that_could_not_finish_does_not_report_a_clean_pass(self):
        """Minor 19."""
        import argparse

        db, _ = fixtures.full_run(self.dir / "a", stop_after=None)
        self.addCleanup(db.close)
        from pipeline import prepare

        with state.tx(db):
            fixtures.new_run(db, "warm")
            prepare.prepare(db, "warm", self.dir / "a" / "r1.csv", seed=fixtures.SEED, verify_seed="verify-v1", verify_size=10)
        db.execute("DELETE FROM artifacts WHERE run='r1' AND role='group'")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli._warm(db, argparse.Namespace(run="warm", warm_from="r1"), standins.StandinGemma(loaded=False))
        self.assertEqual(code, cli.NOT_FINISHED)
        self.assertNotIn("0 calls of any role", out.getvalue())

    def test_an_eval_call_left_open_by_a_kill_gives_its_reservation_back_to_spend(self):
        """Minor 9: an open eval call stayed reserved for good."""
        import sys

        sys.path.insert(0, str(fixtures.ROOT / "evals"))
        import common

        db = state.connect(self.dir / "state.sqlite", synchronous="OFF")
        self.addCleanup(db.close)
        billing = fixtures.write_billing(self.dir / "billing.json")
        led = ledger.Ledger(db, billing)
        session = state.open_session(db, common.RUN, "eval: test", 1, fixtures.FakeClock())
        state.begin_attempt(db, led, request_id="open", run=common.RUN, role="enrich", review_ids=["x"], model="m", label_config="c", session_id=session, reserve_tokens=2500)
        self.assertGreater(led.reserved_usd(), 0)
        fresh = ledger.Ledger(db, billing)
        common.Paid(db, fresh, standins.ReplayJev(), jev.load_setup(fixtures.ROOT / "prompts", 0.7), "test")
        self.assertEqual(fresh.reserved_usd(), 0)
        self.assertGreater(fresh.spent_usd(), 0)
        self.assertEqual(db.execute("SELECT outcome FROM calls WHERE request_id='open'").fetchone()[0], "failed")

    def test_a_stand_in_run_has_its_own_default_state_file(self):
        """Minor 11: a stand-in's made-up charges must never land in the real ledger by default."""
        a = cli.parser().parse_args(["run", "--run", "x", "--new", "--input", "f.csv", "--standin"])
        self.assertEqual(Path(cli.state_path(a)).name, "standin.sqlite")
        b = cli.parser().parse_args(["run", "--run", "x", "--new", "--input", "f.csv", "--go"])
        self.assertEqual(Path(cli.state_path(b)).name, "state.sqlite")
        c = cli.parser().parse_args(["run", "--run", "x", "--standin", "--state", "/tmp/mine.sqlite"])
        self.assertEqual(cli.state_path(c), "/tmp/mine.sqlite")

    def test_neither_default_state_file_can_be_committed(self):
        """A state file holds every saved model answer; the stand-in one would also dirty the tree before a real run."""
        ignored = (fixtures.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for path in (cli.STATE, cli.STANDIN_STATE):
            with self.subTest(path=path.name):
                self.assertIn(f"runs/{path.name}*", ignored)

    def test_a_real_eval_refuses_a_state_file_that_holds_stand_in_runs(self):
        import argparse
        import os
        import sys

        sys.path.insert(0, str(fixtures.ROOT / "evals"))
        import common

        db = fixtures.prepared_db(self.dir)
        db.execute("UPDATE runs SET configs_json=?", (json.dumps({"standin": True}),))
        db.close()
        a = argparse.Namespace(go=True, standin=False, state=str(self.dir / "state.sqlite"), prompt_file="enrich-v1.json", cutoff=0.7, cap="25")
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "fake-key-for-tests-0123456789"}):
            with self.assertRaises(cli.Refused):
                with common.session(a, "test"):
                    self.fail("the session must not open")

    def test_a_golden_cell_that_is_not_a_number_is_reported_without_its_value(self):
        """Minor 13: a traceback would print the cell, and no golden label is ever printed."""
        import sys

        sys.path.insert(0, str(fixtures.ROOT / "evals"))
        import score_golden

        golden = self.dir / "golden.csv"
        golden.write_text("review_id,review_text,intent,topic,severity,sentiment,evidence_quote,entities,needs_review,notes\nid-1,Bad app,complaint,other,SECRETLABEL,-0.5,Bad app,,FALSE,\n", encoding="utf-8")
        records = self.dir / "records.jsonl"
        records.write_text("", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = score_golden.main(["--golden", str(golden), "--records", str(records), "--run", "t", "--out-dir", str(self.dir)])
        self.assertEqual(code, 2)
        self.assertNotIn("SECRETLABEL", out.getvalue())
        self.assertIn("row 2", out.getvalue())

    def test_large_run_evidence_is_gzipped_and_named_when_it_is_too_big_for_the_repo(self):
        """Minor 16: the full run's log is far over GitHub's file limit."""
        from pipeline import export

        db, csv_path = fixtures.full_run(self.dir / "a")
        self.addCleanup(db.close)
        evidence = self.dir / "a" / "evidence"
        result = export.export(db, "r1", self.dir / "a" / "grading", checker_path=fixtures.CHECKER, input_path=csv_path, evidence_dir=evidence, gzip_over=1, size_limit=200)
        names = {p.name for p in evidence.iterdir()}
        self.assertIn("run_log.jsonl.gz", names)
        self.assertNotIn("run_log.jsonl", names)
        self.assertIn("evidence/run_log.jsonl.gz", result["release_assets"])

    def test_a_csv_that_cannot_be_read_stops_with_a_plain_message(self):
        """Review Focus 1: a fresh input may be malformed in ways the supplied one is not."""
        from pipeline import prepare

        bad_bytes = self.dir / "latin1.csv"
        bad_bytes.write_bytes(b"review_id,review_text,review_rating,review_likes,app_version,review_timestamp\n1,caf\xe9,5,0,1,2024-01-01\n")
        unbalanced = self.dir / "quote.csv"
        unbalanced.write_text('review_id,review_text,review_rating,review_likes,app_version,review_timestamp\n1,"never closed,5,0,1,2024-01-01\n', encoding="utf-8")
        for path in (bad_bytes, unbalanced):
            with self.subTest(path=path.name), self.assertRaises(prepare.BadInput):
                prepare.read_rows(path)


PILOT_CSV = fixtures.DATA / "cost_100.csv"


class Finding2PilotCanBeReentered(StagedCase):
    """The paid pilot must be able to pick up where it stopped, and must know a planned stop from any other."""

    def setUp(self):
        super().setUp()
        self.state = self.dir / "state.sqlite"
        self.cost = self.dir / "cost"
        self.cost.mkdir()
        for name in ("rates.csv", "local_compute.csv", "assumptions.csv", "text_volume.json"):
            shutil.copy2(fixtures.ROOT / "cost" / name, self.cost / name)

    def run_pipeline(self, *args):
        return run_cli("run", *args, "--standin", "--state", self.state)

    def steps(self):
        from cost import evidence

        db = state.connect(self.state, synchronous="OFF")
        try:
            return evidence.pilot_steps(db, "cold", "warm")
        finally:
            db.close()

    def pilot(self, *extra):
        return subprocess.run(
            [sys.executable, "-m", "cost", "pilot", "--standin", "--state", str(self.state), "--dir", str(self.cost), "--cold", "cold", "--warm", "warm", *extra],
            cwd=fixtures.ROOT, capture_output=True, text=True,
        )  # fmt: skip

    def test_a_fresh_pilot_plans_the_stopped_start_the_resume_and_the_warm_pass(self):
        self.assertEqual(self.steps(), ["cold_start", "cold_resume", "warm"])

    def test_after_the_planned_stop_only_the_resume_and_the_warm_pass_are_left(self):
        self.run_pipeline("--run", "cold", "--new", "--input", PILOT_CSV, "--stop-after", "50")
        self.assertEqual(self.steps(), ["cold_resume", "warm"])

    def test_a_start_that_completed_nothing_is_started_again_with_its_stop(self):
        """An outage at the first request leaves no completed review, so there is no boundary to resume across yet."""
        self.run_pipeline("--run", "cold", "--new", "--input", PILOT_CSV, "--stop-after", "50")
        db = state.connect(self.state, synchronous="OFF")
        db.execute("UPDATE reviews SET status='pending', completed_session=NULL WHERE run='cold'")
        db.execute("DELETE FROM results WHERE run='cold'")
        db.close()
        self.assertEqual(self.steps(), ["cold_restart", "cold_resume", "warm"])

    def test_a_finished_cold_run_leaves_only_the_warm_pass_and_a_finished_pair_leaves_nothing(self):
        self.run_pipeline("--run", "cold", "--new", "--input", PILOT_CSV, "--stop-after", "50")
        self.run_pipeline("--run", "cold")
        self.assertEqual(self.steps(), ["warm"])
        self.run_pipeline("--run", "warm", "--new", "--input", PILOT_CSV, "--warm-from", "cold")
        self.assertEqual(self.steps(), [])

    def test_a_cold_run_that_was_never_stopped_cannot_be_the_pilot(self):
        from cost import evidence

        self.run_pipeline("--run", "cold", "--new", "--input", PILOT_CSV)
        with self.assertRaises(evidence.BadPilot) as caught:
            self.steps()
        self.assertIn("--cold", str(caught.exception))

    def test_the_pilot_command_can_be_run_again_after_it_finished(self):
        first = self.pilot()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        again = self.pilot()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertTrue((self.cost / "usage.csv").exists())

    def test_the_pilot_command_finishes_a_pilot_that_was_cut_off_after_its_first_step(self):
        self.run_pipeline("--run", "cold", "--new", "--input", PILOT_CSV, "--stop-after", "50")
        done = self.pilot()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.steps(), [])
        self.assertTrue((self.cost / "pilot_calls.jsonl").exists())

    def test_the_evidence_can_be_written_on_its_own_from_finished_runs(self):
        self.run_pipeline("--run", "cold", "--new", "--input", PILOT_CSV, "--stop-after", "50")
        self.run_pipeline("--run", "cold")
        self.run_pipeline("--run", "warm", "--new", "--input", PILOT_CSV, "--warm-from", "cold")
        done = subprocess.run(
            [sys.executable, "-m", "cost", "evidence", "--state", str(self.state), "--dir", str(self.cost), "--cold", "cold", "--warm", "warm"],
            cwd=fixtures.ROOT, capture_output=True, text=True,
        )  # fmt: skip
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.cost / "pilot_records.jsonl").exists())


class Finding7RowCount(unittest.TestCase):
    """The instructor changes the projected row count. The report must stay consistent with itself."""

    @classmethod
    def setUpClass(cls):
        from tests import test_cost

        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = test_cost.make_pilot(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def replay(self, *args):
        done = subprocess.run([sys.executable, "-m", "cost", "replay", "--dir", str(self.dir), *args], cwd=fixtures.ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-1500:])
        return (self.dir / "report.md").read_text()

    def test_changing_only_the_row_count_scales_the_counts_that_depend_on_it(self):
        report = self.replay("--rows", "1000")
        section = report.split("## Estimated before the full run")[1]
        self.assertIn("All 1,000 rows accounted for; 1,000 nonempty outputs; 0 empty-text quarantines", section)
        self.assertNotIn("660,609", section)
        self.assertNotIn("484,189", section)
        self.assertNotRegex(section, r"-\d[\d,]* empty-text")
        self.assertIn("733", section)  # 1,000 rows at the full file's share of distinct texts
        self.assertIn("scaled to this row count", section)

    def test_the_full_files_own_counts_are_used_when_nothing_is_changed(self):
        section = self.replay().split("## Estimated before the full run")[1]
        self.assertIn("All 660,622 rows accounted for; 660,609 nonempty outputs; 13 empty-text quarantines", section)
        self.assertIn("484,189", section)
        self.assertNotIn("scaled to this row count", section)

    def test_counts_given_by_hand_are_kept_as_given(self):
        section = self.replay("--rows", "1000", "--nonempty", "990", "--distinct", "900").split("## Estimated before the full run")[1]
        self.assertIn("All 1,000 rows accounted for; 990 nonempty outputs; 10 empty-text quarantines", section)
        self.assertIn("| 900 |", section)

    def test_an_assumptions_file_with_only_its_row_count_edited_is_scaled_too(self):
        from cost import calc

        inputs = calc.load(self.dir)
        inputs["assumptions"] = [{**r, "value": "1000"} if r["item"] == "rows" else r for r in inputs["assumptions"]]
        plan = calc.projection_inputs(inputs)
        self.assertEqual((plan["rows"], plan["nonempty"], plan["distinct"]), (1000, 1000, 733))

    def test_counts_that_cannot_be_true_together_are_refused(self):
        done = subprocess.run([sys.executable, "-m", "cost", "replay", "--dir", str(self.dir), "--rows", "100", "--nonempty", "500"], cwd=fixtures.ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("nonempty", done.stdout)


if __name__ == "__main__":
    unittest.main()
