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


def load_check(day="2026-10-05"):
    path = fixtures.ROOT / f"experiments/{day}/billing/usage_page_check.py"
    spec = importlib.util.spec_from_file_location(f"usage_page_check_{day.replace('-', '_')}", path)
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
        self.assertEqual(row["checked"], "2026-10-07")  # the second reading, after the full run
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


class SecondReading(unittest.TestCase):
    """The reading after the full run (validation log entry 41). The evidence itself, held so it cannot pass by accident."""

    @classmethod
    def setUpClass(cls):
        cls.check = load_check("2026-10-07")
        cls.groups = json.loads(cls.check.SAVED.read_text(encoding="utf-8"))

    def changed(self, run, **add):
        return [{**g, **{k: g[k] + v for k, v in add.items()}} if g["run"] == run and not g["before_first_reading"] else g for g in self.groups]

    def test_the_rise_between_the_readings_is_what_was_logged_to_the_token(self):
        r = self.check.check(self.groups)
        self.assertEqual(r["rise"], {"requests": 493_699, "tokens": 600_815_745})
        self.assertEqual(sum(g["succeeded"] for g in r["on_page"]), 493_699)
        self.assertEqual(sum(g["input_tokens"] + g["output_tokens"] for g in r["on_page"]), 600_815_745)
        self.assertEqual([g["run"] for g in r["not_yet"]], ["demo-100b"])

    def test_the_full_run_in_that_file_is_the_exported_full_run(self):
        """The saved totals come from a state file a clone does not have. The full run's row is held to the committed export."""
        full = next(g for g in self.groups if g["run"] == "full")
        summary = json.loads((fixtures.ROOT / "runs/full/run_summary.json").read_text(encoding="utf-8"))
        self.assertEqual((full["calls"], full["succeeded"], full["failed"]), (484_213, 484_189, 24))
        self.assertEqual((full["input_tokens"], full["output_tokens"]), (484_181_345, 105_139_277))
        self.assertIn("484181345", json.dumps(summary))
        self.assertIn("105139277", json.dumps(summary))

    def test_the_dollars_fit_input_only_billing_and_not_billing_of_every_token(self):
        r = self.check.check(self.groups)
        self.assertTrue(r["input_only_fits"])
        self.assertEqual(round(r["input_only_usd"], 2), Decimal("20.79"))
        self.assertEqual(round(r["every_token_usd"], 2), Decimal("25.30"))

    def test_one_token_more_or_one_failed_attempt_counted_and_nothing_matches(self):
        for groups in (self.changed("full", output_tokens=1), self.changed("full", succeeded=24), self.changed("gate-10k", input_tokens=-1)):
            with self.assertRaises(self.check.Mismatch):
                self.check.check(groups)

    def test_calls_before_the_first_reading_must_be_the_wording_trial(self):
        wrong = [{**g, "calls": g["calls"] - 1} if g["before_first_reading"] else g for g in self.groups]
        with self.assertRaises(self.check.Mismatch):
            self.check.check(wrong)

    def test_the_saved_output_is_what_the_script_prints_now(self):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.check.main([]), 0)
        self.assertEqual(out.getvalue(), (self.check.HERE / "usage_page_check_out.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
