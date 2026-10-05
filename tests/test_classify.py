import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from pipeline import classify, jev, ledger, limits, prepare, standins, state
from tests import fixtures

SAVED = fixtures.PROBE / "simple.jsonl"
FAST = (0, 0, 0)  # no waiting between retries


class ClassifyCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.billing = fixtures.write_billing(self.dir / "billing.json")
        self.setup_ = jev.load_setup(fixtures.ROOT / "prompts", 0.7)

    def make(self, rows=None, name="state"):
        folder = self.dir / name
        folder.mkdir()
        db = fixtures.prepared_db(folder, rows if rows is not None else fixtures.synthetic_rows(30, empties=2, copies=5))
        self.addCleanup(db.close)
        return db

    def go(self, db, labeler, *, cap="25", setup=None, **options):
        options.setdefault("backoff", FAST)
        return classify.run(
            db, "r1", labeler, ledger=ledger.Ledger(db, self.billing, cap_usd=Decimal(cap)),
            limiter=limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9), setup=setup or self.setup_, **options,
        )  # fmt: skip

    @staticmethod
    def reviews(db):
        return {r["review_id"]: r for r in db.execute("SELECT * FROM reviews WHERE run='r1'")}

    @staticmethod
    def originals(db):
        return db.execute(
            "SELECT * FROM reviews WHERE run='r1' AND cache_source_id IS NULL AND status!='quarantined' ORDER BY run_order"
        ).fetchall()

    @staticmethod
    def calls(db, review_id=None):
        rows = db.execute("SELECT * FROM calls WHERE run='r1' ORDER BY rowid").fetchall()
        return [c for c in rows if review_id is None or json.loads(c["review_ids_json"]) == [review_id]]

    @staticmethod
    def labels_by_text(db):
        return {
            r["text_key"]: (r["topic"], r["intent"], r["severity"], r["sentiment"], r["evidence_quote"], r["needs_review"])
            for r in db.execute("SELECT * FROM results WHERE run='r1'")
        }


class HappyPath(ClassifyCase):
    def setUp(self):
        super().setUp()
        self.db = self.make()
        self.labeler = standins.ReplayJev(SAVED)
        self.out = self.go(self.db, self.labeler)

    def test_everything_nonempty_completes(self):
        self.assertEqual((self.out.ended_how, self.out.completed, self.out.pending, self.out.quarantined), ("finished", 28, 0, 2))

    def test_every_copy_is_completed_with_its_original_in_the_same_session(self):
        got = self.reviews(self.db)
        copies = [r for r in got.values() if r["cache_source_id"]]
        self.assertEqual(len(copies), 5)
        for copy in copies:
            original = got[copy["cache_source_id"]]
            self.assertEqual((copy["status"], copy["completed_session"]), ("completed", original["completed_session"]))

    def test_each_distinct_text_is_sent_exactly_once(self):
        texts = [r["review_text"] for r in self.originals(self.db)]
        self.assertEqual(sorted(self.labeler.sent), sorted(texts))
        self.assertEqual(len(texts), 23)

    def test_every_call_is_a_succeeded_enrich_call_with_usage_and_the_runs_label_config(self):
        calls = self.calls(self.db)
        self.assertEqual(len(calls), 23)
        self.assertEqual({(c["role"], c["outcome"], c["usage_known"], c["model"]) for c in calls}, {("enrich", "succeeded", 1, "jev-1.13.0")})
        self.assertEqual({c["label_config"] for c in calls}, {self.setup_.label_config})
        self.assertEqual(len({c["request_id"] for c in calls}), 23)

    def test_originals_are_sent_in_run_order_with_one_worker(self):
        self.assertEqual(self.labeler.sent, [r["review_text"] for r in self.originals(self.db)])

    def test_the_session_is_closed_as_finished(self):
        row = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (self.out.session_id,)).fetchone()
        self.assertEqual((row["stage"], row["ended_how"]), ("classify", "finished"))
        self.assertIsNotNone(row["ended_mono"])

    def test_spend_is_the_usage_of_the_calls_and_nothing_is_left_reserved(self):
        led = ledger.Ledger(self.db, self.billing)
        tokens = sum(c["input_tokens"] + c["output_tokens"] for c in self.calls(self.db))
        self.assertEqual(led.spent_usd(), tokens * Decimal("0.042") / 1_000_000)
        self.assertEqual(led.reserved_usd(), 0)

    def test_a_second_run_sends_nothing(self):
        again = standins.ReplayJev(SAVED)
        out = self.go(self.db, again)
        self.assertEqual((out.ended_how, again.sent), ("finished", []))


class Failures(ClassifyCase):
    def first(self, db, n=0):
        return self.originals(db)[n]

    def test_a_temporary_error_is_retried_and_then_succeeds(self):
        db = self.make()
        target = self.first(db, 3)
        out = self.go(db, standins.ReplayJev(SAVED, script={target["review_text"]: ["temporary"]}))
        self.assertEqual(out.ended_how, "finished")
        calls = self.calls(db, target["review_id"])
        self.assertEqual([(c["outcome"], c["usage_known"]) for c in calls], [("failed", 0), ("succeeded", 1)])
        self.assertEqual(self.reviews(db)[target["review_id"]]["status"], "completed")

    def test_a_review_that_keeps_failing_returns_to_pending_and_is_never_quarantined(self):
        db = self.make()
        target = self.first(db, 3)
        out = self.go(db, standins.ReplayJev(SAVED, script={target["review_text"]: ["temporary"] * 8}))
        self.assertEqual((out.ended_how, out.pending), ("stuck", 1))
        self.assertEqual(out.stuck, [target["review_id"]])
        row = self.reviews(db)[target["review_id"]]
        self.assertEqual((row["status"], row["reason"], row["attempts"]), ("pending", None, 2))
        self.assertEqual([c["outcome"] for c in self.calls(db, target["review_id"])], ["failed"] * 8)
        self.assertEqual(out.completed, 27)

    def test_an_invalid_answer_is_retried_once_and_a_valid_retry_completes(self):
        db = self.make()
        target = self.first(db, 2)
        out = self.go(db, standins.ReplayJev(SAVED, script={target["review_text"]: ["invalid"]}))
        self.assertEqual(out.ended_how, "finished")
        calls = self.calls(db, target["review_id"])
        self.assertEqual([(c["outcome"], c["usage_known"]) for c in calls], [("failed", 1), ("succeeded", 1)])
        self.assertIn("topic", calls[0]["error"])

    def test_an_invalid_answer_twice_quarantines_the_review_and_its_copies(self):
        db = self.make()
        shared = db.execute(
            "SELECT * FROM reviews o WHERE cache_source_id IS NULL AND EXISTS (SELECT 1 FROM reviews c WHERE c.cache_source_id=o.review_id)"
        ).fetchone()
        out = self.go(db, standins.ReplayJev(SAVED, script={shared["review_text"]: ["invalid", "invalid"]}))
        self.assertEqual(out.ended_how, "finished")
        family = [r for r in self.reviews(db).values() if r["text_key"] == shared["text_key"]]
        self.assertGreater(len(family), 1)
        self.assertEqual({(r["status"], r["reason"]) for r in family}, {("quarantined", "invalid_model_output")})
        self.assertEqual(len(self.calls(db, shared["review_id"])), 2)
        self.assertEqual(out.quarantined, 2 + len(family))

    def test_a_paid_invalid_answer_still_counts_as_spend(self):
        db = self.make()
        target = self.first(db, 2)
        self.go(db, standins.ReplayJev(SAVED, script={target["review_text"]: ["invalid", "invalid"]}))
        tokens = sum(c["input_tokens"] + c["output_tokens"] for c in self.calls(db))
        self.assertEqual(ledger.Ledger(db, self.billing).spent_usd(), tokens * Decimal("0.042") / 1_000_000)

    def test_a_response_from_another_model_halts_and_changes_no_status(self):
        db = self.make()
        target = self.first(db, 4)
        labeler = standins.ReplayJev(SAVED, script={target["review_text"]: ["wrong_model"]})
        out = self.go(db, labeler)
        self.assertEqual(out.ended_how, "fatal")
        got = self.reviews(db)
        self.assertEqual(got[target["review_id"]]["status"], "pending")
        self.assertEqual(sum(r["status"] == "quarantined" for r in got.values()), 2)
        self.assertEqual(len(labeler.sent), 5)
        call = self.calls(db, target["review_id"])[-1]
        self.assertEqual(call["outcome"], "failed")
        self.assertIn("jev-9.9.9", call["error"])

    def test_a_fatal_response_halts_and_changes_no_status(self):
        db = self.make()
        target = self.first(db, 1)
        labeler = standins.ReplayJev(SAVED, script={target["review_text"]: ["fatal"]})
        out = self.go(db, labeler)
        self.assertEqual((out.ended_how, len(labeler.sent)), ("fatal", 2))
        self.assertEqual(self.reviews(db)[target["review_id"]]["status"], "pending")
        self.assertEqual(out.new_completions, 1)

    def test_a_review_over_jevs_limits_is_quarantined_and_never_sent(self):
        rows = fixtures.synthetic_rows(10, empties=0, copies=0)
        rows[4]["review_text"] = "word " * 20_000
        db = self.make(rows)
        labeler = standins.ReplayJev(SAVED)
        out = self.go(db, labeler)
        self.assertEqual((out.ended_how, out.quarantined, out.completed), ("finished", 1, 9))
        row = self.reviews(db)[rows[4]["review_id"]]
        self.assertEqual((row["status"], row["reason"]), ("quarantined", "request_over_limit"))
        self.assertNotIn(rows[4]["review_text"], labeler.sent)
        self.assertEqual(self.calls(db, rows[4]["review_id"]), [])


class Stops(ClassifyCase):
    def test_stop_after_leaves_work_pending_and_the_next_run_sends_no_completed_text_again(self):
        db = self.make()
        labeler = standins.ReplayJev(SAVED)
        first = self.go(db, labeler, stop_after=10)
        self.assertEqual(first.ended_how, "stop_after")
        self.assertGreaterEqual(first.new_completions, 10)
        self.assertGreater(first.pending, 0)
        second = self.go(db, labeler)
        self.assertEqual((second.ended_how, second.pending), ("finished", 0))
        self.assertEqual(len(labeler.sent), len(set(labeler.sent)))
        self.assertEqual(len(labeler.sent), 23)
        self.assertNotEqual(first.session_id, second.session_id)

    def test_the_cap_stops_admission_before_the_request_that_would_pass_it(self):
        db = self.make()
        labeler = standins.ReplayJev(SAVED)
        sizes = [len(jev.body_bytes(jev.build_request(r["review_text"], self.setup_.prompt))) for r in self.originals(db)]
        room_for_three = Decimal(sum(sizes[:3]) + 1) * Decimal("0.042") / 1_000_000
        out = self.go(db, labeler, cap=str(room_for_three))
        self.assertEqual(out.ended_how, "cap")
        self.assertLess(len(labeler.sent), 23)
        led = ledger.Ledger(db, self.billing, cap_usd=room_for_three)
        self.assertLessEqual(led.spent_usd() + led.reserved_usd(), room_for_three)
        self.assertEqual(len(self.calls(db)), len(labeler.sent))

    def test_a_set_stop_event_ends_the_session_as_interrupted_and_resume_finishes(self):
        db = self.make()
        stop = threading.Event()

        class StopsAfterFive(standins.ReplayJev):
            def label(self, text, request):
                if len(self.sent) == 4:
                    stop.set()
                return super().label(text, request)

        labeler = StopsAfterFive(SAVED)
        out = self.go(db, labeler, stop_event=stop)
        self.assertEqual(out.ended_how, "interrupted")
        self.assertEqual(out.new_completions, len(labeler.sent))
        self.assertGreater(out.pending, 0)
        stop.clear()
        self.assertEqual(self.go(db, labeler, stop_event=stop).ended_how, "finished")
        self.assertEqual(len(labeler.sent), len(set(labeler.sent)))

    def test_the_time_box_ends_the_session(self):
        db = self.make()
        clock = fixtures.FakeClock()

        class AnHourEach(standins.ReplayJev):
            def label(self, text, request):
                clock.advance(3600)
                return super().label(text, request)

        out = self.go(db, AnHourEach(SAVED), clock=clock, max_hours=2.5)
        self.assertEqual(out.ended_how, "time_box")
        self.assertEqual(out.new_completions, 3)
        self.assertGreater(out.pending, 0)

    def test_16_workers_give_the_same_labels_as_one(self):
        one, sixteen = self.make(name="one"), self.make(name="sixteen")
        self.go(one, standins.ReplayJev(SAVED))
        out = self.go(sixteen, standins.ReplayJev(SAVED, latency=0.002), workers=16)
        self.assertEqual(out.ended_how, "finished")
        self.assertEqual(self.labels_by_text(sixteen), self.labels_by_text(one))
        self.assertEqual({r["status"] for r in self.reviews(sixteen).values()}, {"completed", "quarantined"})


class Sleep(ClassifyCase):
    """Review Focus 4: the laptop sleeps with requests in flight."""

    def test_a_long_pause_ends_the_session_cleanly_and_the_next_run_finishes(self):
        db = self.make()
        clock = fixtures.FakeClock()
        asleep = {"done": False}

        class SleepsOnSixth(standins.ReplayJev):
            def label(self, text, request):
                if len(self.sent) == 5 and not asleep["done"]:
                    asleep["done"] = True
                    self.sent.append(text)
                    clock.advance(2 * 3600)  # the lid closed; the request times out on waking
                    raise jev.Temporary("timed out")
                return super().label(text, request)

        labeler = SleepsOnSixth(SAVED)
        out = self.go(db, labeler, clock=clock)
        self.assertEqual(out.ended_how, "no_success_60s")
        self.assertEqual(out.new_completions, 5)
        row = db.execute("SELECT ended_how FROM sessions WHERE session_id=?", (out.session_id,)).fetchone()
        self.assertEqual(row["ended_how"], "no_success_60s")
        again = self.go(db, labeler, clock=clock)
        self.assertEqual((again.ended_how, again.pending), ("finished", 0))
        self.assertEqual(again.completed, 28)


class Copies(ClassifyCase):
    def test_a_text_with_two_copies_fails_a_run_then_succeeds_with_its_copies_intact(self):
        rows = fixtures.synthetic_rows(12, empties=0, copies=0)
        rows[5]["review_text"] = rows[9]["review_text"] = rows[2]["review_text"]
        db = self.make(rows)
        text = rows[2]["review_text"]
        labeler = standins.ReplayJev(SAVED, script={text: ["temporary"] * 8})
        first = self.go(db, labeler)
        self.assertEqual((first.ended_how, first.pending), ("stuck", 3))
        second = self.go(db, labeler)
        self.assertEqual((second.ended_how, second.pending, second.completed), ("finished", 0, 12))
        family = sorted((r for r in self.reviews(db).values() if r["review_text"] == text), key=lambda r: r["run_order"])
        original, *copies = family
        self.assertEqual(len(copies), 2)
        self.assertEqual({c["cache_source_id"] for c in copies}, {original["review_id"]})
        self.assertEqual({r["status"] for r in family}, {"completed"})
        outcomes = [c["outcome"] for c in self.calls(db, original["review_id"])]
        self.assertEqual((outcomes.count("succeeded"), outcomes.count("failed")), (1, 8))
        for copy in copies:
            self.assertEqual(self.calls(db, copy["review_id"]), [])
        self.assertEqual(labeler.sent.count(text), 9)


class OneTopic:
    """A labeler that gives every review the same topic, with confidence that alternates."""

    def __init__(self):
        self.n = 0

    def label(self, text, request):
        self.n += 1
        p = 0.9 if self.n % 2 else 0.5
        answers = {}
        for name, choice in (("topic", "playback"), ("intent", "complaint"), ("severity", "degraded")):
            options = list(request["questions"][name]["criteria"])
            answers[name] = {"choice": choice, "probabilities": {o: (p if o == choice else (1 - p) / (len(options) - 1)) for o in options}}
        answers["tone"] = {"score": 1.0}
        return jev.Reply(answer=answers, model=jev.MODEL, input_tokens=900, output_tokens=200, http_status=200)


class Guards(ClassifyCase):
    def big(self, name="big"):
        return self.make(fixtures.synthetic_rows(520, empties=0, copies=0), name=name)

    def test_under_500_reviews_no_guard_applies(self):
        db = self.make()
        self.assertEqual(self.go(db, standins.ReplayJev(SAVED)).ended_how, "finished")

    def test_one_topic_on_more_than_95_percent_raises_and_names_itself(self):
        db = self.big()
        with self.assertRaises(classify.GuardFailed) as caught:
            self.go(db, OneTopic(), workers=8)
        self.assertEqual(caught.exception.names, ["one_topic_over_95"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM results").fetchone()[0], 520)

    def test_needs_review_all_false_raises(self):
        db = self.big()
        with self.assertRaises(classify.GuardFailed) as caught:
            self.go(db, standins.ReplayJev(SAVED), workers=8)
        self.assertEqual(caught.exception.names, ["needs_review_all_false"])

    def test_needs_review_all_true_raises(self):
        db = self.big()
        strict = jev.load_setup(fixtures.ROOT / "prompts", 0.95)
        with self.assertRaises(classify.GuardFailed) as caught:
            self.go(db, standins.ReplayJev(SAVED), workers=8, setup=strict)
        self.assertEqual(caught.exception.names, ["needs_review_all_true"])

    def test_another_input_can_accept_a_guard_by_name_and_that_is_logged(self):
        db = self.big()
        out = self.go(db, standins.ReplayJev(SAVED), workers=8, accept_guards=("needs_review_all_false",))
        self.assertEqual(out.ended_how, "finished")
        configs = json.loads(db.execute("SELECT configs_json FROM runs WHERE run='r1'").fetchone()[0])
        self.assertEqual([g["guard"] for g in configs["accepted_guards"]], ["needs_review_all_false"])

    def test_accepting_one_guard_does_not_accept_another(self):
        db = self.big()
        with self.assertRaises(classify.GuardFailed) as caught:
            self.go(db, standins.ReplayJev(SAVED), workers=8, accept_guards=("one_topic_over_95",))
        self.assertEqual(caught.exception.names, ["needs_review_all_false"])

    def test_the_supplied_files_cannot_accept_a_guard(self):
        db = self.big()
        with mock.patch.object(prepare, "supplied_hashes", return_value={fixtures.RUN_ARGS["input_sha256"]}):
            with self.assertRaises(classify.GuardFailed) as caught:
                self.go(db, standins.ReplayJev(SAVED), workers=8, accept_guards=("needs_review_all_false",))
        self.assertTrue(caught.exception.supplied)

    def test_the_supplied_hashes_are_the_manifests(self):
        hashes = prepare.supplied_hashes()
        self.assertIn(prepare.SUPPLIED["sha256"], hashes)
        self.assertIn(fixtures.checker().sha(fixtures.DATA / "cost_100.csv"), hashes)
        self.assertEqual(len(hashes), 5)


class Crash(ClassifyCase):
    def test_a_killed_run_recovers_its_orphans_and_finishes_without_sending_a_completed_text_again(self):
        db = self.make(fixtures.synthetic_rows(40, empties=0, copies=0))
        log = self.dir / "sent.log"
        child = subprocess.Popen(
            [sys.executable, str(fixtures.ROOT / "tests/crash_child.py"), str(self.dir / "state/state.sqlite"), str(self.billing), str(log)]
        )
        deadline = time.time() + 30
        while time.time() < deadline and (not log.exists() or len(log.read_text().splitlines()) < 10):
            time.sleep(0.02)
        os.kill(child.pid, signal.SIGKILL)
        child.wait()
        done_at_kill = {r["review_text"] for r in db.execute("SELECT review_text FROM reviews WHERE status='completed'")}
        open_at_kill = db.execute("SELECT COUNT(*) FROM calls WHERE outcome='pending'").fetchone()[0]
        self.assertGreater(open_at_kill, 0)
        self.assertLess(len(done_at_kill), 40)

        labeler = standins.ReplayJev()
        out = self.go(db, labeler, workers=4)
        self.assertEqual((out.ended_how, out.completed), ("finished", 40))
        self.assertFalse(done_at_kill & set(labeler.sent))
        orphans = db.execute("SELECT * FROM calls WHERE error LIKE 'the process ended%'").fetchall()
        self.assertEqual(len(orphans), open_at_kill)
        self.assertEqual({(c["outcome"], c["usage_known"]) for c in orphans}, {("failed", 0)})
        kept = db.execute("SELECT COUNT(*) FROM ledger WHERE kind='kept'").fetchone()[0]
        self.assertEqual(kept, open_at_kill)
        crashed = db.execute("SELECT ended_how FROM sessions ORDER BY session_id").fetchall()
        self.assertEqual([s["ended_how"] for s in crashed], ["crashed", "finished"])


if __name__ == "__main__":
    unittest.main()
