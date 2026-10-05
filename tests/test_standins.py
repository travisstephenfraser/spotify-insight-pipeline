import unittest

from pipeline import jev, labels, standins
from tests import fixtures

SAVED = fixtures.PROBE / "simple.jsonl"


def ask(labeler, text):
    s = jev.load_setup(fixtures.ROOT / "prompts", 0.7)
    return labeler.label(text, jev.build_request(text, s.prompt)), s


class Replay(unittest.TestCase):
    def test_a_pilot_review_gets_the_answer_jev_really_gave(self):
        saved = fixtures.saved_jev()[3]
        reply, _ = ask(standins.ReplayJev(SAVED), saved["request"]["state"])
        self.assertEqual(reply.answer, saved["response"]["answers"])
        self.assertEqual((reply.model, reply.http_status), ("jev-1.13.0", 200))
        self.assertEqual(reply.input_tokens, saved["response"]["usage"]["input_tokens"])

    def test_unseen_text_gets_a_rule_based_answer_that_maps_to_a_valid_record(self):
        labeler = standins.ReplayJev(SAVED)
        for row in fixtures.synthetic_rows(12, empties=0, copies=0):
            text = row["review_text"]
            reply, s = ask(labeler, text)
            rec = jev.to_record(text, reply.answer, features=s.features, cutoff=s.cutoff, label_config=s.label_config)
            labels.validate(text, rec)
            self.assertGreater(reply.input_tokens, 0)

    def test_the_rule_gives_the_synthetic_reviews_a_mix_of_intents(self):
        labeler = standins.ReplayJev(SAVED)
        intents = {ask(labeler, r["review_text"])[0].answer["intent"]["choice"] for r in fixtures.synthetic_rows(12, empties=0, copies=0)}
        self.assertEqual(intents, {"complaint", "praise", "request", "cancellation"})

    def test_a_multi_sentence_text_gets_an_evidence_choice_that_names_a_part(self):
        text = "I love the lyrics. The app crashes on my phone though."
        reply, s = ask(standins.ReplayJev(SAVED), text)
        rec = jev.to_record(text, reply.answer, features=s.features, cutoff=s.cutoff, label_config=s.label_config)
        self.assertIn(rec["evidence_quote"], text)

    def test_every_text_sent_is_logged_in_order(self):
        labeler = standins.ReplayJev(SAVED)
        ask(labeler, "first text")
        ask(labeler, "second text")
        self.assertEqual(labeler.sent, ["first text", "second text"])


class Script(unittest.TestCase):
    def test_a_scripted_text_fails_the_set_number_of_times_then_answers(self):
        labeler = standins.ReplayJev(SAVED, script={"flaky": ["temporary", "temporary"]})
        for _ in range(2):
            with self.assertRaises(jev.Temporary):
                ask(labeler, "flaky")
        self.assertEqual(ask(labeler, "flaky")[0].model, "jev-1.13.0")
        self.assertEqual(labeler.sent, ["flaky", "flaky", "flaky"])

    def test_a_scripted_fatal_response_raises_fatal(self):
        with self.assertRaises(jev.Fatal):
            ask(standins.ReplayJev(SAVED, script={"locked out": ["fatal"]}), "locked out")

    def test_a_scripted_wrong_model_comes_back_as_a_reply_naming_another_model(self):
        reply, _ = ask(standins.ReplayJev(SAVED, script={"drift": ["wrong_model"]}), "drift")
        self.assertNotEqual(reply.model, jev.MODEL)

    def test_a_scripted_invalid_answer_fails_validation(self):
        reply, s = ask(standins.ReplayJev(SAVED, script={"garbled": ["invalid"]}), "garbled")
        with self.assertRaises(labels.InvalidAnswer):
            jev.to_record("garbled", reply.answer, features=s.features, cutoff=s.cutoff, label_config=s.label_config)

    def test_other_texts_are_untouched_by_the_script(self):
        labeler = standins.ReplayJev(SAVED, script={"flaky": ["temporary"]})
        self.assertEqual(ask(labeler, "fine text")[0].http_status, 200)

    def test_an_unknown_script_step_is_an_error_in_the_test_not_a_silent_pass(self):
        with self.assertRaises(ValueError):
            ask(standins.ReplayJev(SAVED, script={"x": ["explode"]}), "x")


if __name__ == "__main__":
    unittest.main()
