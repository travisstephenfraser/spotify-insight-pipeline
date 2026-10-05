"""The cap on total Jev spend. Travis set it at $25 on 2026-10-04 and raised it to $35 on 2026-10-05."""

import argparse
import csv
import inspect
import sys
import unittest
from decimal import Decimal

from cost import calc
from pipeline import cli, export, ledger
from tests import fixtures


class TheCap(unittest.TestCase):
    def test_the_cap_is_35_dollars(self):
        self.assertEqual(ledger.CAP_USD, Decimal("35"))

    def test_every_default_reads_the_one_cap(self):
        """A second copy of the number would let one command guard a different budget from the rest."""
        sys.path.insert(0, str(fixtures.ROOT / "evals"))
        import common

        evals = argparse.ArgumentParser()
        common.add_arguments(evals)
        defaults = {
            "pipeline command": cli.parser().parse_args(["status", "--run", "x"]).cap,
            "eval scripts": evals.parse_args([]).cap,
            "ledger": inspect.signature(ledger.Ledger.__init__).parameters["cap_usd"].default,
            "export": inspect.signature(export.export).parameters["cap_usd"].default,
            "calculator": inspect.signature(calc.project).parameters["cap"].default,
        }
        for name, value in defaults.items():
            with self.subTest(default=name):
                self.assertEqual(Decimal(value), ledger.CAP_USD)

    def test_the_calculators_assumption_is_the_same_cap(self):
        with open(fixtures.ROOT / "cost" / "assumptions.csv", encoding="utf-8", newline="") as f:
            rows = {r["item"]: r["value"] for r in csv.DictReader(f)}
        self.assertEqual(Decimal(rows["spending_limit_usd"]), ledger.CAP_USD)


if __name__ == "__main__":
    unittest.main()
