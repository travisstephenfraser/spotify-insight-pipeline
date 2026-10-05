import unittest

from pipeline import splitter
from tests import fixtures


class Pieces(unittest.TestCase):
    def test_every_piece_of_every_pilot_review_is_an_exact_substring(self):
        most = 0
        for row in fixtures.supplied("cost_100.csv"):
            parts = splitter.pieces(row["review_text"])
            self.assertTrue(parts)
            for part in parts:
                self.assertIn(part, row["review_text"])
            most = max(most, len(parts))
        self.assertLessEqual(most, 39)

    def test_the_pieces_are_the_ones_the_probe_sent(self):
        """Known answer: the tagged parts in the 25 saved multi-sentence requests."""
        for saved in fixtures.saved_jev():
            asked = saved["request"]["questions"].get("evidence")
            parts = splitter.pieces(saved["request"]["state"])
            if asked:
                self.assertEqual(sorted(parts), sorted(asked["criteria"].values()))
            else:
                self.assertEqual(len(parts), 1)

    def test_sentences_and_lines_split(self):
        self.assertEqual(splitter.pieces("Bad app. It crashes!\nFix it"), ["Bad app.", "It crashes!", "Fix it"])

    def test_a_piece_with_no_letter_or_digit_is_dropped_when_others_have_content(self):
        self.assertEqual(splitter.pieces("Great app. !!!"), ["Great app."])

    def test_text_with_no_letter_or_digit_is_one_piece_the_whole_text_trimmed(self):
        self.assertEqual(splitter.pieces("  \U0001f621\U0001f621 !!  "), ["\U0001f621\U0001f621 !!"])

    def test_one_sentence_is_one_piece(self):
        self.assertEqual(splitter.pieces("None"), ["None"])


if __name__ == "__main__":
    unittest.main()
