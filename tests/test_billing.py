"""Whether Jev's output tokens are billed.

Settled on 2026-10-05 from the TypeSafe usage page (validation log entry 24): they are not.
The ledger and the calculator each hold the rate; these tests hold them to the same answer
and keep the evidence's arithmetic from drifting.
"""

import csv
import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from pipeline import ledger, state
from tests import fixtures


def load_check():
    path = fixtures.ROOT / "experiments/2026-10-05/billing/usage_page_check.py"
    spec = importlib.util.spec_from_file_location("usage_page_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OutputTokens(unittest.TestCase):
    def test_the_ledger_charges_input_tokens_only(self):
        billing = json.loads((fixtures.ROOT / "pipeline/billing.json").read_text(encoding="utf-8"))["jev"]
        self.assertEqual(Decimal(billing["usd_per_mtok_in"]), Decimal("0.042"))
        self.assertEqual(Decimal(billing["usd_per_mtok_out"]), 0)
        self.assertEqual(billing["output_rate_checked"], "2026-10-05")
        with tempfile.TemporaryDirectory() as tmp:
            db = state.connect(Path(tmp) / "state.sqlite", synchronous="OFF")
            self.addCleanup(db.close)
            led = ledger.Ledger(db, fixtures.ROOT / "pipeline/billing.json")
            session = state.open_session(db, "r", "classify", 1, fixtures.FakeClock())
            state.begin_attempt(db, led, request_id="q", run="r", role="enrich", review_ids=["x"], model="m", label_config="c", session_id=session, reserve_tokens=3000)
            state.finish_attempt(db, "q", outcome="succeeded", input_tokens=1000, output_tokens=200, seconds=0.1, ledger=led)
            self.assertEqual(led.spent_usd(), Decimal(1000) * Decimal("0.042") / 1_000_000)

    def test_the_calculator_prices_output_tokens_at_zero_and_no_longer_calls_them_unknown(self):
        with open(fixtures.ROOT / "cost/rates.csv", encoding="utf-8", newline="") as f:
            rows = {r["item"]: r for r in csv.DictReader(f)}
        row = rows["jev_output_tokens"]
        self.assertEqual(Decimal(row["usd_per_unit"]), 0)
        self.assertEqual(row["checked"], "2026-10-05")
        self.assertIn("usage page", row["note"])

    def test_the_usage_page_fits_input_only_billing_and_not_billing_of_every_token(self):
        """The evidence itself: a slip in its arithmetic would look like a settled question."""
        r = load_check().readings()
        self.assertTrue(r["a_fits"])
        self.assertFalse(r["b_fits"])
        self.assertEqual(r["logged_requests"], 325)
        self.assertEqual(round(r["b_usd"], 4), Decimal("0.0689"))
        self.assertGreater(r["a_output_per_request_low"], 150)  # a range wide enough to fit anything would prove nothing
        self.assertLess(r["a_output_per_request_high"] - r["a_output_per_request_low"], 20)


if __name__ == "__main__":
    unittest.main()
