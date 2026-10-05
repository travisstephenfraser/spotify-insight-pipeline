import json
import tempfile
import unittest
from pathlib import Path

from pipeline import gemma, group, hashing, labels, standins
from tests import fixtures


class GroupCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def classified(self, name="a", **options):
        db, _ = fixtures.classified_db(self.dir / name, **options)
        self.addCleanup(db.close)
        return db

    @staticmethod
    def members(db):
        return db.execute("SELECT issue_id, review_id FROM membership WHERE run='r1' ORDER BY issue_id, review_id").fetchall()

    @staticmethod
    def labels_of(db):
        return {
            r["review_id"]: r
            for r in db.execute(
                "SELECT r.review_id, r.status, r.cache_source_id, s.topic, s.intent, s.evidence_quote FROM reviews r "
                "LEFT JOIN results s ON s.run=r.run AND s.text_key=r.text_key WHERE r.run='r1'"
            )
        }

    @staticmethod
    def calls(db):
        return db.execute("SELECT * FROM calls WHERE run='r1' AND role='group' ORDER BY rowid").fetchall()


class Definitions(unittest.TestCase):
    def test_the_topic_definitions_are_the_contracts_word_for_word(self):
        contract = (fixtures.DATA / "GRADING_CONTRACT.md").read_text(encoding="utf-8")
        self.assertEqual(set(labels.TOPIC_DEFINITIONS), set(labels.TOPICS))
        for topic, definition in labels.TOPIC_DEFINITIONS.items():
            self.assertIn(f"| `{topic}` | {definition} |", contract)


class Assign(GroupCase):
    def test_every_complaint_and_cancellation_joins_the_issue_for_its_topic_and_nothing_else_does(self):
        db = self.classified()
        n = group.assign(db, "r1")
        got = self.labels_of(db)
        members = self.members(db)
        self.assertEqual(n, len(members))
        expected = {(f"issue-{r['topic']}", rid) for rid, r in got.items() if r["status"] == "completed" and r["intent"] in ("complaint", "cancellation")}
        self.assertEqual({(m["issue_id"], m["review_id"]) for m in members}, expected)
        self.assertGreater(n, 0)
        self.assertLess(n, 28)  # praise and requests are completed but are not members

    def test_each_member_is_in_exactly_one_issue(self):
        db = self.classified()
        group.assign(db, "r1")
        ids = [m["review_id"] for m in self.members(db)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_a_copy_is_a_member_in_its_own_right(self):
        db = self.classified()
        group.assign(db, "r1")
        got = self.labels_of(db)
        member_ids = {m["review_id"] for m in self.members(db)}
        copies = [rid for rid, r in got.items() if r["cache_source_id"] and r["intent"] in ("complaint", "cancellation")]
        self.assertTrue(copies)
        self.assertTrue(set(copies) <= member_ids)

    def test_assigning_twice_changes_nothing(self):
        db = self.classified()
        group.assign(db, "r1")
        first = [tuple(m) for m in self.members(db)]
        group.assign(db, "r1")
        self.assertEqual([tuple(m) for m in self.members(db)], first)

    def test_a_quarantined_review_is_not_a_member(self):
        rows = fixtures.synthetic_rows(10, empties=0, copies=0)
        db = self.classified(rows=rows, labeler=standins.ReplayJev(script={rows[0]["review_text"]: ["invalid", "invalid"]}))
        group.assign(db, "r1")
        self.assertNotIn(rows[0]["review_id"], {m["review_id"] for m in self.members(db)})


class Naming(GroupCase):
    def named(self, fake=None, name="a", **options):
        db = self.classified(name, **options)
        group.assign(db, "r1")
        fake = fake or standins.StandinGemma()
        return db, fake, group.name_issues(db, "r1", fake)

    def test_one_call_names_each_issue_that_has_members(self):
        db, fake, out = self.named()
        issues = db.execute("SELECT * FROM issues WHERE run='r1' ORDER BY issue_id").fetchall()
        with_members = sorted({m["issue_id"] for m in self.members(db)})
        self.assertEqual([i["issue_id"] for i in issues], with_members)
        self.assertEqual((out.ended_how, out.named, out.cached, out.fallbacks), ("finished", len(with_members), 0, 0))
        self.assertEqual(len(fake.calls), len(with_members))
        self.assertTrue(all(i["name"].strip() and i["description"].strip() and i["model"] == gemma.MODEL for i in issues))

    def test_each_naming_call_is_logged_as_a_group_call_with_no_review_ids(self):
        db, _, _ = self.named()
        calls = self.calls(db)
        self.assertEqual({(c["outcome"], c["review_ids_json"], c["model"]) for c in calls}, {("succeeded", "[]", gemma.MODEL)})
        self.assertEqual({type(c["input_tokens"]) for c in calls}, {int})

    def test_the_quotes_are_the_first_by_the_sample_seed_among_the_issues_originals(self):
        db, fake, _ = self.named()
        got = self.labels_of(db)
        for _, user, _, max_tokens in fake.calls:
            pack = json.loads(user)
            issue_id = pack["issue_id"]
            originals = [m["review_id"] for m in self.members(db) if m["issue_id"] == issue_id and not got[m["review_id"]]["cache_source_id"]]
            expected = sorted(originals, key=lambda i: hashing.order_key("sample-v1", i))[:30]
            self.assertEqual([q["review_id"] for q in pack["quotes"]], expected)
            self.assertEqual([q["quote"] for q in pack["quotes"]], [got[i]["evidence_quote"] for i in expected])
            self.assertEqual(pack["definition"], labels.TOPIC_DEFINITIONS[issue_id.removeprefix("issue-")])
            self.assertEqual(max_tokens, 300)

    def test_at_most_the_asked_number_of_quotes_is_sent(self):
        db = self.classified()
        group.assign(db, "r1")
        fake = standins.StandinGemma()
        group.name_issues(db, "r1", fake, quotes_per_issue=2)
        self.assertTrue(all(len(json.loads(user)["quotes"]) <= 2 for _, user, _, _ in fake.calls))

    def test_a_quote_over_500_characters_is_left_out_and_the_next_one_taken(self):
        rows = fixtures.synthetic_rows(8, empties=0, copies=0)
        long_text = "The app crashes " + "again and again " * 40  # one piece, about 660 characters
        rows[0]["review_text"] = long_text
        db, fake, _ = self.named(rows=rows)
        quotes = [q["quote"] for _, user, _, _ in fake.calls for q in json.loads(user)["quotes"]]
        self.assertNotIn(long_text.strip(), quotes)
        self.assertTrue(all(len(q) <= 500 for q in quotes))
        self.assertIn(rows[0]["review_id"], {m["review_id"] for m in self.members(db)})

    def test_a_warm_call_with_the_same_inputs_makes_no_new_request(self):
        db, _, first = self.named()
        again = standins.StandinGemma()
        out = group.name_issues(db, "r1", again)
        self.assertEqual((again.calls, out.named, out.cached), ([], 0, first.named))
        self.assertEqual(out.ended_how, "finished")

    def test_an_input_with_no_complaints_makes_no_naming_call_and_says_so(self):
        rows = fixtures.synthetic_rows(6, empties=0, copies=0)
        for i, row in enumerate(rows):
            row["review_text"] = f"I love the lyrics feature, number {i}"
        db = self.classified(rows=rows)
        self.assertEqual(group.assign(db, "r1"), 0)
        fake = standins.StandinGemma()
        out = group.name_issues(db, "r1", fake)
        self.assertEqual((out.ended_how, fake.calls), ("no_complaints", []))

    def test_an_invalid_name_is_retried_once(self):
        db, fake, out = self.named(standins.StandinGemma(script=["invalid"]))
        self.assertEqual((out.ended_how, out.fallbacks), ("finished", 0))
        self.assertEqual([c["outcome"] for c in self.calls(db)][:2], ["failed", "succeeded"])

    def test_two_invalid_names_fall_back_to_the_topic_and_the_contracts_definition(self):
        db, _, out = self.named(standins.StandinGemma(script=["invalid", "invalid"]))
        self.assertEqual((out.ended_how, out.fallbacks), ("finished", 1))
        first = db.execute("SELECT * FROM issues WHERE run='r1' ORDER BY issue_id").fetchone()
        topic = first["issue_id"].removeprefix("issue-")
        self.assertEqual((first["name"], first["description"], first["model"]), (topic, labels.TOPIC_DEFINITIONS[topic], None))

    def test_a_blank_or_overlong_name_counts_as_invalid(self):
        for bad in ({"name": " ", "description": "x"}, {"name": "n" * 200, "description": "x"}, {"name": "ok", "description": 7}):
            with self.subTest(bad=bad):
                db, _, out = self.named(standins.StandinGemma(respond=lambda s, u, sch, bad=bad: bad), name=str(len(str(bad))))
                self.assertEqual(out.ended_how, "no_success")
                self.assertTrue(all(c["outcome"] == "failed" for c in self.calls(db)))

    def test_when_no_naming_call_succeeds_the_stage_says_so(self):
        _, _, out = self.named(standins.StandinGemma(respond=lambda s, u, sch: {"name": "", "description": ""}))
        self.assertEqual(out.ended_how, "no_success")
        self.assertEqual(out.named, 0)

    def test_a_server_problem_halts_naming_and_a_later_call_finishes_it(self):
        db, _, out = self.named(standins.StandinGemma(script=["server_problem"]))
        self.assertEqual((out.ended_how, out.named), ("server_problem", 0))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM issues").fetchone()[0], 0)
        self.assertEqual(group.name_issues(db, "r1", standins.StandinGemma()).ended_how, "finished")

    def test_names_never_change_membership(self):
        db = self.classified()
        group.assign(db, "r1")
        before = [tuple(m) for m in self.members(db)]
        group.name_issues(db, "r1", standins.StandinGemma())
        self.assertEqual([tuple(m) for m in self.members(db)], before)


if __name__ == "__main__":
    unittest.main()
