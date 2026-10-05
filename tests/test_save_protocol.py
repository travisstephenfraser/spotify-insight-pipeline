import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from pipeline import ledger, state
from tests import fixtures


class SaveCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.db = fixtures.prepared_db(self.dir)
        self.addCleanup(self.db.close)
        self.ledger = ledger.Ledger(self.db, fixtures.write_billing(self.dir / "billing.json"))
        self.session = state.open_session(self.db, "r1", "classify", 1, fixtures.FakeClock())
        # An original that has at least one copy, and one that has none.
        self.shared = self.db.execute(
            "SELECT * FROM reviews o WHERE cache_source_id IS NULL AND status='pending' AND EXISTS "
            "(SELECT 1 FROM reviews c WHERE c.cache_source_id = o.review_id) ORDER BY run_order"
        ).fetchone()
        self.alone = self.db.execute(
            "SELECT * FROM reviews o WHERE cache_source_id IS NULL AND status='pending' AND NOT EXISTS "
            "(SELECT 1 FROM reviews c WHERE c.cache_source_id = o.review_id) ORDER BY run_order"
        ).fetchone()

    def begin(self, request_id, review, role="enrich", led="default", session=None):
        state.begin_attempt(
            self.db, self.ledger if led == "default" else led, request_id=request_id, run="r1", role=role,
            review_ids=[review["review_id"]], model="jev-1.13.0", label_config=fixtures.RUN_ARGS["label_config"],
            session_id=session or self.session, reserve_tokens=2500 if led == "default" else 0,
        )  # fmt: skip

    def family(self, review):
        return self.db.execute(
            "SELECT * FROM reviews WHERE run='r1' AND text_key=? ORDER BY run_order", (review["text_key"],)
        ).fetchall()

    def status(self, review):
        return self.db.execute(
            "SELECT status FROM reviews WHERE run='r1' AND review_id=?", (review["review_id"],)
        ).fetchone()["status"]


class Intent(SaveCase):
    def test_the_intent_row_and_its_reservation_exist_before_anything_is_sent(self):
        self.begin("q1", self.alone)
        call = self.db.execute("SELECT * FROM calls WHERE request_id='q1'").fetchone()
        self.assertEqual((call["outcome"], call["role"], call["session_id"]), ("pending", "enrich", self.session))
        self.assertEqual(self.db.execute("SELECT kind FROM ledger WHERE request_id='q1'").fetchone()["kind"], "reserve")
        self.assertEqual(self.status(self.alone), "pending")


class Completion(SaveCase):
    def finish(self, request_id, review, **changes):
        state.finish_attempt(
            self.db, request_id, outcome="succeeded", input_tokens=926, output_tokens=215, http_status=200, seconds=0.12,
            result=fixtures.result_for(review["review_text"], **changes), ledger=self.ledger,
        )  # fmt: skip

    def test_a_valid_answer_completes_the_original_and_every_copy_together(self):
        self.begin("q1", self.shared)
        self.finish("q1", self.shared)
        family = self.family(self.shared)
        self.assertGreater(len(family), 1)
        self.assertEqual({r["status"] for r in family}, {"completed"})
        self.assertEqual({r["completed_session"] for r in family}, {self.session})
        self.assertEqual(self.status(self.alone), "pending")
        saved = self.db.execute("SELECT * FROM results WHERE run='r1'").fetchall()
        self.assertEqual([(r["text_key"], r["topic"], r["severity"], r["model"]) for r in saved],
                         [(self.shared["text_key"], "playback", 3, "jev-1.13.0")])  # fmt: skip

    def test_a_copy_keeps_its_pointer_after_completion(self):
        self.begin("q1", self.shared)
        self.finish("q1", self.shared)
        original, *copies = self.family(self.shared)
        self.assertIsNone(original["cache_source_id"])
        self.assertEqual({c["cache_source_id"] for c in copies}, {original["review_id"]})

    def test_a_failure_inside_the_save_changes_nothing_at_all(self):
        """Stands in for a kill between the response and the save: all of it lands or none of it."""
        self.begin("q1", self.shared)
        spent = self.ledger.spent_usd()
        broken = fixtures.result_for(self.shared["review_text"])
        del broken["evidence_quote"]
        with self.assertRaises(KeyError):
            state.finish_attempt(
                self.db, "q1", outcome="succeeded", input_tokens=926, output_tokens=215, seconds=0.1, result=broken, ledger=self.ledger
            )
        call = self.db.execute("SELECT * FROM calls WHERE request_id='q1'").fetchone()
        self.assertEqual((call["outcome"], call["input_tokens"]), ("pending", None))
        self.assertEqual({r["status"] for r in self.family(self.shared)}, {"pending"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM results").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM ledger WHERE kind='actual'").fetchone()[0], 0)
        self.assertEqual(self.ledger.spent_usd(), spent)
        self.assertEqual(self.ledger.reserved_usd(), Decimal(2500) * Decimal("0.042") / 1_000_000)

    def test_a_paid_response_that_fails_validation_still_has_its_charge(self):
        self.begin("q1", self.alone)
        state.finish_attempt(
            self.db, "q1", outcome="failed", input_tokens=926, output_tokens=215, http_status=200,
            error="evidence quote is not an exact piece of the review", seconds=0.1, ledger=self.ledger,
        )  # fmt: skip
        self.assertEqual(self.ledger.spent_usd(), Decimal(926 + 215) * Decimal("0.042") / 1_000_000)
        self.assertEqual(self.status(self.alone), "pending")


class Recovery(SaveCase):
    def test_an_orphaned_call_becomes_failed_with_usage_unknown_and_keeps_its_reservation(self):
        self.begin("q1", self.alone)
        counts = state.recover_orphans(self.db, "r1", ledger=self.ledger)
        self.assertEqual(counts, {"enrich": 1})
        call = self.db.execute("SELECT * FROM calls WHERE request_id='q1'").fetchone()
        self.assertEqual((call["outcome"], call["usage_known"], call["input_tokens"]), ("failed", 0, None))
        self.assertEqual(self.ledger.spent_usd(), Decimal(2500) * Decimal("0.042") / 1_000_000)
        self.assertEqual(self.ledger.reserved_usd(), 0)
        self.assertEqual(self.status(self.alone), "pending")

    def test_recovery_never_changes_a_reviews_status(self):
        """A crash in verify must not send a classified review back to be classified again."""
        self.begin("q1", self.shared)
        state.finish_attempt(
            self.db, "q1", outcome="succeeded", input_tokens=926, output_tokens=215, seconds=0.1,
            result=fixtures.result_for(self.shared["review_text"]), ledger=self.ledger,
        )  # fmt: skip
        verify = state.open_session(self.db, "r1", "verify", 1, fixtures.FakeClock())
        self.begin("v1", self.shared, role="verify", led=None, session=verify)
        self.begin("q2", self.alone)
        before = {r["review_id"]: (r["status"], r["attempts"]) for r in self.db.execute("SELECT * FROM reviews")}
        counts = state.recover_orphans(self.db, "r1", ledger=self.ledger)
        self.assertEqual(counts, {"enrich": 1, "verify": 1})
        after = {r["review_id"]: (r["status"], r["attempts"]) for r in self.db.execute("SELECT * FROM reviews")}
        self.assertEqual(after, before)
        self.assertEqual({r["status"] for r in self.family(self.shared)}, {"completed"})

    def test_recovery_leaves_another_runs_calls_alone(self):
        self.begin("q1", self.alone)
        self.assertEqual(state.recover_orphans(self.db, "some-other-run", ledger=self.ledger), {})
        self.assertEqual(self.db.execute("SELECT outcome FROM calls").fetchone()["outcome"], "pending")


class Retry(SaveCase):
    def test_return_to_pending_raises_the_attempt_count_and_touches_nothing_else(self):
        before = dict(self.shared)
        state.return_to_pending(self.db, "r1", self.shared["review_id"])
        after = dict(self.db.execute("SELECT * FROM reviews WHERE review_id=?", (self.shared["review_id"],)).fetchone())
        self.assertEqual(after, {**before, "attempts": 1})
        _, *copies = self.family(self.shared)
        self.assertEqual({c["cache_source_id"] for c in copies}, {self.shared["review_id"]})

    def test_a_quarantined_original_takes_its_copies_and_each_copy_keeps_its_pointer(self):
        state.quarantine(self.db, "r1", self.shared["review_id"], "invalid_model_output")
        original, *copies = self.family(self.shared)
        self.assertEqual({(r["status"], r["reason"]) for r in (original, *copies)}, {("quarantined", "invalid_model_output")})
        self.assertEqual({c["cache_source_id"] for c in copies}, {original["review_id"]})
        self.assertEqual(self.status(self.alone), "pending")


if __name__ == "__main__":
    unittest.main()


class RecoveryByRole(SaveCase):
    def test_recovery_limited_to_one_role_leaves_the_other_roles_open_calls_alone(self):
        self.begin("q1", self.alone)
        verify = state.open_session(self.db, "r1", "verify", 1, fixtures.FakeClock())
        self.begin("v1", self.shared, role="verify", led=None, session=verify)
        self.assertEqual(state.recover_orphans(self.db, "r1", roles=("verify",)), {"verify": 1})
        outcomes = {c["request_id"]: c["outcome"] for c in self.db.execute("SELECT * FROM calls")}
        self.assertEqual(outcomes, {"q1": "pending", "v1": "failed"})
        self.assertEqual(self.ledger.reserved_usd(), Decimal(2500) * Decimal("0.042") / 1_000_000)
