import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import hashing, prepare, state
from tests import fixtures


class PrepCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.db = state.connect(self.dir / "state.sqlite")
        self.addCleanup(self.db.close)
        self.csv = self.dir / "in.csv"

    def prep(self, rows=None, *, run="r1", path=None, verify_size=5000, **csv_options):
        if rows is not None:
            fixtures.write_csv(self.csv, rows, **csv_options)
        with state.tx(self.db):
            fixtures.new_run(self.db, run)
            return prepare.prepare(
                self.db, run, path or self.csv, seed=fixtures.SEED, verify_seed="verify-v1", verify_size=verify_size
            )

    def reviews(self, run="r1"):
        return {r["review_id"]: r for r in self.db.execute("SELECT * FROM reviews WHERE run=?", (run,))}


class Rows(PrepCase):
    def setUp(self):
        super().setUp()
        self.rows = fixtures.synthetic_rows(20, empties=3, copies=4)
        self.counts = self.prep(self.rows)
        self.got = self.reviews()

    def test_every_row_lands_with_its_exact_fields(self):
        self.assertEqual(set(self.got), {r["review_id"] for r in self.rows})
        for row in self.rows:
            saved = self.got[row["review_id"]]
            self.assertEqual({k: saved[k] for k in hashing.FIELDS}, row)
            self.assertEqual(saved["source_sha256"], fixtures.checker().row_sha(row))

    def test_whitespace_only_text_is_quarantined_with_the_exact_reason(self):
        empty = [r for r in self.got.values() if not r["review_text"].strip()]
        self.assertEqual(len(empty), 3)
        self.assertEqual({(r["status"], r["reason"]) for r in empty}, {("quarantined", "empty_review_text")})
        others = [r for r in self.got.values() if r["review_text"].strip()]
        self.assertEqual({(r["status"], r["reason"]) for r in others}, {("pending", None)})

    def test_counts_add_up(self):
        self.assertEqual(
            {k: self.counts[k] for k in ("rows", "empty", "distinct_texts", "copies")},
            {"rows": 20, "empty": 3, "distinct_texts": 13, "copies": 4},
        )
        by_status = {s: sum(r["status"] == s for r in self.got.values()) for s in ("pending", "quarantined")}
        self.assertEqual(by_status["pending"] + by_status["quarantined"], self.counts["rows"])
        self.assertEqual(self.counts["missing_app_version"], sum(not r["app_version"].strip() for r in self.rows))

    def test_run_order_is_the_seeded_order(self):
        ordered = sorted(self.got.values(), key=lambda r: r["run_order"])
        self.assertEqual([r["run_order"] for r in ordered], list(range(20)))
        ids = [r["review_id"] for r in ordered]
        self.assertEqual(ids, sorted(ids, key=lambda i: hashing.order_key(fixtures.SEED, i)))

    def test_a_copy_points_at_the_first_in_run_order_and_the_original_at_nothing(self):
        groups = {}
        for r in self.got.values():
            if r["review_text"].strip():
                groups.setdefault(r["review_text"], []).append(r)
        shared = [g for g in groups.values() if len(g) > 1]
        self.assertEqual(len(shared), 4)
        for group in shared:
            first, *rest = sorted(group, key=lambda r: r["run_order"])
            self.assertIsNone(first["cache_source_id"])
            self.assertEqual({r["cache_source_id"] for r in rest}, {first["review_id"]})
            self.assertEqual(len({r["text_key"] for r in group}), 1)
        alone = [g[0] for g in groups.values() if len(g) == 1]
        self.assertEqual({r["cache_source_id"] for r in alone}, {None})

    def test_an_empty_text_is_never_a_copy(self):
        empty = [r for r in self.got.values() if not r["review_text"].strip()]
        self.assertEqual({r["cache_source_id"] for r in empty}, {None})


class VerifySample(PrepCase):
    def test_the_sample_is_the_lowest_keys_among_nonempty_reviews(self):
        rows = fixtures.synthetic_rows(30, empties=2, copies=3)
        counts = self.prep(rows, verify_size=5)
        got = self.reviews()
        sample = {i for i, r in got.items() if r["in_verify_sample"]}
        nonempty = [r["review_id"] for r in rows if r["review_text"].strip()]
        expected = set(sorted(nonempty, key=lambda i: hashing.order_key("verify-v1", i))[:5])
        self.assertEqual(sample, expected)
        self.assertEqual(counts["verify_sample"], 5)

    def test_the_same_input_gives_the_same_sample_in_another_run(self):
        rows = fixtures.synthetic_rows(30, empties=2, copies=3)
        self.prep(rows, verify_size=5)
        self.prep(run="r2", verify_size=5)
        first = {i for i, r in self.reviews("r1").items() if r["in_verify_sample"]}
        second = {i for i, r in self.reviews("r2").items() if r["in_verify_sample"]}
        self.assertEqual(first, second)

    def test_a_run_smaller_than_the_sample_size_verifies_every_nonempty_review(self):
        rows = fixtures.synthetic_rows(10, empties=1, copies=2)
        counts = self.prep(rows)
        self.assertEqual(counts["verify_sample"], 9)
        self.assertEqual(sum(r["in_verify_sample"] for r in self.reviews().values()), 9)


class SuppliedSamples(PrepCase):
    def test_the_cost_pilot_file_is_already_in_run_order(self):
        """Known answer from outside this code: the supplied samples were cut by the same seeded order."""
        self.prep(path=fixtures.DATA / "cost_100.csv")
        ordered = sorted(self.reviews().values(), key=lambda r: r["run_order"])
        self.assertEqual(
            [r["review_id"] for r in ordered], [r["review_id"] for r in fixtures.supplied("cost_100.csv")]
        )

    def test_another_input_is_not_the_supplied_file(self):
        counts = self.prep(path=fixtures.DATA / "cost_100.csv")
        self.assertIs(counts["supplied_file"], False)


class FreshInput(PrepCase):
    """Review Focus 1: the instructor may hand over a CSV we have never seen."""

    def test_a_byte_order_mark_crlf_and_extra_columns_are_accepted(self):
        rows = [dict(r, extra_note="x", stars_again="5") for r in fixtures.synthetic_rows(8)]
        counts = self.prep(rows, bom=True, eol="\r\n", fields=(*fixtures.FIELDS, "extra_note", "stars_again"))
        self.assertEqual(counts["rows"], 8)
        got = self.reviews()
        for row in rows:
            self.assertEqual(got[row["review_id"]]["source_sha256"], fixtures.checker().row_sha(row))

    def test_a_missing_column_stops_with_a_plain_message(self):
        fields = tuple(f for f in fixtures.FIELDS if f != "review_likes")
        with self.assertRaises(prepare.BadInput) as caught:
            self.prep(fixtures.synthetic_rows(8), fields=fields)
        self.assertIn("review_likes", str(caught.exception))

    def test_a_repeated_review_id_stops_with_a_plain_message(self):
        rows = fixtures.synthetic_rows(8)
        rows[5]["review_id"] = rows[2]["review_id"]
        with self.assertRaises(prepare.BadInput) as caught:
            self.prep(rows)
        self.assertIn(rows[2]["review_id"], str(caught.exception))

    def test_a_one_row_file_works(self):
        counts = self.prep(fixtures.synthetic_rows(1, empties=0, copies=0))
        self.assertEqual((counts["rows"], counts["verify_sample"]), (1, 1))

    def test_a_file_with_only_a_header_stops_with_a_plain_message(self):
        with self.assertRaises(prepare.BadInput):
            self.prep([])


class AwkwardText(PrepCase):
    """Review Focus 2."""

    def test_awkward_text_is_stored_exactly_and_identical_bytes_share_one_result(self):
        rows = fixtures.synthetic_rows(12, empties=1, copies=0)
        for row, text in zip(rows, (*fixtures.AWKWARD, fixtures.AWKWARD[0])):
            row["review_text"] = text
        self.prep(rows)
        got = self.reviews()
        for row in rows:
            self.assertEqual(got[row["review_id"]]["review_text"], row["review_text"])
            self.assertEqual(got[row["review_id"]]["source_sha256"], fixtures.checker().row_sha(row))
        twins = [r for r in got.values() if r["review_text"] == fixtures.AWKWARD[0]]
        self.assertEqual(sorted(r["cache_source_id"] is None for r in twins), [False, True])

    def test_one_trailing_space_makes_a_different_text(self):
        rows = fixtures.synthetic_rows(4, empties=0, copies=0)
        rows[0]["review_text"], rows[1]["review_text"] = "bad app", "bad app "
        counts = self.prep(rows)
        self.assertEqual(counts["copies"], 0)


class Guards(PrepCase):
    def patched(self, **wrong):
        fixtures.write_csv(self.csv, fixtures.synthetic_rows(20, empties=3, copies=4))
        right = {"sha256": hashing.file_sha(self.csv), "rows": 20, "empty": 3, "distinct_texts": 13, "missing_app_version": 5}
        return mock.patch.object(prepare, "SUPPLIED", {**right, **wrong})

    def test_the_supplied_file_with_the_known_counts_passes(self):
        with self.patched():
            counts = self.prep()
        self.assertIs(counts["supplied_file"], True)

    def test_the_supplied_file_with_a_wrong_count_raises(self):
        for name in ("rows", "empty", "distinct_texts", "missing_app_version"):
            with self.subTest(name=name), self.patched(**{name: 999}):
                with self.assertRaises(prepare.GuardFailed) as caught:
                    self.prep(run=f"run-{name}")
                self.assertIn(name, str(caught.exception))

    def test_a_failure_partway_leaves_no_run_and_no_reviews_and_new_can_be_repeated(self):
        with self.patched(rows=999), self.assertRaises(prepare.GuardFailed):
            self.prep()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
        self.assertEqual(self.prep()["rows"], 20)


@unittest.skipUnless(os.environ.get("RUN_FULL") == "1", "set RUN_FULL=1 to read the 97 MB file")
class FullFile(PrepCase):
    def test_the_supplied_file_gives_the_manifests_counts(self):
        counts = self.prep(path=fixtures.DATA / "spotify_reviews_18months.csv")
        self.assertEqual(
            counts,
            {"rows": 660622, "empty": 13, "distinct_texts": 484189, "copies": 660609 - 484189,
             "missing_app_version": 159701, "verify_sample": 5000, "supplied_file": True},
        )  # fmt: skip


if __name__ == "__main__":
    unittest.main()
