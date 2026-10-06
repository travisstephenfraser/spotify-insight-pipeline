import ast
import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

from pipeline import jev, labels, ledger, limits, standins, state
from tests import fixtures

sys.path.insert(0, str(fixtures.ROOT / "evals"))
import common  # noqa: E402
import cutoff_rows  # noqa: E402
import cutoff_table  # noqa: E402
import holdout_score  # noqa: E402
import planted_cases  # noqa: E402
import score_golden  # noqa: E402
import wording_trial  # noqa: E402


class KeyFollower:
    """A labeler that gives each planted case its first accepted answer, and everything else `unclear`."""

    def __init__(self, slogans_as=None):
        self.cases = {c["text"]: c for c in planted_cases.cases()}
        self.slogans_as = slogans_as
        self.sent = []

    def label(self, text, request):
        self.sent.append(text)
        case = self.cases.get(text)
        want = {"topic": "other", "intent": "unclear", "severity": 1}
        if case:
            want = {"topic": sorted(case["topics"])[0], "intent": sorted(case["intents"])[0], "severity": sorted(case["severities"])[0]}
            if self.slogans_as and case["group"] == "slogan":
                want["intent"] = self.slogans_as
        name = {v: k for k, v in labels.SEVERITY.items()}[want["severity"]]
        answers = {}
        for q, choice in (("topic", want["topic"]), ("intent", want["intent"]), ("severity", name)):
            options = list(request["questions"][q]["criteria"])
            answers[q] = {"choice": choice, "probabilities": {o: float(o == choice) for o in options}}
        answers["tone"] = {"score": 2.0}
        if "evidence" in request["questions"]:
            first = min(request["questions"]["evidence"]["criteria"])
            answers["evidence"] = {"choice": first, "probabilities": {first: 1.0}}
        return jev.Reply(answer=answers, model=jev.MODEL, input_tokens=900, output_tokens=200, http_status=200)


class EvalCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.db = state.connect(self.dir / "state.sqlite", synchronous="OFF")
        self.addCleanup(self.db.close)
        self.billing = fixtures.write_billing(self.dir / "billing.json")
        self.setup_ = jev.load_setup(fixtures.ROOT / "prompts", 0.7)

    def paid(self, labeler, cap="25", setup=None):
        fast = limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9)
        return common.Paid(self.db, ledger.Ledger(self.db, self.billing, cap_usd=Decimal(cap)), labeler, setup or self.setup_, "test", limiter=fast)


class Planted(EvalCase):
    def test_the_cases_are_the_25_written_for_the_2026_10_04_tests_unchanged(self):
        tree = ast.parse((fixtures.PROBE / "three_tests.py").read_text(encoding="utf-8"))
        original = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "CASES")
        mine = [(c["id"], c["group"], c["text"], c["topics"], c["intents"], c["severities"]) for c in planted_cases.cases()]
        self.assertEqual(mine, [tuple(c) for c in original])
        self.assertEqual(len(mine), 25)

    def test_a_labeler_that_follows_the_key_scores_25_of_25(self):
        result = planted_cases.score(self.paid(KeyFollower()).ask)
        self.assertEqual(result["right"], 25)
        self.assertEqual(result["by_group"]["slogan"], [4, 4])
        self.assertEqual(sum(total for _, total in result["by_group"].values()), 25)

    def test_calling_every_slogan_a_cancellation_gets_one_of_four(self):
        """Only S3, where the writer says they cancelled, is a cancellation."""
        result = planted_cases.score(self.paid(KeyFollower(slogans_as="cancellation")).ask)
        self.assertEqual(result["by_group"]["slogan"], [1, 4])
        wrong = [r["id"] for r in result["results"] if not r["right"]]
        self.assertEqual(sorted(wrong), ["S1", "S2", "S4"])


class PaidCalls(EvalCase):
    def test_every_eval_call_goes_through_the_ledger_and_the_call_log(self):
        labeler = KeyFollower()
        paid = self.paid(labeler)
        paid.ask("planted:S1", "Boycott Spotify")
        calls = self.db.execute("SELECT * FROM calls").fetchall()
        self.assertEqual([(c["run"], c["role"], c["outcome"], c["review_ids_json"]) for c in calls], [("evals", "enrich", "succeeded", '["planted:S1"]')])
        self.assertEqual(ledger.Ledger(self.db, self.billing).spent_usd(), Decimal(1100) * Decimal("0.042") / 1_000_000)

    def test_a_call_that_would_pass_the_cap_is_refused_before_it_is_sent(self):
        labeler = KeyFollower()
        paid = self.paid(labeler, cap="0.000001")
        with self.assertRaises(ledger.CapReached):
            paid.ask("planted:S1", "Boycott Spotify")
        self.assertEqual(labeler.sent, [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0], 0)

    def test_a_temporary_failure_is_retried_and_each_try_is_logged(self):
        paid = self.paid(standins.ReplayJev(script={"Boycott Spotify": ["temporary"]}))
        record = paid.ask("planted:S1", "Boycott Spotify")
        self.assertIn(record["intent"], labels.INTENTS)
        self.assertEqual([c["outcome"] for c in self.db.execute("SELECT outcome FROM calls ORDER BY rowid")], ["failed", "succeeded"])


class RefusedRequest(EvalCase):
    """A request the provider refuses for one item has no answer. The script must go on and nothing may stay reserved."""

    def test_a_refused_request_is_one_item_without_an_answer(self):
        paid = self.paid(standins.ReplayJev(script={"Boycott Spotify": ["rejected"]}))
        record = paid.ask("b1", "Boycott Spotify")
        self.assertIn("invalid", record)
        self.assertIn("refused", record["invalid"])
        rows = [tuple(r) for r in self.db.execute("SELECT outcome, http_status FROM calls ORDER BY rowid")]
        self.assertEqual(rows, [("failed", 400)])  # one try: the same request would be refused again
        self.assertEqual(paid.ledger.reserved_usd(), 0)
        self.assertNotIn("invalid", paid.ask("ok", "Great app"))


class OpeningSpend(unittest.TestCase):
    """The ledger starts with the Jev spend made before it existed, whichever real command touches it first."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def args(self, **over):
        import argparse

        base = dict(go=True, standin=False, state=str(self.dir / "state.sqlite"), prompt_file="enrich-v1.json", cutoff=0.7, cap="35")
        return argparse.Namespace(**{**base, **over})

    def opening_rows(self):
        db = state.connect(self.dir / "state.sqlite", synchronous="OFF")
        try:
            return db.execute("SELECT COUNT(*) FROM ledger WHERE kind='opening'").fetchone()[0]
        finally:
            db.close()

    def test_a_real_eval_on_a_new_state_file_records_the_earlier_probe_spend_once(self):
        import os
        from unittest import mock

        from pipeline import cli

        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "fake-key-for-tests-0123456789"}):
            for _ in range(2):
                with redirect_stdout(io.StringIO()), common.session(self.args(), "test") as paid:
                    self.assertEqual(paid.ledger.spent_usd(), sum(cli.OPENING_SPEND))
        self.assertEqual(self.opening_rows(), 2)  # one measured row and one estimated row, written once

    def test_a_stand_in_eval_records_no_opening_spend(self):
        with redirect_stdout(io.StringIO()), common.session(self.args(go=False, standin=True), "test") as paid:
            self.assertEqual(paid.ledger.spent_usd(), 0)


class CutoffRows(EvalCase):
    """The cut-off-half reviews the pilot does not cover: labeled once, with the frozen wording, for the cut-off table."""

    def pilot_ids(self):
        return {json.loads(line)["review_id"] for line in (fixtures.PROBE / "simple.jsonl").read_text().splitlines() if line.strip()}

    def test_the_missing_rows_are_the_28_cut_off_half_reviews_outside_the_pilot(self):
        todo = cutoff_rows.missing(self.pilot_ids())
        _, cutoff_half = common.halves()
        self.assertEqual(len(todo), 28)
        self.assertTrue({i["id"] for i in todo} <= set(cutoff_half))
        self.assertFalse({i["id"] for i in todo} & self.pilot_ids())
        self.assertTrue(all(i["text"].strip() for i in todo))

    def test_no_golden_review_can_be_among_them(self):
        golden = {r["review_id"] for r in csv.DictReader(open(fixtures.ROOT / "evals/golden_50_labeled.csv", encoding="utf-8-sig", newline=""))}
        self.assertFalse({i["id"] for i in cutoff_rows.missing(set())} & golden)

    def test_each_answer_is_saved_with_its_lowest_top_probability(self):
        items = cutoff_rows.missing(self.pilot_ids())[:3]
        rows = cutoff_rows.run(self.paid(standins.ReplayJev()).ask, items)
        self.assertEqual([r["review_id"] for r in rows], [i["id"] for i in items])
        for row in rows:
            self.assertIn(row["topic"], labels.TOPICS)
            self.assertIn(row["intent"], labels.INTENTS)
            self.assertTrue(0 <= row["min_top"] <= 1)

    def test_the_table_reads_the_pilot_answers_and_these_rows_together(self):
        flat = self.dir / "rows.jsonl"
        flat.write_text(json.dumps({"review_id": "extra-1", "topic": "other", "intent": "praise", "severity": 1, "min_top": 0.55}) + "\n")
        answers = cutoff_table.answers_from_files([fixtures.PROBE / "simple.jsonl", flat])
        self.assertEqual(len(answers), 101)
        self.assertEqual(answers["extra-1"], {"topic": "other", "intent": "praise", "severity": 1, "min_top": 0.55})


class Wording(EvalCase):
    def test_the_trial_reads_the_planted_slogans_and_the_tune_half_only(self):
        items = wording_trial.items()
        self.assertEqual(len(items), 34)
        with open(fixtures.ROOT / "evals/boycott_60.csv", encoding="utf-8", newline="") as f:
            tune = {r["review_id"] for r in csv.DictReader(f) if r["split"] == "tune"}
        self.assertEqual({i["id"] for i in items if not i["id"].startswith("planted:")}, tune)
        self.assertEqual(sorted(i["id"] for i in items if i["id"].startswith("planted:")), ["planted:S1", "planted:S2", "planted:S3", "planted:S4"])

    def test_a_holdout_row_stops_the_trial(self):
        holdout = common.boycott("holdout")[0]
        with self.assertRaises(wording_trial.HoldoutTouched):
            wording_trial.run({"probe": self.paid(KeyFollower()).ask}, items=[*wording_trial.items(), holdout])

    def test_each_wording_is_scored_on_the_slogans_and_against_the_raters_shared_intent(self):
        follows = KeyFollower()
        cancels = KeyFollower(slogans_as="cancellation")
        result = wording_trial.run({"probe": self.paid(cancels).ask, "candidate": self.paid(follows).ask})
        self.assertEqual((result["probe"]["slogans_right"], result["candidate"]["slogans_right"]), (1, 4))
        shared = result["candidate"]["tune_with_shared_rater_intent"]
        self.assertGreater(shared, 20)
        self.assertLessEqual(result["candidate"]["tune_intent_matches"], shared)
        self.assertEqual(len(follows.sent), 34)

    def test_the_pass_marks_need_every_slogan_right_and_no_fewer_tune_matches_than_the_probe(self):
        good = {"slogans_right": 4, "slogans": {"S1": True, "S2": True, "S3": True, "S4": True}, "tune_intent_matches": 25}
        probe = {"slogans_right": 2, "slogans": {"S1": True, "S2": False, "S3": True, "S4": False}, "tune_intent_matches": 24}
        self.assertEqual(wording_trial.marks(probe, good), [])
        worse = {**good, "tune_intent_matches": 20}
        self.assertTrue(any("tune" in m for m in wording_trial.marks(probe, worse)))
        lost = {**good, "slogans_right": 3, "slogans": {**good["slogans"], "S1": False}}
        missed = wording_trial.marks(probe, lost)
        self.assertTrue(any("S1" in m for m in missed))

    def test_the_candidate_wording_changes_only_the_intent_question(self):
        v1 = json.loads((fixtures.ROOT / "prompts/enrich-v1.json").read_text())
        v2 = json.loads((fixtures.ROOT / "prompts/enrich-v2.json").read_text())
        self.assertEqual(v2["version"], "prompt-v2")
        for same in ("topic", "severity", "tone", "evidence", "model", "schema"):
            self.assertEqual(v2[same], v1[same])
        self.assertNotEqual(v2["intent"], v1["intent"])
        self.assertEqual(set(v2["intent"]["criteria"]), set(v1["intent"]["criteria"]))
        self.assertEqual(jev.load_setup(fixtures.ROOT / "prompts", 0.7, prompt_name="enrich-v2.json").label_config, "jev-1.13.0/prompt-v2/schema-v1/cut-0.70")


class Holdout(EvalCase):
    def test_the_holdout_is_scored_once_and_a_second_run_is_refused(self):
        out = self.dir / "holdout.json"
        labeler = KeyFollower()
        first = holdout_score.run(self.paid(labeler).ask, out_path=out)
        self.assertEqual((first["holdout_rows"], first["planted"]["right"]), (30, 25))
        self.assertEqual(len(labeler.sent), 55)
        with self.assertRaises(holdout_score.AlreadyScored):
            holdout_score.run(self.paid(labeler).ask, out_path=out)
        self.assertEqual(len(labeler.sent), 55)
        self.assertEqual(json.loads(out.read_text())["planted"]["right"], 25)

    def test_the_holdout_rows_are_the_other_half(self):
        ids = {i["id"] for i in holdout_score.items() if not i["id"].startswith("planted:")}
        self.assertEqual(ids, {r["id"] for r in common.boycott("holdout")})
        self.assertFalse(ids & {i["id"] for i in wording_trial.items()})


class Cutoff(unittest.TestCase):
    def setUp(self):
        self.answers = cutoff_table.answers_from_exchanges(fixtures.PROBE / "simple.jsonl")

    def test_the_table_reproduces_the_one_recorded_on_2026_10_04(self):
        """Known answer from flag_probe.py, recorded in CLAUDE.md: flagged of 100, mistakes caught of 5, right answers flagged of 24."""
        rows = cutoff_table.table(self.answers, {"hand": common.dev_labels()}, cutoffs=(0.6, 0.7, 0.8, 0.9))
        got = [(r["cutoff"], r["flagged"], r["hand"]["caught"], r["hand"]["agreeing_flagged"]) for r in rows]
        self.assertEqual(got, [(0.6, 17, 2, 1), (0.7, 26, 4, 4), (0.8, 38, 4, 8), (0.9, 54, 5, 11)])
        self.assertEqual((rows[0]["of"], rows[0]["hand"]["rows"], rows[0]["hand"]["differences"], rows[0]["hand"]["agreeing"]), (100, 29, 5, 24))

    def test_every_reference_is_shown_side_by_side_and_disputed_rows_are_their_own_group(self):
        answers = {
            "a": {"topic": "playback", "intent": "complaint", "severity": 3, "min_top": 0.5},
            "b": {"topic": "other", "intent": "unclear", "severity": 1, "min_top": 0.95},
            "c": {"topic": "billing", "intent": "complaint", "severity": 2, "min_top": 0.65},
        }
        hand = {"a": {"topic": "playback", "intent": "complaint", "severity": 2}, "b": {"topic": "other", "intent": "unclear", "severity": 2}}
        raters = {"a": {"topic": "playback", "intent": "complaint", "severity": 3}, "b": {"topic": "other", "intent": "unclear", "severity": 1}}
        refs = {"raters": raters, "hand as written": hand, "hand with the rule": cutoff_table.by_rule(hand)}
        (row,) = cutoff_table.table(answers, refs, cutoffs=(0.7,), disputed={"c"})
        self.assertEqual(row["flagged"], 2)
        self.assertEqual(row["raters"], {"rows": 2, "differences": 0, "caught": 0, "agreeing": 2, "agreeing_flagged": 1})
        self.assertEqual(row["hand as written"], {"rows": 2, "differences": 2, "caught": 1, "agreeing": 0, "agreeing_flagged": 0})
        self.assertEqual(row["hand with the rule"], {"rows": 2, "differences": 1, "caught": 1, "agreeing": 1, "agreeing_flagged": 0})
        self.assertEqual(row["disputed"], {"rows": 1, "flagged": 1})

    def test_the_two_halves_split_the_121_rows_and_leave_out_the_29(self):
        wording, cutoff = common.halves()
        earlier = set(common.dev_labels())
        self.assertEqual(len(wording) + len(cutoff), 121)
        self.assertFalse(set(wording) & set(cutoff))
        self.assertFalse((set(wording) | set(cutoff)) & earlier)
        self.assertLessEqual(abs(len(wording) - len(cutoff)), 1)
        self.assertEqual(common.halves(), (wording, cutoff))

    def test_the_table_prints_as_text(self):
        rows = cutoff_table.table(self.answers, {"hand": common.dev_labels()}, cutoffs=(0.7,))
        text = cutoff_table.render(rows)
        self.assertIn("0.70", text)
        self.assertIn("26 of 100", text)


class Golden(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.rows = fixtures.synthetic_rows(8, empties=0, copies=0)
        # Made-up golden labels. Rows 0-3: complaints. Rows 4-5: unclear with severity 2, which the rule makes 1.
        gold = [("playback", "complaint", 3), ("playback", "complaint", 3), ("billing", "complaint", 2), ("access", "complaint", 4),
                ("other", "unclear", 2), ("other", "unclear", 2), ("other", "praise", 1), ("catalog", "request", 1)]  # fmt: skip
        self.golden = self.dir / "golden.csv"
        with open(self.golden, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["review_id", "review_text", "intent", "topic", "severity", "sentiment", "evidence_quote", "entities", "needs_review", "notes"])
            for row, (topic, intent, severity) in zip(self.rows, gold, strict=True):
                w.writerow([row["review_id"], row["review_text"], intent, topic, severity, "-0.5", row["review_text"], "", "FALSE", "alt topic: other" if topic == "billing" else ""])
        # Predictions: right on rows 0, 2, 3, 6, 7; row 1 has the wrong topic and is flagged; rows 4-5 are unclear with severity 1.
        pred = [("playback", "complaint", 3, False), ("usability", "complaint", 3, True), ("billing", "complaint", 2, False), ("access", "complaint", 4, True),
                ("other", "unclear", 1, False), ("other", "unclear", 1, False), ("other", "praise", 1, False), ("catalog", "request", 1, False)]  # fmt: skip
        self.records = self.dir / "records.jsonl"
        with open(self.records, "w", encoding="utf-8") as f:
            for row, (topic, intent, severity, flag) in zip(self.rows[:7], pred, strict=False):
                f.write(json.dumps(fixtures.record_for(row, topic=topic, intent=intent, severity=severity, needs_review=flag)) + "\n")
            last = self.rows[7]  # the eighth review was quarantined: it stays in the denominator
            f.write(json.dumps({"review_id": last["review_id"], "source_sha256": "x", "status": "quarantined", "reason": "invalid_model_output"}) + "\n")

    def report(self):
        return score_golden.report(self.golden, self.records)

    def test_the_counts_as_written(self):
        r = self.report()["as_written"]
        self.assertEqual((r["rows"], r["missing_predictions"]), (8, 1))
        self.assertEqual((r["topic"], r["intent"], r["severity_exact"], r["all_three"]), (6, 7, 5, 4))
        self.assertEqual(r["severity_error"], {"mean_signed": str(Decimal(-2) / 7), "mean_unsigned": str(Decimal(2) / 7), "on_rows": 7})
        self.assertEqual(r["ambiguous_cases"], 1)

    def test_the_second_reading_changes_only_rows_with_no_reported_problem(self):
        both = self.report()
        self.assertEqual(both["rule_changes"], 2)
        r = both["by_rule"]
        self.assertEqual((r["topic"], r["intent"]), (both["as_written"]["topic"], both["as_written"]["intent"]))
        self.assertEqual((r["severity_exact"], r["all_three"]), (7, 6))
        ids_as_written = {d["review_id"] for d in both["as_written"]["disagreements"]}
        ids_by_rule = {d["review_id"] for d in r["disagreements"]}
        self.assertEqual(ids_as_written - ids_by_rule, {self.rows[4]["review_id"], self.rows[5]["review_id"]})

    def test_needs_review_is_scored_as_a_prediction(self):
        r = self.report()["as_written"]["needs_review"]
        self.assertEqual(r, {"wrong_labels": 3, "wrong_caught": 1, "right_labels": 4, "right_flagged": 1})

    def test_disagreements_name_the_review_and_the_fields_never_the_label(self):
        r = self.report()["as_written"]
        by_id = {d["review_id"]: d["fields"] for d in r["disagreements"]}
        self.assertEqual(by_id[self.rows[1]["review_id"]], ["topic"])
        self.assertEqual(by_id[self.rows[7]["review_id"]], ["no prediction"])
        text = json.dumps(r["disagreements"])
        for label in (*labels.TOPICS, *labels.INTENTS):
            self.assertNotIn(f'"{label}"', text)

    def test_quotes_are_checked_as_exact_copies(self):
        self.assertEqual(self.report()["as_written"]["quotes_exact_copies"], {"checked": 7, "exact": 7})

    def test_the_command_prints_counts_and_ids_only_and_refuses_a_second_run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = score_golden.main(["--golden", str(self.golden), "--records", str(self.records), "--run", "t", "--out-dir", str(self.dir)])
        self.assertEqual(code, 0)
        printed = out.getvalue()
        self.assertIn("all three", printed)
        self.assertNotIn("alt topic", printed)
        self.assertTrue((self.dir / "golden_score_t.json").exists())
        again = io.StringIO()
        with redirect_stdout(again):
            code = score_golden.main(["--golden", str(self.golden), "--records", str(self.records), "--run", "t", "--out-dir", str(self.dir)])
        self.assertEqual(code, 2)
        self.assertIn("already", again.getvalue())


if __name__ == "__main__":
    unittest.main()
