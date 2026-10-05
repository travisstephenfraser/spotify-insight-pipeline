import unittest

from pipeline import hashing
from tests import fixtures


class RowSha(unittest.TestCase):
    def test_row_sha_matches_checker(self):
        rows = fixtures.supplied("cost_100.csv")
        self.assertEqual(len(rows), 100)
        for row in rows:
            self.assertEqual(hashing.row_sha(row), fixtures.checker().row_sha(row))

    def test_fields_are_the_checkers(self):
        self.assertEqual(hashing.FIELDS, fixtures.checker().FIELDS)

    def test_awkward_text(self):
        for text in fixtures.AWKWARD:
            row = dict(zip(hashing.FIELDS, ("id-1", text, "1", "0", "", "2024-01-01 00:00:00")))
            with self.subTest(text=text[:20]):
                self.assertEqual(hashing.row_sha(row), fixtures.checker().row_sha(row))

    def test_file_sha_matches_checker(self):
        path = fixtures.DATA / "cost_100.csv"
        self.assertEqual(hashing.file_sha(path), fixtures.checker().sha(path))


class RunOrder(unittest.TestCase):
    def test_run_order_known_answer(self):
        ids = [r["review_id"] for r in fixtures.supplied("checkpoint_500.csv")]
        self.assertEqual(ids, sorted(ids, key=lambda i: hashing.order_key(fixtures.SEED, i)))

    def test_golden_sorts_before_every_analysis_row(self):
        golden = [r["review_id"] for r in fixtures.supplied("golden_50_to_label.csv")]
        analysis = [r["review_id"] for r in fixtures.supplied("analysis_10000.csv")]
        key = lambda i: hashing.order_key(fixtures.SEED, i)  # noqa: E731
        self.assertLess(max(map(key, golden)), min(map(key, analysis)))


class TextKey(unittest.TestCase):
    def test_one_trailing_space_is_a_different_text(self):
        self.assertNotEqual(hashing.text_key("bad app"), hashing.text_key("bad app "))

    def test_identical_bytes_share_a_key(self):
        self.assertEqual(hashing.text_key("\U0001f621 bad"), hashing.text_key("\U0001f621 bad"))
        self.assertEqual(len(hashing.text_key("x")), 64)


if __name__ == "__main__":
    unittest.main()
