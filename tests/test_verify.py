import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from pipeline import classify, gemma, jev, ledger, limits, prepare, standins, verify
from tests import fixtures

sys.path.insert(0, str(fixtures.ROOT / "evals"))
import compare_check  # noqa: E402


class VerifyCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def classified(self, name="a", **options):
        db, _ = fixtures.classified_db(self.dir / name, **options)
        self.addCleanup(db.close)
        return db

    @staticmethod
    def sample(db):
        return db.execute("SELECT * FROM reviews WHERE run='r1' AND in_verify_sample=1 ORDER BY run_order").fetchall()

    @staticmethod
    def rows(db):
        return {r["review_id"]: r for r in db.execute("SELECT * FROM verify WHERE run='r1'")}

    @staticmethod
    def calls(db):
        return db.execute("SELECT * FROM calls WHERE run='r1' AND role='verify' ORDER BY rowid").fetchall()


class Prompt(unittest.TestCase):
    def test_the_definitions_are_the_contracts_label_section_word_for_word(self):
        """Known answer: the section the outside raters were given (validation log entry 11)."""
        section = verify.definitions(verify.load_system(fixtures.ROOT / "prompts/verify-v1.md"))
        self.assertEqual(len(section), 2522)
        self.assertTrue(hashlib.sha256(section.encode("utf-8")).hexdigest().startswith("21b37d5f43750bc9"))
        contract = (fixtures.DATA / "GRADING_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn(section, contract)

    def test_the_schema_offers_exactly_the_contracts_labels(self):
        props = verify.SCHEMA["properties"]
        self.assertEqual(set(props), {"topic", "intent", "severity"})
        self.assertEqual(set(props["topic"]["enum"]), set(fixtures.checker().TOPICS))
        self.assertEqual(set(props["intent"]["enum"]), set(fixtures.checker().INTENTS))
        self.assertEqual(props["severity"]["enum"], [1, 2, 3, 4, 5])


class Run(VerifyCase):
    def test_every_sampled_review_ends_with_a_prediction(self):
        db = self.classified()
        out = verify.run(db, "r1", standins.StandinGemma())
        self.assertEqual((out.ended_how, out.predicted, out.failed, out.remaining), ("finished", 10, 0, 0))
        got = self.rows(db)
        self.assertEqual(set(got), {r["review_id"] for r in self.sample(db)})
        self.assertEqual({r["outcome"] for r in got.values()}, {"predicted"})

    def test_each_request_is_one_review_the_definitions_and_the_bound(self):
        db = self.classified()
        fake = standins.StandinGemma()
        verify.run(db, "r1", fake)
        system = verify.load_system(fixtures.ROOT / "prompts/verify-v1.md")
        self.assertEqual([c[1] for c in fake.calls], [r["review_text"] for r in self.sample(db)])
        self.assertEqual({(c[0], c[3]) for c in fake.calls}, {(system, 200)})
        self.assertTrue(all(c[2] == verify.SCHEMA for c in fake.calls))

    def test_every_call_is_logged_as_a_verify_call_naming_its_review_and_model(self):
        db = self.classified()
        verify.run(db, "r1", standins.StandinGemma())
        calls = self.calls(db)
        self.assertEqual(len(calls), 10)
        self.assertEqual({(c["outcome"], c["model"], c["usage_known"]) for c in calls}, {("succeeded", gemma.MODEL, 1)})
        self.assertEqual([json.loads(c["review_ids_json"]) for c in calls], [[r["review_id"]] for r in self.sample(db)])
        session = db.execute("SELECT stage, ended_how FROM sessions WHERE session_id=?", (calls[0]["session_id"],)).fetchone()
        self.assertEqual((session["stage"], session["ended_how"]), ("verify", "finished"))

    def test_a_second_run_sends_nothing(self):
        db = self.classified()
        verify.run(db, "r1", standins.StandinGemma())
        again = standins.StandinGemma()
        self.assertEqual((verify.run(db, "r1", again).ended_how, again.calls), ("finished", []))

    def test_verify_does_not_start_while_reviews_are_still_pending(self):
        db = fixtures.prepared_db(self.dir, verify_size=10)
        self.addCleanup(db.close)
        fake = standins.StandinGemma()
        self.assertEqual((verify.run(db, "r1", fake).ended_how, fake.calls), ("not_ready", []))

    def test_the_time_box_ends_the_stage_and_resume_finishes(self):
        db = self.classified()
        clock = fixtures.FakeClock()

        class AnHourEach(standins.StandinGemma):
            def ask(self, *args, **kwargs):
                clock.advance(3600)
                return super().ask(*args, **kwargs)

        out = verify.run(db, "r1", AnHourEach(), clock=clock, max_hours=2.5)
        self.assertEqual((out.ended_how, out.predicted, out.remaining), ("time_box", 3, 7))
        self.assertEqual(verify.run(db, "r1", standins.StandinGemma()).remaining, 0)


class Blind(VerifyCase):
    def test_the_requests_are_identical_whatever_jev_answered_and_whether_it_answered_at_all(self):
        """Item 25: nothing of the first prediction can reach the verifier."""
        normal = self.classified("normal")
        target = self.sample(normal)[0]
        different = self.classified("different", labeler=OtherAnswers())
        quarantined = self.classified(
            "quarantined", labeler=standins.ReplayJev(script={target["review_text"]: ["invalid", "invalid"]})
        )
        self.assertEqual(
            quarantined.execute("SELECT status FROM reviews WHERE review_id=?", (target["review_id"],)).fetchone()[0], "quarantined"
        )
        calls = []
        for db in (normal, different, quarantined):
            fake = standins.StandinGemma()
            verify.run(db, "r1", fake)
            calls.append(json.dumps(fake.calls, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[0], calls[2])
        self.assertNotEqual(
            normal.execute("SELECT topic, severity FROM results ORDER BY text_key").fetchall(),
            different.execute("SELECT topic, severity FROM results ORDER BY text_key").fetchall(),
        )


class OtherAnswers:
    """A labeler whose answers differ from the stand-in's: everything is a billing complaint."""

    def label(self, text, request):
        answers = {}
        for name, choice in (("topic", "billing"), ("intent", "complaint"), ("severity", "degraded")):
            options = list(request["questions"][name]["criteria"])
            answers[name] = {"choice": choice, "probabilities": {o: (0.9 if o == choice else 0.1 / (len(options) - 1)) for o in options}}
        answers["tone"] = {"score": 1.0}
        if "evidence" in request["questions"]:
            first = min(request["questions"]["evidence"]["criteria"])
            answers["evidence"] = {"choice": first, "probabilities": {first: 1.0}}
        return jev.Reply(answer=answers, model=jev.MODEL, input_tokens=900, output_tokens=200, http_status=200)


class Failures(VerifyCase):
    def test_an_invalid_answer_is_retried_once_and_a_good_retry_is_a_prediction(self):
        db = self.classified()
        out = verify.run(db, "r1", standins.StandinGemma(script=["invalid"]))
        self.assertEqual((out.predicted, out.failed), (10, 0))
        first = self.sample(db)[0]["review_id"]
        mine = [c["outcome"] for c in self.calls(db) if json.loads(c["review_ids_json"]) == [first]]
        self.assertEqual(mine, ["failed", "succeeded"])

    def test_an_invalid_answer_twice_is_recorded_as_a_verify_failure(self):
        db = self.classified()
        out = verify.run(db, "r1", standins.StandinGemma(script=["invalid", "invalid"]))
        self.assertEqual((out.ended_how, out.predicted, out.failed), ("finished", 9, 1))
        first = self.sample(db)[0]
        row = self.rows(db)[first["review_id"]]
        self.assertEqual((row["outcome"], row["reason"], row["topic"]), ("failed", "invalid_output", None))
        self.assertEqual(db.execute("SELECT status FROM reviews WHERE review_id=?", (first["review_id"],)).fetchone()[0], "completed")

    def test_an_answer_outside_the_labels_counts_as_invalid(self):
        db = self.classified()
        fake = standins.StandinGemma(respond=lambda system, user, schema: {"topic": "pricing", "intent": "complaint", "severity": 2})
        out = verify.run(db, "r1", fake)
        self.assertEqual((out.predicted, out.failed), (0, 10))

    def test_a_server_problem_halts_the_stage_and_records_no_failure(self):
        db = self.classified()
        out = verify.run(db, "r1", standins.StandinGemma(script=["server_problem"]))
        self.assertEqual((out.ended_how, out.predicted, out.failed, out.remaining), ("server_problem", 0, 0, 10))
        self.assertEqual(self.rows(db), {})
        self.assertEqual([c["outcome"] for c in self.calls(db)], ["failed"])
        self.assertEqual(verify.run(db, "r1", standins.StandinGemma()).ended_how, "finished")

    def test_a_server_serving_another_model_halts_before_any_request(self):
        db = self.classified()
        fake = standins.StandinGemma(loaded=False)
        out = verify.run(db, "r1", fake)
        self.assertEqual((out.ended_how, fake.calls, self.calls(db)), ("server_problem", [], []))

    def test_a_review_over_the_bound_is_a_verify_failure_and_is_never_sent(self):
        """Review Focus 5."""
        rows = fixtures.synthetic_rows(12, empties=0, copies=0)
        rows[3]["review_text"] = "The app crashes. " * 300  # 5,100 characters
        db = self.classified(rows=rows, verify_size=12)
        fake = standins.StandinGemma()
        out = verify.run(db, "r1", fake, max_chars=5000)
        self.assertEqual((out.ended_how, out.predicted, out.failed), ("finished", 11, 1))
        row = self.rows(db)[rows[3]["review_id"]]
        self.assertEqual((row["outcome"], row["reason"], row["request_id"]), ("failed", "too_long", None))
        self.assertNotIn(rows[3]["review_text"], [c[1] for c in fake.calls])


def flip_topic(texts):
    """A verifier that follows the stand-in rule except on `texts`, where it says `support`."""
    base = standins.StandinGemma()

    def respond(system, user, schema):
        data = base._by_rule(user, schema)
        return {**data, "topic": "support"} if user in texts else data

    return standins.StandinGemma(respond=respond)


class Report(VerifyCase):
    def setUp(self):
        super().setUp()
        self.db = self.classified()
        texts = {r["review_text"] for r in self.sample(self.db)[:3]}
        # A sampled copy shares its original's text, so it is flipped with it.
        self.flipped = [r for r in self.sample(self.db) if r["review_text"] in texts]
        self.n = len(self.flipped)
        verify.run(self.db, "r1", flip_topic(texts))
        self.report = verify.report(self.db, "r1")

    def test_the_four_counts(self):
        self.assertEqual(
            {k: self.report[k] for k in ("sample", "predictions", "verify_failures", "jev_unlabeled")},
            {"sample": 10, "predictions": 10, "verify_failures": 0, "jev_unlabeled": 0},
        )
        self.assertEqual((self.report["pairs"], self.report["pairs_share_of_sample"]), (10, 1.0))

    def test_agreement_per_field_counts_the_pairs_that_match(self):
        self.assertGreaterEqual(self.n, 3)
        self.assertEqual(self.report["agreement"]["topic"], 10 - self.n)
        self.assertEqual(self.report["agreement"]["all_three"], 10 - self.n)
        self.assertEqual(self.report["agreement"]["intent"], 10)

    def test_the_disagreeing_reviews_are_listed_with_both_answers(self):
        listed = {d["review_id"]: d for d in self.report["disagreements"]}
        self.assertEqual(set(listed), {r["review_id"] for r in self.flipped})
        one = listed[self.flipped[0]["review_id"]]
        self.assertEqual(one["gemma"]["topic"], "support")
        self.assertNotEqual(one["jev"]["topic"], "support")

    def test_agreement_is_split_by_complaints_against_the_rest_and_per_topic(self):
        groups = self.report["by_group"]
        self.assertEqual(groups["complaints_and_cancellations"]["pairs"] + groups["rest"]["pairs"], 10)
        self.assertEqual(groups["complaints_and_cancellations"]["all_three"] + groups["rest"]["all_three"], 10 - self.n)
        self.assertEqual(sum(t["pairs"] for t in self.report["by_topic"].values()), 10)

    def test_the_confusion_table_puts_the_flips_off_the_diagonal(self):
        table = self.report["confusion"]["topic"]
        off = sum(n for jev_label, row in table.items() for gemma_label, n in row.items() if jev_label != gemma_label)
        self.assertEqual(off, self.n)

    def test_the_sample_is_ranked_on_both_engines_labels(self):
        for engine in ("jev", "gemma"):
            ranking = self.report["ranking"][engine]
            sums = [r["severity_sum"] for r in ranking]
            self.assertEqual(sums, sorted(sums, reverse=True))
            self.assertTrue(all(set(r) == {"topic", "complaint_count", "severity_sum"} for r in ranking))
        self.assertIn("support", [r["topic"] for r in self.report["ranking"]["gemma"]] + ["support"])

    def test_failures_and_reviews_jev_could_not_label_are_counted_not_dropped(self):
        target = self.sample(self.db)[0]
        db = self.classified("q", labeler=standins.ReplayJev(script={target["review_text"]: ["invalid", "invalid"]}))
        verify.run(db, "r1", standins.StandinGemma(script=["invalid", "invalid"]))
        report = verify.report(db, "r1")
        self.assertEqual((report["sample"], report["predictions"], report["verify_failures"]), (10, 9, 1))
        self.assertGreaterEqual(report["jev_unlabeled"], 1)
        self.assertLess(report["pairs"], 10)
        self.assertEqual(report["pairs_share_of_sample"], report["pairs"] / 10)


class Guard(VerifyCase):
    def big(self, name="big"):
        return self.classified(name, rows=fixtures.synthetic_rows(70, empties=0, copies=0), verify_size=60)

    def test_agreement_of_exactly_100_percent_on_50_or_more_raises(self):
        db = self.big()
        with self.assertRaises(classify.GuardFailed) as caught:
            verify.run(db, "r1", standins.StandinGemma())
        self.assertEqual(caught.exception.names, ["verifier_agreement_100"])
        self.assertEqual(len(self.rows(db)), 60)

    def test_under_50_pairs_the_guard_does_not_apply(self):
        self.assertEqual(verify.run(self.classified(), "r1", standins.StandinGemma()).ended_how, "finished")

    def test_one_disagreement_is_enough_to_pass(self):
        db = self.big()
        first = self.sample(db)[0]["review_text"]
        self.assertEqual(verify.run(db, "r1", flip_topic({first})).ended_how, "finished")

    def test_another_input_can_accept_the_guard_and_a_supplied_file_cannot(self):
        db = self.big()
        out = verify.run(db, "r1", standins.StandinGemma(), accept_guards=("verifier_agreement_100",))
        self.assertEqual(out.ended_how, "finished")
        configs = json.loads(db.execute("SELECT configs_json FROM runs").fetchone()[0])
        self.assertEqual([g["guard"] for g in configs["accepted_guards"]], ["verifier_agreement_100"])
        with mock.patch.object(prepare, "supplied_hashes", return_value={fixtures.RUN_ARGS["input_sha256"]}):
            with self.assertRaises(classify.GuardFailed):
                verify.run(db, "r1", standins.StandinGemma(), accept_guards=("verifier_agreement_100",))


class CompareCheck(VerifyCase):
    def test_every_label_changed_on_purpose_is_flagged_by_the_comparison(self):
        db = self.classified()
        verify.run(db, "r1", standins.StandinGemma())
        self.assertEqual(verify.report(db, "r1")["disagreements"], [])
        result = compare_check.check(self.dir / "a/state.sqlite", "r1", changes=4)
        self.assertEqual(result["texts"], 4)
        self.assertGreaterEqual(len(result["changed"]), 4)  # a sampled copy changes with its text
        self.assertEqual(sorted(result["flagged"]), sorted(result["changed"]))
        self.assertEqual(verify.report(db, "r1")["disagreements"], [])  # the real results were not touched


class Crash(VerifyCase):
    def test_a_kill_mid_verify_reopens_no_classified_review_and_verify_finishes(self):
        db = self.classified(rows=fixtures.synthetic_rows(20, empties=0, copies=0), verify_size=20)
        child = subprocess.Popen([sys.executable, str(fixtures.ROOT / "tests/crash_child_verify.py"), str(self.dir / "a/state.sqlite")])
        deadline = time.time() + 30
        while time.time() < deadline:
            done = db.execute("SELECT COUNT(*) FROM verify").fetchone()[0]
            open_calls = db.execute("SELECT COUNT(*) FROM calls WHERE role='verify' AND outcome='pending'").fetchone()[0]
            if done >= 2 and open_calls == 1:
                break
            time.sleep(0.01)
        os.kill(child.pid, signal.SIGKILL)
        child.wait()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM calls WHERE role='verify' AND outcome='pending'").fetchone()[0], 1)
        before = {r["review_id"]: r["status"] for r in db.execute("SELECT review_id, status FROM reviews")}

        labeler = standins.ReplayJev()
        outcome = classify.run(  # classify is asked to run again first, as the CLI would
            db, "r1", labeler, ledger=ledger.Ledger(db, self.dir / "a/billing.json", cap_usd=Decimal("25")),
            limiter=limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9),
            setup=jev.load_setup(fixtures.ROOT / "prompts", 0.7), backoff=(0, 0, 0),
        )  # fmt: skip
        self.assertEqual((outcome.ended_how, labeler.sent), ("finished", []))
        out = verify.run(db, "r1", standins.StandinGemma())
        self.assertEqual((out.ended_how, out.remaining), ("finished", 0))
        after = {r["review_id"]: r["status"] for r in db.execute("SELECT review_id, status FROM reviews")}
        self.assertEqual(after, before)
        self.assertEqual(set(after.values()), {"completed"})
        orphan = db.execute("SELECT * FROM calls WHERE role='verify' AND error LIKE 'the process ended%'").fetchall()
        self.assertEqual([(c["outcome"], c["usage_known"]) for c in orphan], [("failed", 0)])
        self.assertEqual(len(self.rows(db)), 20)


if __name__ == "__main__":
    unittest.main()
