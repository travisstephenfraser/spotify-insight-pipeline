"""The frozen enrich wording.

Travis froze prompts/enrich-v2.json on 2026-10-05, after the wording trial (validation log
entry 23). The probe's wording, enrich-v1.json, stays in the repo: the trial compares
against it and the saved pilot answers were made with it.
"""

import argparse
import json
import sys
import unittest

from pipeline import jev
from tests import fixtures
from tests.test_review_fixes import TmpCase


class FrozenWording(TmpCase):
    def test_the_frozen_wording_is_v2(self):
        self.assertEqual(jev.PROMPT_FILE, "enrich-v2.json")
        self.assertEqual(jev.load_setup(fixtures.ROOT / "prompts", 0.7).label_config, "jev-1.13.0/prompt-v2/schema-v1/cut-0.70")

    def test_a_new_run_that_names_no_wording_is_labeled_under_the_frozen_one(self):
        """The paid pilot and every gate start this way, so the default is what the full pass will be labeled with."""
        code, text = self.cli("run", "--run", "r", "--new", "--input", self.csv, "--standin", "--verify-size", "15")
        self.assertEqual(code, 0, text)
        row = self.db().execute("SELECT * FROM runs WHERE run='r'").fetchone()
        self.assertEqual(row["label_config"], "jev-1.13.0/prompt-v2/schema-v1/cut-0.70")
        self.assertIn("prompt:enrich-v2.json", json.loads(row["hashes_json"]))
        configs = {c["label_config"] for c in self.db().execute("SELECT label_config FROM calls WHERE run='r' AND role='enrich'")}
        self.assertEqual(configs, {"jev-1.13.0/prompt-v2/schema-v1/cut-0.70"})

    def test_the_eval_scripts_score_the_frozen_wording_unless_told_otherwise(self):
        sys.path.insert(0, str(fixtures.ROOT / "evals"))
        import common

        ap = argparse.ArgumentParser()
        common.add_arguments(ap)
        self.assertEqual(ap.parse_args([]).prompt_file, jev.PROMPT_FILE)

    def test_the_probe_wording_can_still_be_named(self):
        self.assertEqual(jev.load_setup(fixtures.ROOT / "prompts", 0.7, prompt_name="enrich-v1.json").label_config, "jev-1.13.0/prompt-v1/schema-v1/cut-0.70")
        code, text = self.cli("run", "--run", "old", "--new", "--input", self.csv, "--standin", "--verify-size", "15", "--prompt-file", "enrich-v1.json")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.db().execute("SELECT label_config FROM runs WHERE run='old'").fetchone()[0], "jev-1.13.0/prompt-v1/schema-v1/cut-0.70")


if __name__ == "__main__":
    unittest.main()
