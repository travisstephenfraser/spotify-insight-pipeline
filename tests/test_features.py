import unittest

from pipeline import features, labels
from tests import fixtures

LIST = fixtures.ROOT / "prompts/features-v1.txt"
COUNTS = fixtures.ROOT / "evals/feature_words_out.txt"


class Find(unittest.TestCase):
    ENTRIES = ("playlist", "skip", "shuffle", "smart shuffle", "ads", "sleep timer")

    def find(self, text):
        return features.find(text, self.ENTRIES)

    def test_a_plural_is_found_under_its_entry(self):
        self.assertEqual(self.find("My playlists are gone"), ["playlist"])

    def test_a_longer_word_that_starts_with_an_entry_is_not_found(self):
        self.assertEqual(self.find("it keeps skipping songs"), [])
        self.assertEqual(self.find("reshuffle everything"), [])

    def test_matching_ignores_letter_case_and_returns_lowercase(self):
        self.assertEqual(self.find("SHUFFLE is broken"), ["shuffle"])

    def test_a_phrase_wins_over_the_word_inside_it(self):
        self.assertEqual(self.find("Smart Shuffle ruins my queue"), ["smart shuffle"])

    def test_entries_come_back_once_each_in_the_order_they_appear(self):
        self.assertEqual(self.find("ads, then skips, then more ads and a sleep timer"), ["ads", "skip", "sleep timer"])

    def test_punctuation_around_a_word_does_not_hide_it(self):
        self.assertEqual(self.find("(playlist) shuffle!"), ["playlist", "shuffle"])

    def test_nothing_is_found_in_text_without_letters(self):
        self.assertEqual(self.find("\U0001f621\U0001f621"), [])
        self.assertEqual(self.find(""), [])

    def test_no_entries_means_no_entities(self):
        self.assertEqual(features.find("playlist", ()), [])


class SavedList(unittest.TestCase):
    """The draft list Travis reads at the 100 gate, and the counts behind it."""

    def setUp(self):
        self.entries = features.load(LIST)
        self.counts = {}
        for line in COUNTS.read_text(encoding="utf-8").splitlines():
            if "\t" in line and not line.startswith("#"):
                name, n = line.split("\t")
                self.counts[name] = int(n)

    def test_every_listed_entry_was_found_in_at_least_100_reviews(self):
        self.assertGreater(len(self.entries), 10)
        for entry in self.entries:
            self.assertGreaterEqual(self.counts[entry], 100, entry)

    def test_every_candidate_under_100_is_left_out(self):
        self.assertEqual(set(self.entries), {name for name, n in self.counts.items() if n >= 100})

    def test_no_entry_is_a_topic_or_intent_name(self):
        self.assertFalse(set(self.entries) & (set(labels.TOPICS) | set(labels.INTENTS)))

    def test_the_list_has_no_duplicates_and_is_lowercase(self):
        self.assertEqual(len(self.entries), len(set(self.entries)))
        self.assertEqual(list(self.entries), [e.lower() for e in self.entries])


if __name__ == "__main__":
    unittest.main()
