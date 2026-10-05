import json
import math
import tempfile
import unittest
from pathlib import Path

from pipeline import labels
from tests import fixtures

TEXT = "The app crashes every time I open a playlist. Fix it."
GOOD = {
    "topic": "playback",
    "intent": "complaint",
    "severity": 4,
    "sentiment": -0.315,
    "entities": ["playlist"],
    "evidence_quote": "The app crashes every time I open a playlist.",
    "needs_review": False,
    "label_config": "jev-1.13.0/prompt-v1/schema-v1/cut-0.70",
}

# What labels.validate must refuse, and the flag the supplied checker raises for the same record.
BAD = {
    "severity is a bool": ({"severity": True}, "invalid_schema"),
    "severity is a float": ({"severity": 3.0}, "invalid_schema"),
    "severity is a string": ({"severity": "3"}, "invalid_schema"),
    "severity out of range": ({"severity": 6}, "invalid_schema"),
    "needs_review is an int": ({"needs_review": 1}, "invalid_schema"),
    "sentiment out of range": ({"sentiment": 1.5}, "invalid_schema"),
    "sentiment is a bool": ({"sentiment": True}, "invalid_schema"),
    "sentiment is not finite": ({"sentiment": math.nan}, "malformed_jsonl"),
    "entity is blank": ({"entities": [" "]}, "invalid_schema"),
    "entities is not a list": ({"entities": "playlist"}, "invalid_schema"),
    "entity is not a string": ({"entities": [7]}, "invalid_schema"),
    "quote is not in the text": ({"evidence_quote": "the app crashes every time"}, "unsupported_quote"),
    "quote is blank": ({"evidence_quote": "  "}, "invalid_schema"),
    "topic is unknown": ({"topic": "pricing"}, "invalid_schema"),
    "intent is unknown": ({"intent": "angry"}, "invalid_schema"),
    "label_config is blank": ({"label_config": " "}, "invalid_schema"),
    "a field is missing": ({"intent": None}, "invalid_schema"),
}


def audit_one(record):
    """Run the supplied checker over a folder holding only this record. Returns its report."""
    checker = fixtures.checker()
    row = dict(zip(checker.FIELDS, ("id-1", TEXT, "1", "0", "", "2024-01-01 00:00:00")))
    ref = {"rows": {"id-1": {"source_sha256": checker.row_sha(row), "review_text": TEXT}}, "analysis_sha256": "x", "ingestion": {}}
    with tempfile.TemporaryDirectory() as folder:
        line = {"review_id": "id-1", "source_sha256": checker.row_sha(row), "status": "completed", **record}
        Path(folder, "records.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        return checker.audit(folder, ref)


class Vocabulary(unittest.TestCase):
    def test_labels_are_the_checkers(self):
        self.assertEqual(set(labels.TOPICS), set(fixtures.checker().TOPICS))
        self.assertEqual(set(labels.INTENTS), set(fixtures.checker().INTENTS))

    def test_intents_are_in_the_contracts_precedence_order(self):
        self.assertEqual(labels.INTENTS, ("cancellation", "complaint", "request", "praise", "unclear"))

    def test_severity_names_map_to_one_through_five(self):
        self.assertEqual(sorted(labels.SEVERITY.values()), [1, 2, 3, 4, 5])
        self.assertEqual((labels.SEVERITY["no_problem"], labels.SEVERITY["serious_harm"]), (1, 5))


class Validate(unittest.TestCase):
    def test_a_good_record_passes(self):
        labels.validate(TEXT, GOOD)

    def test_an_empty_entity_list_passes(self):
        labels.validate(TEXT, {**GOOD, "entities": []})

    def test_each_bad_record_is_refused(self):
        for name, (change, _) in BAD.items():
            with self.subTest(name=name), self.assertRaises(labels.InvalidAnswer):
                labels.validate(TEXT, {**GOOD, **change})

    def test_the_quote_must_be_an_exact_piece_not_a_close_one(self):
        with self.assertRaises(labels.InvalidAnswer) as caught:
            labels.validate(TEXT, {**GOOD, "evidence_quote": "The app crashes every time I open a playlist"[:-1] + "T"})
        self.assertIn("quote", str(caught.exception))


class AgainstTheChecker(unittest.TestCase):
    """The checker is the outside judge: what we accept it must accept, what we refuse it must flag."""

    def test_the_checker_accepts_what_validate_accepts(self):
        report = audit_one(GOOD)
        self.assertEqual(report["coverage"]["valid_completed"], 1)
        self.assertNotIn("invalid_schema", report["issue_counts"])
        self.assertNotIn("unsupported_quote", report["issue_counts"])

    def test_the_checker_flags_what_validate_refuses(self):
        for name, (change, flag) in BAD.items():
            with self.subTest(name=name):
                report = audit_one({**GOOD, **change})
                self.assertEqual(report["coverage"]["valid_completed"], 0)
                self.assertIn(flag, report["issue_counts"])


class Tone(unittest.TestCase):
    def test_scores_map_onto_minus_one_to_one(self):
        self.assertEqual(labels.sentiment_from_tone(0), -1)
        self.assertEqual(labels.sentiment_from_tone(4), 1)
        self.assertEqual(labels.sentiment_from_tone(2.0), 0)
        self.assertAlmostEqual(labels.sentiment_from_tone(1.37), -0.315)

    def test_a_score_outside_the_scale_raises_and_is_never_clamped(self):
        for score in (4.01, -0.1, math.nan, math.inf, True, "2", None):
            with self.subTest(score=score), self.assertRaises(labels.InvalidAnswer):
                labels.sentiment_from_tone(score)


class FixedRule(unittest.TestCase):
    def test_no_reported_problem_is_severity_one(self):
        for intent in ("unclear", "praise", "request"):
            self.assertEqual(labels.by_rule(intent, 2), 1)

    def test_a_complaint_or_cancellation_keeps_its_severity(self):
        self.assertEqual(labels.by_rule("complaint", 3), 3)
        self.assertEqual(labels.by_rule("cancellation", "2"), 2)


if __name__ == "__main__":
    unittest.main()
