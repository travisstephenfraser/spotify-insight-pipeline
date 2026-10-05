import csv
import gzip
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline import export, jev, standins, state
from tests import fixtures


def read_jsonl(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class ExportCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def run_all(self, name="a", **options):
        db, csv_path = fixtures.full_run(self.dir / name, **options)
        self.addCleanup(db.close)
        return db, csv_path

    def export(self, db, csv_path, name="a", **options):
        out = self.dir / name / "grading"
        return export.export(db, "r1", out, checker_path=fixtures.CHECKER, input_path=csv_path, **options), out


class GoodExport(ExportCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.db, cls.csv = fixtures.full_run(cls.root / "a")
        cls.out = cls.root / "a" / "grading"
        cls.evidence = cls.root / "a" / "evidence"
        cls.result = export.export(cls.db, "r1", cls.out, checker_path=fixtures.CHECKER, input_path=cls.csv, evidence_dir=cls.evidence)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls._tmp.cleanup()

    def test_the_supplied_checker_passes_with_no_flags(self):
        self.assertEqual(self.result["status"], "pass")
        self.assertEqual(self.result["issue_counts"], {})

    def test_every_labelable_review_is_classified_and_every_row_accounted_for(self):
        coverage = self.result["coverage"]
        self.assertEqual(coverage["labelable_completion_fraction"], 1.0)
        self.assertEqual(coverage["accounted_fraction"], 1.0)
        self.assertEqual(self.result["coverage_point"], 1.0)
        self.assertEqual((coverage["valid_completed"], coverage["quarantined"], coverage["expected"]), (28, 2, 30))

    def test_the_checkers_files_stay_outside_the_grading_folder(self):
        names = {p.name for p in self.out.iterdir()}
        self.assertEqual(
            names,
            {"run.json", "ingestion.json", "records.jsonl", "membership.csv", "ranking.csv", "claims.csv", "calls.jsonl",
             "checkpoint_before.json", "checkpoint_after.json"},
        )  # fmt: skip
        self.assertTrue((self.out.parent / "self-check.json").exists())
        self.assertTrue((self.out.parent / "local-reference.json").exists())

    def test_run_json_has_the_five_fields(self):
        run = json.loads((self.out / "run.json").read_text())
        self.assertEqual(
            run,
            {"version": "a5-audit-v1", "analysis_count": 30, "analysis_sha256": fixtures.checker().sha(self.csv),
             "classification_input_fields": ["review_text"], "allow_multi_issue": False},
        )  # fmt: skip

    def test_there_is_one_record_per_source_row_and_a_copy_points_at_its_original(self):
        records = {r["review_id"]: r for r in read_jsonl(self.out / "records.jsonl")}
        self.assertEqual(len(records), 30)
        copies = [r for r in records.values() if r.get("cache_source_id")]
        self.assertEqual(len(copies), 5)
        for copy in copies:
            original = records[copy["cache_source_id"]]
            self.assertNotIn("cache_source_id", original)
            for key in ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review", "label_config"):
                self.assertEqual(copy[key], original[key])
        empty = [r for r in records.values() if r["status"] == "quarantined"]
        self.assertEqual([set(r) for r in empty], [{"review_id", "source_sha256", "status", "reason"}] * 2)
        self.assertEqual({r["reason"] for r in empty}, {"empty_review_text"})

    def test_the_boundary_is_the_first_session_that_left_an_original_unlabeled(self):
        sessions = self.db.execute("SELECT session_id, ended_how FROM sessions WHERE stage='classify' ORDER BY session_id").fetchall()
        self.assertEqual([s["ended_how"] for s in sessions], ["stop_after", "finished"])
        self.assertEqual(self.result["boundary_session"], sessions[0]["session_id"])
        before = json.loads((self.out / "checkpoint_before.json").read_text())["completed_ids"]
        after = json.loads((self.out / "checkpoint_after.json").read_text())["completed_ids"]
        self.assertTrue(set(before) < set(after))
        self.assertEqual(len(after), 28)
        done_first = {r["review_id"] for r in self.db.execute("SELECT review_id FROM reviews WHERE completed_session=?", (sessions[0]["session_id"],))}
        self.assertEqual(set(before), done_first)

    def test_enrich_calls_are_initial_up_to_the_boundary_and_resume_after(self):
        calls = read_jsonl(self.out / "calls.jsonl")
        before = set(json.loads((self.out / "checkpoint_before.json").read_text())["completed_ids"])
        enrich = [c for c in calls if c["role"] == "enrich"]
        self.assertEqual({c["phase"] for c in enrich}, {"initial", "resume"})
        for call in enrich:
            self.assertEqual(call["phase"] == "resume", not (set(call["review_ids"]) & before) and call["phase"] == "resume")
            if call["phase"] == "resume":
                self.assertFalse(set(call["review_ids"]) & before)
        self.assertEqual({c["role"] for c in calls if c["outcome"] == "succeeded"}, {"enrich", "verify", "group", "memo"})
        self.assertTrue(all("phase" not in c for c in calls if c["role"] != "enrich"))
        self.assertEqual(len({c["request_id"] for c in calls}), len(calls))

    def test_claims_csv_holds_the_claims_the_memo_cites(self):
        with open(self.out / "claims.csv", newline="", encoding="utf-8") as f:
            claims = list(csv.DictReader(f))
        self.assertTrue(claims)
        self.assertEqual(set(claims[0]), {"claim_id", "issue_id", "metric", "value"})
        self.assertEqual(self.result["memo_problems"], [])

    def test_the_run_evidence_is_written_from_the_state_file(self):
        names = {p.name for p in self.evidence.iterdir()}
        self.assertEqual(
            names,
            {"run_manifest.json", "run_log.jsonl", "run_summary.json", "quarantine.jsonl", "verify_predictions.jsonl", "verify_report.json", "artifacts.jsonl", "memo.md"},
        )
        summary = json.loads((self.evidence / "run_summary.json").read_text())
        self.assertEqual(summary["statuses"], {"completed": 28, "quarantined": 2})
        self.assertEqual(summary["resume"]["boundary_session"], self.result["boundary_session"])
        self.assertEqual(summary["spend"]["cap_usd"], "25")
        self.assertEqual({s["stage"] for s in summary["sessions"]}, {"classify", "verify", "group", "memo"})
        self.assertEqual(len(read_jsonl(self.evidence / "verify_predictions.jsonl")), 10)
        self.assertEqual(len(read_jsonl(self.evidence / "quarantine.jsonl")), 2)
        manifest = json.loads((self.evidence / "run_manifest.json").read_text())
        self.assertEqual(manifest["input_sha256"], fixtures.checker().sha(self.csv))
        self.assertEqual(set(manifest["outputs"]), {p.name for p in self.out.iterdir()})


class Problems(ExportCase):
    def test_export_refuses_while_a_review_is_pending(self):
        db = fixtures.prepared_db(self.dir)
        self.addCleanup(db.close)
        with self.assertRaises(export.NotReady):
            export.export(db, "r1", self.dir / "grading", checker_path=fixtures.CHECKER, input_path=self.dir / "r1.csv")
        self.assertFalse((self.dir / "grading").exists())

    def test_a_run_that_was_never_stopped_is_reported_as_having_no_boundary(self):
        db, csv_path = self.run_all(stop_after=None)
        result, out = self.export(db, csv_path)
        self.assertIsNone(result["boundary_session"])
        self.assertIn("no boundary", result["notes"][0])
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(set(result["issue_counts"]), {"resume_snapshot_mismatch", "resume_call_evidence"})
        self.assertEqual(json.loads((out / "checkpoint_before.json").read_text()), {"completed_ids": []})

    def test_a_failed_call_is_exported_with_zeros_and_usage_known_false(self):
        rows = fixtures.synthetic_rows(30, empties=2, copies=5)
        flaky = rows[3]["review_text"]
        db, csv_path = self.run_all(rows=rows, labeler=standins.ReplayJev(fixtures.PROBE / "simple.jsonl", script={flaky: ["temporary"]}))
        result, out = self.export(db, csv_path)
        self.assertEqual(result["status"], "pass")
        failed = [c for c in read_jsonl(out / "calls.jsonl") if c["outcome"] == "failed"]
        self.assertEqual([(c["input_tokens"], c["output_tokens"], c["usage_known"]) for c in failed], [(0, 0, False)])
        self.assertEqual(result["calls_with_unknown_usage"], 1)

    def test_a_quarantined_nonempty_review_exports_and_reports_review_required(self):
        rows = fixtures.synthetic_rows(30, empties=2, copies=5)
        shared = rows[0]["review_text"]  # the first texts are the ones that have copies
        db, csv_path = self.run_all(rows=rows, labeler=standins.ReplayJev(fixtures.PROBE / "simple.jsonl", script={shared: ["invalid", "invalid"]}))
        result, out = self.export(db, csv_path)
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(set(result["issue_counts"]), {"unfinished_classification"})
        self.assertLess(result["coverage"]["labelable_completion_fraction"], 1.0)
        self.assertEqual(result["coverage"]["accounted_fraction"], 1.0)
        bad = [r for r in read_jsonl(out / "records.jsonl") if r.get("reason") == "invalid_model_output"]
        self.assertEqual(len(bad), 2)
        self.assertTrue(all("cache_source_id" not in r for r in bad))

    def test_large_jsonl_files_are_gzipped_and_the_plain_form_is_removed(self):
        db, csv_path = self.run_all()
        self.export(db, csv_path)
        result, out = self.export(db, csv_path, gzip_over=1)
        names = {p.name for p in out.iterdir()}
        self.assertIn("records.jsonl.gz", names)
        self.assertIn("calls.jsonl.gz", names)
        self.assertNotIn("records.jsonl", names)
        self.assertNotIn("calls.jsonl", names)
        self.assertEqual(result["status"], "pass")
        result, out = self.export(db, csv_path)
        self.assertEqual({p.name for p in out.iterdir() if p.name.startswith("records")}, {"records.jsonl"})

    def test_a_file_over_the_size_limit_is_named_as_needing_a_release_asset(self):
        db, csv_path = self.run_all()
        result, _ = self.export(db, csv_path, size_limit=2000)
        self.assertIn("records.jsonl", result["release_assets"])
        self.assertNotIn("run.json", result["release_assets"])

    def test_a_run_with_no_memo_exports_and_the_checker_says_what_is_missing(self):
        db, csv_path = self.run_all(memo=False)
        result, _ = self.export(db, csv_path)
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(set(result["issue_counts"]), {"missing_claims", "missing_model_roles"})

    def test_a_memo_that_no_longer_matches_the_numbers_is_reported(self):
        db, csv_path = self.run_all()
        row = db.execute("SELECT * FROM artifacts WHERE key='final-memo:r1'").fetchone()
        text = json.loads(row["output_json"])["memo"] + "\nAbout 99999 people are affected."
        db.execute("UPDATE artifacts SET output_json=? WHERE key='final-memo:r1'", (json.dumps({"memo": text}),))
        result, _ = self.export(db, csv_path)
        self.assertTrue(any("99999" in p for p in result["memo_problems"]))


class Mutations(unittest.TestCase):
    """Break one thing in a good export and see the checker name it: proof these tests would notice a regression."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.db, cls.csv = fixtures.full_run(cls.root / "a")
        cls.good = cls.root / "a" / "grading"
        export.export(cls.db, "r1", cls.good, checker_path=fixtures.CHECKER, input_path=cls.csv)
        cls.ref = fixtures.checker().reference(cls.csv, cls.csv)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls._tmp.cleanup()

    def audit(self, change):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "grading"
            shutil.copytree(self.good, folder)
            change(folder)
            return fixtures.checker().audit(folder, self.ref)["issue_counts"]

    @staticmethod
    def rewrite_jsonl(path, edit):
        rows = read_jsonl(path)
        edit(rows)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def test_the_untouched_copy_passes(self):
        self.assertEqual(self.audit(lambda folder: None), {})

    def test_a_copy_with_a_different_label_is_an_invalid_cache_reuse(self):
        def change(folder):
            self.rewrite_jsonl(folder / "records.jsonl", lambda rows: next(r for r in rows if r.get("cache_source_id")).update(severity=5))

        self.assertIn("invalid_cache_reuse", self.audit(change))

    def test_a_quarantined_id_in_a_checkpoint_breaks_the_snapshot(self):
        def change(folder):
            quarantined = next(r["review_id"] for r in read_jsonl(folder / "records.jsonl") if r["status"] == "quarantined")
            path = folder / "checkpoint_after.json"
            ids = json.loads(path.read_text())["completed_ids"]
            path.write_text(json.dumps({"completed_ids": [*ids, quarantined]}))

        self.assertIn("resume_snapshot_mismatch", self.audit(change))

    def test_a_resume_call_naming_a_checkpointed_id_is_reprocessing(self):
        def change(folder):
            before = json.loads((folder / "checkpoint_before.json").read_text())["completed_ids"]
            self.rewrite_jsonl(folder / "calls.jsonl", lambda rows: next(r for r in rows if r.get("phase") == "resume").update(review_ids=[before[0]]))

        self.assertIn("reprocessed_checkpoint", self.audit(change))

    def test_a_decimal_token_count_is_invalid_usage(self):
        def change(folder):
            self.rewrite_jsonl(folder / "calls.jsonl", lambda rows: rows[0].update(input_tokens=926.5))

        self.assertIn("invalid_usage", self.audit(change))

    def test_a_mean_with_five_decimals_is_a_ranking_mismatch(self):
        def change(folder):
            path = folder / "ranking.csv"
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            rows[0]["mean_severity"] = rows[0]["mean_severity"][:-1]
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)

        self.assertIn("ranking_mismatch", self.audit(change))

    def test_both_forms_of_a_jsonl_file_together_are_ambiguous(self):
        def change(folder):
            with gzip.open(folder / "records.jsonl.gz", "wt", encoding="utf-8") as f:
                f.write((folder / "records.jsonl").read_text(encoding="utf-8"))

        self.assertIn("ambiguous_file", self.audit(change))

    def test_a_call_under_another_label_config_is_a_config_mismatch(self):
        def change(folder):
            self.rewrite_jsonl(folder / "calls.jsonl", lambda rows: next(r for r in rows if r["role"] == "enrich" and r["outcome"] == "succeeded").update(label_config="other"))

        self.assertIn("call_config_mismatch", self.audit(change))

    def test_a_complaint_left_out_of_membership_is_ungrouped(self):
        def change(folder):
            lines = (folder / "membership.csv").read_text().splitlines()
            (folder / "membership.csv").write_text("\n".join(lines[:-1]) + "\n")

        self.assertIn("ungrouped_complaints", self.audit(change))


if __name__ == "__main__":
    unittest.main()
