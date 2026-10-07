import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests import fixtures

sys.path.insert(0, str(fixtures.ROOT / "evals"))
import severity_whatif  # noqa: E402

FULL = fixtures.ROOT / "grading"
SAVED = fixtures.ROOT / "evals/severity_whatif.json"

# issue-a: 4, 4, 4, 2. issue-b: 3, 3, 3, 3. issue-c: 5, 1. One praise and one empty review belong to no issue.
ROWS = (
    ("a1", "a", "complaint", 4), ("a2", "a", "complaint", 4), ("a3", "a", "cancellation", 4), ("a4", "a", "complaint", 2),
    ("b1", "b", "complaint", 3), ("b2", "b", "complaint", 3), ("b3", "b", "complaint", 3), ("b4", "b", "cancellation", 3),
    ("c1", "c", "complaint", 5), ("c2", "c", "complaint", 1),
    ("p1", "a", "praise", 1),
)  # fmt: skip
RANKING = (
    ("1", "issue-a", "4", "14", "3.500000", "14"),
    ("2", "issue-b", "4", "12", "3.000000", "12"),
    ("3", "issue-c", "2", "6", "3.000000", "6"),
)


def write_grading(folder, rows=ROWS, ranking=RANKING):
    """A grading folder written by hand, so nothing here is checked against the code that is under test."""
    folder = Path(folder)
    records = [
        {
            "review_id": i,
            "status": "completed",
            "topic": t,
            "intent": intent,
            "severity": s,
        }
        for i, t, intent, s in rows
    ]
    records.append(
        {"review_id": "q1", "status": "quarantined", "reason": "empty_review_text"}
    )
    (folder / "records.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    with open(folder / "membership.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("issue_id", "review_id"))
        writer.writerows(
            (f"issue-{t}", i)
            for i, t, intent, _ in rows
            if intent in ("complaint", "cancellation")
        )
    with open(folder / "ranking.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            (
                "rank",
                "issue_id",
                "complaint_count",
                "severity_sum",
                "mean_severity",
                "priority_score",
            )
        )
        writer.writerows(ranking)
    return folder


class ByHand(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = write_grading(self._tmp.name)

    def totals(self, name):
        reading = severity_whatif.whatif(self.dir)["readings"][name]
        return [(issue, reading["totals"][issue]) for issue in reading["order"]]

    def test_the_labels_as_exported_give_the_exported_ranking(self):
        self.assertEqual(
            self.totals("as_labeled"),
            [("issue-a", 14), ("issue-b", 12), ("issue-c", 6)],
        )

    def test_every_four_counted_as_three(self):
        self.assertEqual(
            self.totals("four_as_three"),
            [("issue-b", 12), ("issue-a", 11), ("issue-c", 6)],
        )

    def test_every_four_and_five_counted_as_three(self):
        self.assertEqual(
            self.totals("high_as_three"),
            [("issue-b", 12), ("issue-a", 11), ("issue-c", 4)],
        )

    def test_every_complaint_counted_once_with_a_tie_broken_by_issue_id_as_the_ranking_breaks_it(
        self,
    ):
        self.assertEqual(
            self.totals("count_only"), [("issue-a", 4), ("issue-b", 4), ("issue-c", 2)]
        )

    def test_only_the_complaints_rated_four_or_five(self):
        self.assertEqual(
            self.totals("blocked_only"),
            [("issue-a", 3), ("issue-c", 1), ("issue-b", 0)],
        )

    def test_the_share_of_fours_at_which_two_issues_change_places(self):
        """a leads b by 2 and has 3 fours to b's none, so they meet when 2 of every 3 fours are counted as 3. c never catches up."""
        self.assertEqual(
            severity_whatif.whatif(self.dir)["break_even"],
            [{"ahead": "issue-a", "behind": "issue-b", "share_of_fours": "0.6667"}],
        )

    def test_it_says_which_issue_is_first_under_each_reading(self):
        self.assertEqual(
            severity_whatif.whatif(self.dir)["first"],
            {
                "as_labeled": "issue-a",
                "four_as_three": "issue-b",
                "high_as_three": "issue-b",
                "count_only": "issue-a",
                "blocked_only": "issue-a",
            },
        )

    def test_the_severity_counts_behind_it_are_reported(self):
        counts = severity_whatif.whatif(self.dir)["severity_counts"]
        self.assertEqual(counts["issue-a"], {"1": 0, "2": 1, "3": 0, "4": 3, "5": 0})
        self.assertEqual(counts["issue-c"], {"1": 1, "2": 0, "3": 0, "4": 0, "5": 1})

    def test_a_ranking_file_the_labels_do_not_reproduce_is_refused(self):
        """The anchor. A what-if built on a count that does not match the exported ranking would be about some other run."""
        wrong = (("1", "issue-a", "4", "15", "3.750000", "15"), *RANKING[1:])
        write_grading(self.dir, ranking=wrong)
        with self.assertRaises(severity_whatif.Mismatch):
            severity_whatif.whatif(self.dir)

    def test_a_member_that_is_not_a_completed_complaint_is_refused(self):
        with open(self.dir / "membership.csv", "a", encoding="utf-8") as f:
            f.write("issue-a,p1\n")
        with self.assertRaises(severity_whatif.Mismatch):
            severity_whatif.whatif(self.dir)

    def test_a_reading_that_gives_every_issue_the_same_total_is_refused(self):
        flat = tuple(
            (i, t, "complaint", 2)
            for i, t in (("a1", "a"), ("a2", "a"), ("b1", "b"), ("b2", "b"))
        )
        ranking = (
            ("1", "issue-a", "2", "4", "2.000000", "4"),
            ("2", "issue-b", "2", "4", "2.000000", "4"),
        )
        write_grading(self.dir, rows=flat, ranking=ranking)
        with self.assertRaises(severity_whatif.Degenerate):
            severity_whatif.whatif(self.dir)

    def test_nothing_in_the_grading_folder_is_written(self):
        before = {p.name: p.read_bytes() for p in self.dir.iterdir()}
        severity_whatif.whatif(self.dir)
        self.assertEqual({p.name: p.read_bytes() for p in self.dir.iterdir()}, before)

    def test_the_table_has_a_row_for_each_reading_in_its_own_order(self):
        table = severity_whatif.table(severity_whatif.whatif(self.dir)).splitlines()
        self.assertEqual(table[0], "| Reading | 1st | 2nd | 3rd |")
        self.assertIn(
            "| The labels as exported: the sum of severities | issue-a 14 | issue-b 12 | issue-c 6 |",
            table,
        )
        self.assertIn(
            "| Every 4 counted as 3 | issue-b 12 | issue-a 11 | issue-c 6 |", table
        )
        self.assertIn(
            "| Only complaints rated 4 or 5, each counted once | issue-a 3 | issue-c 1 | issue-b 0 |",
            table,
        )
        self.assertEqual(len(table), 2 + 5)

    def test_the_command_prints_the_table_and_saves_the_result(self):
        out, saved = io.StringIO(), self.dir / "out.json"
        with contextlib.redirect_stdout(out):
            code = severity_whatif.main(
                ["--grading", str(self.dir), "--out", str(saved)]
            )
        self.assertEqual(code, 0)
        self.assertIn(
            "| Every 4 counted as 3 | issue-b 12 | issue-a 11 | issue-c 6 |",
            out.getvalue(),
        )
        self.assertEqual(
            json.loads(saved.read_text(encoding="utf-8")),
            severity_whatif.whatif(self.dir),
        )

    def test_the_command_refuses_and_saves_nothing_when_the_ranking_does_not_match(
        self,
    ):
        write_grading(
            self.dir,
            ranking=(("1", "issue-a", "4", "15", "3.750000", "15"), *RANKING[1:]),
        )
        out, saved = io.StringIO(), self.dir / "out.json"
        with contextlib.redirect_stdout(out):
            code = severity_whatif.main(
                ["--grading", str(self.dir), "--out", str(saved)]
            )
        self.assertEqual(code, 2)
        self.assertIn("refused", out.getvalue())
        self.assertFalse(saved.exists())


@unittest.skipUnless(
    (FULL / "records.jsonl.gz").exists() and (FULL / "membership.csv").exists(),
    "the full run's grading folder is not here",
)
class FullRun(unittest.TestCase):
    """Known answers from the full run.

    The first row is the exported ranking, which the supplied checker and an outside reviewer each rebuilt. The other
    rows were counted on 2026-10-07 by a separate throwaway script before this one was written (validation log entry 39).
    """

    @classmethod
    def setUpClass(cls):
        cls.result = severity_whatif.whatif(FULL)

    def top(self, name, n=4):
        reading = self.result["readings"][name]
        return [(issue, reading["totals"][issue]) for issue in reading["order"][:n]]

    def test_the_labels_as_exported(self):
        self.assertEqual(
            self.top("as_labeled"),
            [
                ("issue-usability", 212158),
                ("issue-other", 175815),
                ("issue-playback", 147175),
                ("issue-billing", 141482),
            ],
        )

    def test_first_place_holds_when_every_four_is_counted_as_three_and_places_three_and_four_swap(
        self,
    ):
        self.assertEqual(
            self.top("four_as_three"),
            [
                ("issue-usability", 201649),
                ("issue-other", 173329),
                ("issue-billing", 133532),
                ("issue-playback", 122561),
            ],
        )
        self.assertEqual(
            self.top("high_as_three"),
            [
                ("issue-usability", 201261),
                ("issue-other", 171319),
                ("issue-billing", 131666),
                ("issue-playback", 122295),
            ],
        )

    def test_other_leads_on_count_and_playback_on_blocked_tasks(self):
        self.assertEqual(
            self.top("count_only", 2),
            [("issue-other", 85466), ("issue-usability", 81756)],
        )
        self.assertEqual(
            self.top("blocked_only"),
            [
                ("issue-playback", 24747),
                ("issue-usability", 10703),
                ("issue-access", 9746),
                ("issue-billing", 8883),
            ],
        )

    def test_playback_and_billing_are_the_only_pair_that_changes_places(self):
        self.assertEqual(
            self.result["break_even"],
            [
                {
                    "ahead": "issue-playback",
                    "behind": "issue-billing",
                    "share_of_fours": "0.3416",
                }
            ],
        )

    def test_every_member_is_counted_once(self):
        self.assertEqual(
            sum(sum(c.values()) for c in self.result["severity_counts"].values()),
            291865,
        )
        self.assertEqual(
            self.result["severity_counts"]["issue-playback"],
            {"1": 327, "2": 4560, "3": 12869, "4": 24614, "5": 133},
        )

    def test_the_saved_result_is_what_the_script_gives_now(self):
        self.assertEqual(json.loads(SAVED.read_text(encoding="utf-8")), self.result)

    def test_the_readme_shows_the_table_as_the_script_prints_it(self):
        readme = (fixtures.ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        for line in severity_whatif.table(self.result, places=4).splitlines():
            with self.subTest(line=line[:60]):
                self.assertIn(line, readme)


if __name__ == "__main__":
    unittest.main()
