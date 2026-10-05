import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from pipeline import rank
from tests import fixtures

COLUMNS = ("rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score")


def labeled():
    """Thirteen complaints over three issues that all score 12, and two reviews that are not complaints."""
    rows = fixtures.synthetic_rows(15, empties=0, copies=0)
    plan = [("playback", "complaint", 4)] * 3 + [("billing", "cancellation", 3)] * 4 + [("access", "complaint", 2)] * 6
    records = [fixtures.record_for(r, topic=t, intent=i, severity=s) for r, (t, i, s) in zip(rows, plan, strict=False)]
    assert len(records) == 13
    records += [fixtures.record_for(rows[13], topic="other", intent="praise", severity=1), fixtures.record_for(rows[14], topic="other", intent="unclear", severity=1)]
    membership = [(f"issue-{rec['topic']}", rec["review_id"]) for rec in records if rec["intent"] in ("complaint", "cancellation")]
    return rows, records, membership


class Rank(unittest.TestCase):
    def test_every_field_equals_the_checkers_own_ranking_as_a_string(self):
        """The checker compares str(its value) with our CSV text; this is that comparison."""
        rows, records, membership = labeled()
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            with open(Path(folder, "membership.csv"), "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows([("issue_id", "review_id"), *membership])
            theirs = fixtures.checker().audit(folder, fixtures.reference_for(rows))["calculated_ranking"]
        ours = rank.rank(records, membership)
        self.assertEqual(len(ours), len(theirs))
        self.assertEqual(len(ours), 3)
        for mine, target in zip(ours, theirs):
            self.assertEqual(tuple(mine), COLUMNS)
            for key in COLUMNS:
                self.assertEqual(mine[key], str(target[key]), key)

    def test_values_are_plain_strings_in_export_form(self):
        _, records, membership = labeled()
        top = rank.rank(records, membership)[0]
        self.assertEqual(top, {"rank": "1", "issue_id": "issue-access", "complaint_count": "6", "severity_sum": "12", "mean_severity": "2.000000", "priority_score": "12"})

    def test_a_tie_on_score_is_ordered_by_issue_id(self):
        _, records, membership = labeled()
        ranked = rank.rank(records, membership)
        self.assertEqual([(r["issue_id"], r["priority_score"]) for r in ranked], [("issue-access", "12"), ("issue-billing", "12"), ("issue-playback", "12")])

    def test_the_mean_rounds_half_up_to_six_decimals(self):
        self.assertEqual(rank.mean_string(4_000_001, 2_000_000), "2.000001")
        self.assertEqual(rank.mean_string(4_000_001, 2_000_000), fixtures.checker().mean_string(4_000_001, 2_000_000))
        self.assertEqual(rank.mean_string(10, 3), "3.333333")
        self.assertEqual(rank.mean_string(5, 2), "2.500000")

    def test_a_member_missing_from_the_records_raises(self):
        _, records, membership = labeled()
        with self.assertRaises(rank.BadMembership) as caught:
            rank.rank(records, [*membership, ("issue-access", "no-such-review")])
        self.assertIn("no-such-review", str(caught.exception))

    def test_a_member_that_is_not_a_complaint_or_cancellation_raises(self):
        _, records, membership = labeled()
        praise = next(r for r in records if r["intent"] == "praise")
        with self.assertRaises(rank.BadMembership):
            rank.rank(records, [*membership, ("issue-other", praise["review_id"])])

    def test_a_quarantined_member_raises(self):
        rows, records, membership = labeled()
        records[0] = {"review_id": records[0]["review_id"], "source_sha256": "x", "status": "quarantined", "reason": "invalid_model_output"}
        with self.assertRaises(rank.BadMembership):
            rank.rank(records, membership)

    def test_no_members_gives_an_empty_ranking(self):
        _, records, _ = labeled()
        self.assertEqual(rank.rank(records, []), [])


class FromFiles(unittest.TestCase):
    def folder(self, gz=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        _, records, membership = labeled()
        text = "".join(json.dumps(r) + "\n" for r in records)
        if gz:
            with gzip.open(folder / "records.jsonl.gz", "wt", encoding="utf-8") as f:
                f.write(text)
        else:
            (folder / "records.jsonl").write_text(text, encoding="utf-8")
        with open(folder / "membership.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f, lineterminator="\n").writerows([("issue_id", "review_id"), *membership])
        return folder

    def test_ranking_csv_is_rebuilt_from_the_committed_files_alone(self):
        folder = self.folder()
        rank.from_files(folder)
        with open(folder / "ranking.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        _, records, membership = labeled()
        self.assertEqual(rows, rank.rank(records, membership))

    def test_running_it_twice_gives_byte_identical_files(self):
        folder = self.folder()
        rank.from_files(folder)
        first = (folder / "ranking.csv").read_bytes()
        rank.from_files(folder)
        self.assertEqual((folder / "ranking.csv").read_bytes(), first)
        self.assertTrue(first.startswith(b"rank,issue_id,complaint_count,severity_sum,mean_severity,priority_score\n"))

    def test_gzipped_records_give_the_same_ranking(self):
        plain, zipped = self.folder(), self.folder(gz=True)
        rank.from_files(plain)
        rank.from_files(zipped)
        self.assertEqual((zipped / "ranking.csv").read_bytes(), (plain / "ranking.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
