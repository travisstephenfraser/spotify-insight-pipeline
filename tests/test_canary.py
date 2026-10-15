"""The Jev 1.14 canary (validation log entry 44): the saved report is what the saved calls give, and each check on
the measurement itself raises when its failure is planted.

No network and no key: the calls were made once, on 2026-10-15, and are committed.
"""

import copy
import importlib.util
import json
import unittest

from tests import fixtures

HERE = fixtures.ROOT / "experiments/2026-10-15/jev-1.14-canary"
_spec = importlib.util.spec_from_file_location("canary", HERE / "canary.py")
canary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canary)


class Canary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = json.loads(canary.ITEMS.read_text(encoding="utf-8"))
        cls.rows = canary.load_rows()
        cls.hand = canary.hand_labels()
        cls.stored = canary.load_stored({it["id"] for it in cls.items})

    def report(self, rows):
        return canary.analyze(rows, self.items, self.hand, self.stored)

    def test_the_saved_report_is_what_the_saved_calls_give(self):
        saved = json.loads(canary.REPORT.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(self.report(self.rows))), saved)

    def test_the_figures_the_readme_and_the_log_quote(self):
        r = json.loads(canary.REPORT.read_text(encoding="utf-8"))
        self.assertEqual((r["anchor"]["any"], r["anchor"]["n"]), (72, 2000))
        self.assertEqual(
            (r["pairs"]["random|b14-c14"]["any"], r["pairs"]["random|a13-b14"]["any"]),
            (63, 210),
        )
        self.assertEqual(
            (
                r["hand"]["a13|by_rule"]["all_three"],
                r["hand"]["b14|by_rule"]["all_three"],
                r["hand"]["b14|by_rule"]["n"],
            ),
            (37, 39, 68),
        )
        self.assertEqual(r["spend"]["usd"], 0.3164)

    def test_a_reply_that_names_another_model_stops_the_report(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r["arm"] == "b14" and r["status"] == "ok")[
            "model_reply"
        ] = "jev-1.13.0"
        with self.assertRaisesRegex(canary.Refused, "another model"):
            self.report(rows)

    def test_1_13_that_does_not_reproduce_the_stored_run_stops_the_report(self):
        rows = copy.deepcopy(self.rows)
        mine = [r for r in rows if r["arm"] == "a13" and r["status"] == "ok"]
        records = [r["record"] for r in mine]
        for r, rec in zip(
            mine, records[1:] + records[:1]
        ):  # every 1.13 label moved to the next text
            r["record"] = rec
        with self.assertRaisesRegex(canary.Refused, "differs from the stored run"):
            self.report(rows)

    def test_one_model_behind_both_names_stops_the_report(self):
        rows = copy.deepcopy(self.rows)
        a13 = {r["id"]: r for r in rows if r["arm"] == "a13" and r["status"] == "ok"}
        for r in rows:
            if r["arm"] == "b14" and r["status"] == "ok" and r["id"] in a13:
                r["answer"], r["record"] = (
                    a13[r["id"]]["answer"],
                    a13[r["id"]]["record"],
                )
        with self.assertRaisesRegex(canary.Refused, "identical"):
            self.report(rows)


if __name__ == "__main__":
    unittest.main()
