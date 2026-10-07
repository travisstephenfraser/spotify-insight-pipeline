import csv
import gzip
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from pipeline import export, standins
from tests import fixtures

sys.path.insert(0, str(fixtures.ROOT / "evals"))
import trace_review  # noqa: E402

RANKED = ("complaint", "cancellation")


def read_jsonl(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Trace(unittest.TestCase):
    """A stand-in run, exported. Each test reads the exported files itself and holds the trace to them."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name) / "a"
        cls.rows = fixtures.synthetic_rows(30, empties=2, copies=5)
        cls.flaky = cls.rows[
            6
        ]  # a distinct text with no copy: its first request fails, its second succeeds
        labeler = standins.ReplayJev(
            fixtures.PROBE / "simple.jsonl",
            script={cls.flaky["review_text"]: ["temporary"]},
        )
        cls.db, cls.csv = fixtures.full_run(root, rows=cls.rows, labeler=labeler)
        cls.grading, cls.evidence = root / "grading", root / "evidence"
        export.export(
            cls.db,
            "r1",
            cls.grading,
            checker_path=fixtures.CHECKER,
            input_path=cls.csv,
            evidence_dir=cls.evidence,
        )
        cls.records = {
            r["review_id"]: r for r in read_jsonl(cls.grading / "records.jsonl")
        }
        cls.calls = read_jsonl(cls.grading / "calls.jsonl")
        cls.issue_of = {
            r["review_id"]: r["issue_id"]
            for r in read_csv(cls.grading / "membership.csv")
        }
        cls.ranking = {r["issue_id"]: r for r in read_csv(cls.grading / "ranking.csv")}
        cls.claims = read_csv(cls.grading / "claims.csv")
        cls.verified = {
            v["review_id"]: v
            for v in read_jsonl(cls.evidence / "verify_predictions.jsonl")
        }

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls._tmp.cleanup()

    def trace(self, review_id, **options):
        return trace_review.trace(
            review_id, grading=self.grading, evidence=self.evidence, **options
        )

    def some(self, want):
        """The first exported record, by review ID, that `want` accepts."""
        found = sorted(i for i, r in self.records.items() if want(r))
        self.assertTrue(found, "the stand-in run has no such record")
        return found[0]

    def test_a_complaint_is_followed_from_its_record_to_the_claims_about_its_issue(
        self,
    ):
        review_id = self.some(
            lambda r: r.get("intent") in RANKED and "cache_source_id" not in r
        )
        t = self.trace(review_id)
        self.assertEqual(t["record"], self.records[review_id])
        self.assertEqual(t["labeled_by"], review_id)
        self.assertEqual(t["issue_id"], self.issue_of[review_id])
        self.assertEqual(t["ranking"], self.ranking[t["issue_id"]])
        self.assertEqual(
            t["claims"], [c for c in self.claims if c["issue_id"] == t["issue_id"]]
        )

    def test_the_calls_are_the_ones_that_list_the_review_and_the_last_one_succeeded(
        self,
    ):
        review_id = self.some(
            lambda r: r.get("intent") in RANKED and "cache_source_id" not in r
        )
        t = self.trace(review_id)
        expected = [
            c["request_id"]
            for c in self.calls
            if c["role"] == "enrich" and review_id in c["review_ids"]
        ]
        self.assertEqual([c["request_id"] for c in t["calls"]], expected)
        self.assertEqual(t["calls"][-1]["outcome"], "succeeded")
        self.assertEqual(t["calls"][-1]["label_config"], t["record"]["label_config"])

    def test_a_failed_attempt_is_listed_before_the_one_that_succeeded_with_its_error(
        self,
    ):
        t = self.trace(self.flaky["review_id"])
        self.assertEqual([c["outcome"] for c in t["calls"]], ["failed", "succeeded"])
        self.assertIn("scripted temporary failure", t["calls"][0]["error"])
        self.assertEqual(t["record"]["status"], "completed")

    def test_a_copy_is_traced_to_the_request_that_labeled_its_original(self):
        review_id = self.some(lambda r: "cache_source_id" in r)
        t = self.trace(review_id)
        source = self.records[review_id]["cache_source_id"]
        self.assertEqual(t["labeled_by"], source)
        self.assertTrue(t["calls"])
        for call in t["calls"]:
            self.assertIn(source, call["review_ids"])
            self.assertNotIn(review_id, call["review_ids"])

    def test_a_quarantined_review_shows_its_reason_and_joins_nothing(self):
        review_id = self.some(lambda r: r["status"] == "quarantined")
        t = self.trace(review_id)
        self.assertEqual(t["quarantine"]["reason"], "empty_review_text")
        self.assertEqual(
            (t["calls"], t["verify"], t["issue_id"], t["ranking"], t["claims"]),
            ([], None, None, None, []),
        )

    def test_a_review_that_is_not_a_complaint_joins_no_issue(self):
        review_id = self.some(
            lambda r: r["status"] == "completed" and r["intent"] not in RANKED
        )
        t = self.trace(review_id)
        self.assertNotIn(review_id, self.issue_of)
        self.assertEqual((t["issue_id"], t["ranking"], t["claims"]), (None, None, []))

    def test_the_verifiers_answer_is_shown_for_a_sampled_review_and_compared_field_by_field(
        self,
    ):
        review_id = self.some(
            lambda r: r["review_id"] in self.verified and r["status"] == "completed"
        )
        t = self.trace(review_id)
        record, theirs = self.records[review_id], self.verified[review_id]
        self.assertEqual(
            {f: t["verify"][f] for f in ("topic", "intent", "severity")},
            {f: theirs[f] for f in ("topic", "intent", "severity")},
        )
        self.assertEqual(
            t["verify"]["same"],
            {f: record[f] == theirs[f] for f in ("topic", "intent", "severity")},
        )

    def test_a_review_outside_the_sample_has_no_verifier_answer(self):
        review_id = self.some(
            lambda r: r["review_id"] not in self.verified and r["status"] == "completed"
        )
        self.assertIsNone(self.trace(review_id)["verify"])

    def test_the_source_row_is_hashed_again_and_held_to_the_record(self):
        review_id = self.some(lambda r: r.get("intent") in RANKED)
        t = self.trace(review_id, source=self.csv)
        row = next(r for r in self.rows if r["review_id"] == review_id)
        self.assertEqual(t["source"]["row"]["review_text"], row["review_text"])
        self.assertTrue(t["source"]["hash_matches"])
        self.assertTrue(t["source"]["quote_in_text"])

    def test_a_changed_source_row_no_longer_matches_its_hash(self):
        review_id = self.some(lambda r: r.get("intent") in RANKED)
        changed = Path(self._tmp.name) / "changed.csv"
        fixtures.write_csv(
            changed,
            [
                {**r, "review_likes": "999"} if r["review_id"] == review_id else r
                for r in self.rows
            ],
        )
        self.assertFalse(
            self.trace(review_id, source=changed)["source"]["hash_matches"]
        )

    def test_an_id_with_no_record_is_refused(self):
        with self.assertRaises(trace_review.NoSuchReview):
            self.trace("00000000-0000-4000-8000-999999999999")

    def test_the_command_prints_each_stage_in_order(self):
        review_id = self.some(
            lambda r: r.get("intent") in RANKED and "cache_source_id" not in r
        )
        out = io.StringIO()
        with redirect_stdout(out):
            code = trace_review.main(
                [
                    review_id,
                    "--grading",
                    str(self.grading),
                    "--evidence",
                    str(self.evidence),
                    "--source",
                    str(self.csv),
                ]
            )
        text = out.getvalue()
        self.assertEqual(code, 0)
        places = [
            text.index(stage)
            for stage in (
                "1 source",
                "2 enrich",
                "3 verify",
                "4 group",
                "5 rank",
                "6 memo",
            )
        ]
        self.assertEqual(places, sorted(places))
        self.assertIn(review_id, text)
        self.assertIn(self.issue_of[review_id], text)

    def test_the_command_refuses_an_unknown_id_without_a_traceback(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = trace_review.main(
                [
                    "no-such-id",
                    "--grading",
                    str(self.grading),
                    "--evidence",
                    str(self.evidence),
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("no record", out.getvalue())


FULL = fixtures.ROOT / "grading"


@unittest.skipUnless(
    (FULL / "records.jsonl.gz").exists(), "the full run's export is not in this copy"
)
class FullRun(unittest.TestCase):
    """Known answers from the full run, read by other code on 2026-10-07 (validation log entry 38).

    The stand-in tests above hold the trace to files the same test wrote. These hold it to the real run, so a
    trace that read the wrong column or the wrong review would not agree with itself and pass.
    """

    def trace(self, review_id):
        return trace_review.trace(
            review_id, grading=FULL, evidence=fixtures.ROOT / "runs/full"
        )

    def test_the_review_the_readme_traces(self):
        t = self.trace("00d13536-bd53-4e93-9c76-22db75d384d5")
        record = t["record"]
        self.assertEqual(
            (
                record["topic"],
                record["intent"],
                record["severity"],
                record["needs_review"],
            ),
            ("usability", "complaint", 4, False),
        )
        self.assertEqual(
            (t["verify"]["topic"], t["verify"]["intent"], t["verify"]["severity"]),
            ("other", "request", 1),
        )
        self.assertEqual(
            t["verify"]["same"], {"topic": False, "intent": False, "severity": False}
        )
        self.assertEqual([c["outcome"] for c in t["calls"]], ["succeeded"])
        self.assertEqual(t["issue_id"], "issue-usability")
        self.assertEqual(
            (
                t["ranking"]["rank"],
                t["ranking"]["complaint_count"],
                t["ranking"]["severity_sum"],
            ),
            ("1", "81756", "212158"),
        )
        self.assertEqual(
            [c["claim_id"] for c in t["claims"]],
            ["CL-001", "CL-002", "CL-003", "CL-004"],
        )
        self.assertEqual(
            t["memo"]["cites_claims"], ["CL-001", "CL-002", "CL-003", "CL-004"]
        )
        self.assertFalse(t["memo"]["cites_review"])

    def test_the_request_the_readme_shows_timing_out(self):
        t = self.trace("a1d7bf6e-29bd-439f-b135-b7c059f4227b")
        self.assertEqual([c["outcome"] for c in t["calls"]], ["failed", "succeeded"])
        self.assertIn("timed out", t["calls"][0]["error"])
        self.assertEqual(
            (t["calls"][0]["usage_known"], t["calls"][0]["input_tokens"]), (False, 0)
        )
        self.assertEqual(
            (t["record"]["status"], t["issue_id"]), ("completed", "issue-usability")
        )
        self.assertIsNone(t["verify"])

    def test_a_review_the_memo_quotes(self):
        t = self.trace("88587f1e-7047-4167-b424-735eddada88e")
        self.assertTrue(t["memo"]["cites_review"])
        self.assertEqual(
            t["record"]["evidence_quote"], "Gets stuck in a loop of the same songs."
        )


if __name__ == "__main__":
    unittest.main()
