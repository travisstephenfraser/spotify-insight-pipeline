"""Tests added in the fix pass after the final whole-branch review. Each names the finding it pins."""

import contextlib
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from pipeline import classify, cli, group, jev, ledger, limits, memo, standins, state
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

    def test_an_adjustment_needs_a_note(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["adjust", "--usd", "0.25", "--state", str(self.state)])


if __name__ == "__main__":
    unittest.main()
