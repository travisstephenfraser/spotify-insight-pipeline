import copy
import unittest

from pipeline import jev, labels
from tests import fixtures

PROMPTS = fixtures.ROOT / "prompts"
FEATURES = ("playlist", "shuffle", "premium", "ads")


def setup(cutoff=0.70):
    """The probe's wording: the saved pilot answers these tests replay were made with it."""
    return jev.load_setup(PROMPTS, cutoff, prompt_name=jev.PROBE_PROMPT_FILE)


def record(saved, cutoff=0.70):
    s = setup(cutoff)
    return jev.to_record(
        saved["request"]["state"], saved["response"]["answers"], features=s.features, cutoff=s.cutoff, label_config=s.label_config
    )


def stand_in_answer(text, prompt):
    """A plausible answer to the request built for `text`: first option of each question, tone 2."""
    request = jev.build_request(text, prompt)
    answers = {}
    for name, q in request["questions"].items():
        if q["type"] == "score":
            answers[name] = {"type": "score", "score": 2.0, "probabilities": {"2": 1.0}}
        else:
            first = next(iter(q["criteria"]))
            answers[name] = {"type": "choice", "choice": first, "probabilities": {k: float(k == first) for k in q["criteria"]}}
    return answers


class Setup(unittest.TestCase):
    def test_label_config_names_model_prompt_schema_and_cut_off(self):
        self.assertEqual(setup(0.7).label_config, "jev-1.13.0/prompt-v1/schema-v1/cut-0.70")
        self.assertEqual(setup(0.85).label_config, "jev-1.13.0/prompt-v1/schema-v1/cut-0.85")

    def test_the_prompts_choices_are_the_contracts_labels(self):
        prompt = setup().prompt
        self.assertEqual(set(prompt["topic"]["criteria"]), set(labels.TOPICS))
        self.assertEqual(set(prompt["intent"]["criteria"]), set(labels.INTENTS))
        self.assertEqual(set(prompt["severity"]["criteria"]), set(labels.SEVERITY))
        self.assertFalse(any(k.isdigit() for k in prompt["severity"]["criteria"]))
        self.assertEqual(len(prompt["tone"]["criteria"]), 5)

    def test_hashes_cover_everything_that_shapes_a_label(self):
        hashes = setup().hashes()
        self.assertEqual(set(hashes), {"prompt:enrich-v1.json", "features", "splitter", "cutoff"})
        self.assertNotEqual(setup(0.8).hashes()["cutoff"], hashes["cutoff"])


class BuildRequest(unittest.TestCase):
    def test_the_request_is_the_one_the_probe_sent_for_every_pilot_review(self):
        """Known answer: the 100 requests whose answers were measured on 2026-10-04."""
        prompt = setup().prompt
        for saved in fixtures.saved_jev():
            self.assertEqual(jev.build_request(saved["request"]["state"], prompt), saved["request"])

    def test_the_same_text_always_builds_the_same_request(self):
        prompt = setup().prompt
        self.assertEqual(jev.build_request("Bad app. Fix it", prompt), jev.build_request("Bad app. Fix it", prompt))

    def test_two_texts_get_different_option_orders(self):
        prompt = setup().prompt
        one = list(jev.build_request("The app crashes", prompt)["questions"]["topic"]["criteria"])
        two = list(jev.build_request("I love the lyrics", prompt)["questions"]["topic"]["criteria"])
        self.assertEqual(sorted(one), sorted(two))
        self.assertNotEqual(one, two)

    def test_a_one_piece_text_has_no_evidence_question(self):
        self.assertNotIn("evidence", jev.build_request("Bad app", setup().prompt)["questions"])

    def test_a_request_over_255_options_is_too_large(self):
        with self.assertRaises(jev.TooLarge):
            jev.build_request(" ".join(f"Sentence {i}." for i in range(300)), setup().prompt)

    def test_a_request_over_32000_estimated_tokens_is_too_large(self):
        with self.assertRaises(jev.TooLarge):
            jev.build_request("word " * 20_000, setup().prompt)  # 100,000 bytes is about 41,000 tokens


class ToRecord(unittest.TestCase):
    def test_the_100_saved_answers_become_100_valid_records_with_the_probes_labels(self):
        known = fixtures.probe_records()
        for saved in fixtures.saved_jev():
            rec = record(saved)
            labels.validate(saved["request"]["state"], rec)
            want = known[saved["review_id"]]
            self.assertEqual((rec["topic"], rec["intent"], rec["severity"]), (want["topic"], want["intent"], want["severity"]))
            self.assertEqual(rec["evidence_quote"], want["quote"])
            self.assertEqual(rec["sentiment"], want["sentiment"])

    def test_the_flag_counts_match_the_probes_table(self):
        """Known answer from flag_probe.py, recorded in CLAUDE.md: reviews flagged of 100 at each cut-off."""
        for cutoff, flagged in ((0.6, 17), (0.7, 26), (0.8, 38), (0.9, 54)):
            got = sum(record(saved, cutoff)["needs_review"] for saved in fixtures.saved_jev())
            self.assertEqual(got, flagged, cutoff)

    def test_min_top_probability_is_the_lowest_of_the_three_top_probabilities(self):
        saved = fixtures.saved_jev()[0]
        answers = saved["response"]["answers"]
        tops = [max(answers[q]["probabilities"].values()) for q in ("topic", "intent", "severity")]
        self.assertEqual(record(saved)["min_top_probability"], min(tops))

    def test_a_one_piece_text_quotes_the_whole_text_without_outer_whitespace(self):
        s = setup()
        text = "  Bad app \n"
        rec = jev.to_record(text, stand_in_answer(text, s.prompt), features=s.features, cutoff=0.7, label_config=s.label_config)
        self.assertEqual(rec["evidence_quote"], "Bad app")

    def test_entities_are_the_feature_words_found_in_the_text(self):
        s = setup()
        text = "Premium is fine but the playlists keep reshuffling"
        rec = jev.to_record(text, stand_in_answer(text, s.prompt), features=FEATURES, cutoff=0.7, label_config=s.label_config)
        self.assertEqual(rec["entities"], ["premium", "playlist"])
        self.assertEqual(jev.entities(text, FEATURES), ["premium", "playlist"])

    def test_the_record_carries_its_label_config(self):
        self.assertEqual(record(fixtures.saved_jev()[0])["label_config"], "jev-1.13.0/prompt-v1/schema-v1/cut-0.70")

    def test_a_bad_answer_raises(self):
        s = setup()
        saved = fixtures.saved_jev()[0]
        text, good = saved["request"]["state"], saved["response"]["answers"]

        def broken(change):
            answers = copy.deepcopy(good)
            change(answers)
            return answers

        cases = {
            "tone off the scale": lambda a: a["tone"].update(score=7),
            "unknown topic": lambda a: a["topic"].update(choice="pricing"),
            "unknown severity name": lambda a: a["severity"].update(choice="3"),
            "missing intent": lambda a: a.pop("intent"),
            "no probabilities": lambda a: a["topic"].pop("probabilities"),
            "answers is not an object": None,
        }
        for name, change in cases.items():
            with self.subTest(name=name), self.assertRaises(labels.InvalidAnswer):
                answers = broken(change) if change else ["nope"]
                jev.to_record(text, answers, features=s.features, cutoff=0.7, label_config=s.label_config)

    def test_an_evidence_choice_that_names_no_part_raises(self):
        s = setup()
        saved = next(x for x in fixtures.saved_jev() if "evidence" in x["response"]["answers"])
        answers = copy.deepcopy(saved["response"]["answers"])
        answers["evidence"]["choice"] = "part_zz"
        with self.assertRaises(labels.InvalidAnswer):
            jev.to_record(saved["request"]["state"], answers, features=s.features, cutoff=0.7, label_config=s.label_config)


class AwkwardText(unittest.TestCase):
    """Review Focus 2."""

    def test_emoji_only_and_the_literal_none_build_a_request_and_map_to_a_valid_record(self):
        s = setup()
        for text in ("\U0001f621\U0001f621\U0001f621", "None", *fixtures.AWKWARD[:2]):
            with self.subTest(text=text[:12]):
                rec = jev.to_record(text, stand_in_answer(text, s.prompt), features=s.features, cutoff=0.7, label_config=s.label_config)
                labels.validate(text, rec)
                self.assertIn(rec["evidence_quote"], text)


if __name__ == "__main__":
    unittest.main()
