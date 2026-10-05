import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from pipeline import ledger, state
from tests import fixtures

RATE = Decimal("0.042") / 1_000_000  # dollars per token


class LedgerCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.db = fixtures.prepared_db(self.dir)
        self.addCleanup(self.db.close)
        self.billing = fixtures.write_billing(self.dir / "billing.json")
        self.ledger = ledger.Ledger(self.db, self.billing)
        self.session = state.open_session(self.db, "r1", "classify", 1, fixtures.FakeClock())
        self.pending = [
            r["review_id"]
            for r in self.db.execute(
                "SELECT review_id FROM reviews WHERE status='pending' AND cache_source_id IS NULL ORDER BY run_order"
            )
        ]

    def begin(self, request_id="q1", review=0, tokens=2500, led="default"):
        state.begin_attempt(
            self.db, self.ledger if led == "default" else led, request_id=request_id, run="r1", role="enrich",
            review_ids=[self.pending[review]], model="jev-1.13.0", label_config=fixtures.RUN_ARGS["label_config"],
            session_id=self.session, reserve_tokens=tokens,
        )  # fmt: skip

    def rows(self, kind=None):
        sql = "SELECT * FROM ledger" + (" WHERE kind=?" if kind else "")
        return self.db.execute(sql, (kind,) if kind else ()).fetchall()


class Charges(LedgerCase):
    def test_a_reservation_is_held_until_the_request_settles(self):
        self.begin(tokens=2500)
        self.assertEqual(self.ledger.reserved_usd(), 2500 * RATE)
        self.assertEqual(self.ledger.spent_usd(), 0)

    def test_reserve_then_actual_leaves_spent_at_the_actual_and_nothing_reserved(self):
        self.begin(tokens=2500)
        state.finish_attempt(self.db, "q1", outcome="failed", input_tokens=926, output_tokens=215, seconds=0.1, ledger=self.ledger)
        self.assertEqual(self.ledger.spent_usd(), (926 + 215) * RATE)
        self.assertEqual(self.ledger.reserved_usd(), 0)

    def test_an_attempt_with_no_usage_keeps_its_full_reservation_as_spent(self):
        self.begin(tokens=2500)
        state.finish_attempt(self.db, "q1", outcome="failed", error="timeout", seconds=30.0, ledger=self.ledger)
        self.assertEqual(self.ledger.spent_usd(), 2500 * RATE)
        self.assertEqual(self.ledger.reserved_usd(), 0)
        call = self.db.execute("SELECT * FROM calls WHERE request_id='q1'").fetchone()
        self.assertEqual((call["usage_known"], call["input_tokens"], call["outcome"]), (0, None, "failed"))
        self.assertEqual([r["input_tokens"] for r in self.rows("kept")], [2500])

    def test_totals_in_memory_equal_totals_recomputed_from_the_file(self):
        self.ledger.opening(Decimal("0.0485"), Decimal("0.005"))
        self.begin("q1", 0)
        self.begin("q2", 1)
        self.begin("q3", 2)
        state.finish_attempt(self.db, "q1", outcome="failed", input_tokens=900, output_tokens=200, seconds=0.1, ledger=self.ledger)
        state.finish_attempt(self.db, "q2", outcome="failed", seconds=0.1, ledger=self.ledger)
        fresh = ledger.Ledger(self.db, self.billing)
        self.assertEqual(fresh.spent_usd(), self.ledger.spent_usd())
        self.assertEqual(fresh.reserved_usd(), self.ledger.reserved_usd())
        self.assertEqual(fresh.reserved_usd(), 2500 * RATE)


class Cap(LedgerCase):
    def test_a_request_that_would_pass_the_cap_is_refused_and_writes_nothing(self):
        self.ledger = ledger.Ledger(self.db, self.billing, cap_usd=Decimal("0.0002"))
        self.begin("q1", 0, tokens=2500)  # $0.000105 reserved
        with self.assertRaises(ledger.CapReached):
            self.begin("q2", 1, tokens=2500)  # would make $0.00021
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0], 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.ledger.reserved_usd(), 2500 * RATE)

    def test_spent_reserved_and_the_next_reservation_are_added_together(self):
        self.ledger = ledger.Ledger(self.db, self.billing, cap_usd=Decimal("0.00015"))
        self.begin("q1", 0, tokens=1000)
        state.finish_attempt(self.db, "q1", outcome="failed", input_tokens=1000, output_tokens=0, seconds=0.1, ledger=self.ledger)
        self.begin("q2", 1, tokens=1000)  # spent 0.000042 + reserved 0.000042
        self.assertTrue(self.ledger.would_pass_cap(2000))  # + 0.000084 = 0.000168 > 0.00015
        self.assertFalse(self.ledger.would_pass_cap(1000))  # + 0.000042 = 0.000126

    def test_the_probe_spend_counts_against_the_cap_from_the_start(self):
        self.ledger.opening(Decimal("0.0485"), Decimal("0.005"))
        self.assertEqual(self.ledger.spent_usd(), Decimal("0.0535"))
        with self.assertRaises(ledger.AlreadyOpened):
            self.ledger.opening(Decimal("1"), Decimal("1"))
        self.assertEqual(sorted(r["note"] for r in self.rows("opening")), ["estimated", "measured"])


class Rates(LedgerCase):
    def test_editing_the_rate_file_after_a_charge_does_not_move_past_spend(self):
        self.begin("q1", 0)
        state.finish_attempt(self.db, "q1", outcome="failed", input_tokens=1000, output_tokens=0, seconds=0.1, ledger=self.ledger)
        before = self.ledger.spent_usd()
        fixtures.write_billing(self.billing, rate_in="0.001", rate_out="0")
        cheaper = ledger.Ledger(self.db, self.billing)
        self.assertEqual(cheaper.spent_usd(), before)
        self.assertEqual(before, 1000 * RATE)

    def test_a_new_rate_applies_only_to_rows_written_after_it(self):
        self.begin("q1", 0, tokens=1000)
        fixtures.write_billing(self.billing, rate_in="0.084")
        self.ledger = ledger.Ledger(self.db, self.billing)
        self.begin("q2", 1, tokens=1000)
        self.assertEqual(self.ledger.reserved_usd(), 1000 * RATE + 1000 * RATE * 2)

    def test_a_request_is_billed_at_the_rate_in_force_when_it_was_sent(self):
        self.begin("q1", 0, tokens=1000)
        fixtures.write_billing(self.billing, rate_in="0.084")
        later = ledger.Ledger(self.db, self.billing)
        state.finish_attempt(self.db, "q1", outcome="failed", input_tokens=1000, output_tokens=0, seconds=0.1, ledger=later)
        self.assertEqual(later.spent_usd(), 1000 * RATE)

    def test_an_adjustment_moves_spend_by_exactly_its_amount(self):
        self.ledger.adjust(Decimal("0.0123"), "usage page shows output tokens were billed")
        self.assertEqual(self.ledger.spent_usd(), Decimal("0.0123"))
        self.ledger.adjust(Decimal("-0.0023"), "refund")
        self.assertEqual(self.ledger.spent_usd(), Decimal("0.0100"))
        self.assertEqual(len(self.rows("adjust")), 2)


class ExactlyOnce(LedgerCase):
    def test_a_second_settlement_raises_and_leaves_the_ledger_unchanged(self):
        self.begin("q1", 0)
        state.finish_attempt(self.db, "q1", outcome="failed", input_tokens=900, output_tokens=100, seconds=0.1, ledger=self.ledger)
        spent, n = self.ledger.spent_usd(), len(self.rows())
        with self.assertRaises(state.AlreadySettled):
            state.finish_attempt(self.db, "q1", outcome="failed", input_tokens=5000, output_tokens=5000, seconds=0.1, ledger=self.ledger)
        self.assertEqual((self.ledger.spent_usd(), len(self.rows())), (spent, n))
        self.assertEqual(ledger.Ledger(self.db, self.billing).spent_usd(), spent)

    def test_a_reused_request_id_is_refused_and_writes_nothing(self):
        self.begin("q1", 0)
        reserved = self.ledger.reserved_usd()
        with self.assertRaises(state.DuplicateRequest):
            self.begin("q1", 1)
        self.assertEqual(self.ledger.reserved_usd(), reserved)
        self.assertEqual(len(self.rows()), 1)

    def test_a_local_role_writes_no_ledger_row(self):
        self.begin("v1", 0, tokens=0, led=None)
        state.finish_attempt(self.db, "v1", outcome="succeeded", input_tokens=300, output_tokens=40, seconds=0.6)
        self.assertEqual(len(self.rows()), 0)
        call = self.db.execute("SELECT * FROM calls WHERE request_id='v1'").fetchone()
        self.assertEqual((call["outcome"], call["usage_known"], call["input_tokens"]), ("succeeded", 1, 300))


if __name__ == "__main__":
    unittest.main()
