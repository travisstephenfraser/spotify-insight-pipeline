import contextlib
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from cost import calc
from pipeline import classify, cli, jev, ledger, limits, standins, state
from tests import fixtures

COST = fixtures.ROOT / "cost"


def run_cli(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main([str(a) for a in args])
    return code, out.getvalue()


def make_pilot(folder):
    """A stand-in cold run (stopped once, resumed) and warm run on the real pilot file, written as pilot evidence."""
    from cost import evidence

    state_path = folder / "state.sqlite"
    pilot = fixtures.DATA / "cost_100.csv"
    common = ["--state", state_path, "--standin"]
    assert run_cli("run", "--run", "cold", "--new", "--input", pilot, "--stop-after", "50", *common)[0] == 3
    assert run_cli("run", "--run", "cold", *common)[0] == 0
    assert run_cli("run", "--run", "warm", "--new", "--input", pilot, "--warm-from", "cold", *common)[0] == 0
    out = folder / "cost"
    out.mkdir()
    for name in ("rates.csv", "local_compute.csv", "assumptions.csv", "text_volume.json"):
        shutil.copy2(COST / name, out / name)
    db = state.connect(state_path, synchronous="OFF")
    try:
        evidence.write(db, "cold", "warm", out)
    finally:
        db.close()
    return out


class PilotCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = make_pilot(Path(cls._tmp.name))
        cls.inputs = calc.load(cls.dir)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def measured(self, **changes):
        return calc.measured(**{**self.inputs, **changes})


class Evidence(PilotCase):
    def rows(self, name):
        with open(self.dir / name, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_the_evidence_files_are_written(self):
        names = {p.name for p in self.dir.iterdir()}
        self.assertTrue({"pilot_records.jsonl", "pilot_calls.jsonl", "usage.csv"} <= names)

    def test_there_is_one_record_per_pilot_id_with_its_row_hash(self):
        records = [json.loads(line) for line in (self.dir / "pilot_records.jsonl").read_text().splitlines()]
        pilot = fixtures.supplied("cost_100.csv")
        self.assertEqual([r["review_id"] for r in records], [r["review_id"] for r in pilot])
        self.assertEqual([r["source_sha256"] for r in records], [fixtures.checker().row_sha(r) for r in pilot])
        self.assertEqual({r["status"] for r in records}, {"completed"})

    def test_calls_carry_run_ids_and_the_warm_pass_says_it_made_none(self):
        calls = [json.loads(line) for line in (self.dir / "pilot_calls.jsonl").read_text().splitlines()]
        cold = [c for c in calls if c["run_id"] == "cold"]
        warm = [c for c in calls if c["run_id"] == "warm"]
        self.assertEqual({c["role"] for c in cold}, {"enrich", "verify", "group", "memo"})
        self.assertEqual(len({c["request_id"] for c in cold}), len(cold))
        self.assertEqual(warm, [{"run_id": "warm", "pass": "warm", "calls_made": 0, "record": "no call of any role was made; every result came from run cold"}])
        self.assertTrue(all(c["request_bytes"] > 0 for c in cold if c["role"] == "enrich"))

    def test_usage_has_a_row_for_each_run_and_stage_and_an_end_to_end_row(self):
        usage = self.rows("usage.csv")
        keys = {(u["run_id"], u["stage"]) for u in usage}
        stages = ("classify", "verify", "group", "memo", "end_to_end")
        self.assertEqual(keys, {(run, s) for run in ("cold", "warm") for s in stages})

    def test_the_warm_run_has_zero_requests_and_a_time_above_zero(self):
        usage = {(u["run_id"], u["stage"]): u for u in self.rows("usage.csv")}
        warm = usage[("warm", "end_to_end")]
        self.assertEqual(int(warm["requests"]), 0)
        self.assertGreater(Decimal(warm["seconds"]), 0)
        self.assertEqual(int(usage[("warm", "classify")]["attempts"]), 0)
        self.assertEqual(int(usage[("cold", "classify")]["requests"]), 100)

    def test_end_to_end_seconds_are_the_sum_of_the_stage_seconds(self):
        usage = self.rows("usage.csv")
        for run in ("cold", "warm"):
            parts = sum(Decimal(u["seconds"]) for u in usage if u["run_id"] == run and u["stage"] != "end_to_end")
            total = next(Decimal(u["seconds"]) for u in usage if u["run_id"] == run and u["stage"] == "end_to_end")
            self.assertEqual(total, parts)

    def test_a_warm_pass_that_made_a_call_is_refused_as_evidence(self):
        from cost import evidence

        with tempfile.TemporaryDirectory() as tmp:
            db, _ = fixtures.full_run(Path(tmp) / "a")
            try:
                with self.assertRaises(evidence.BadPilot):
                    evidence.write(db, "r1", "r1", Path(tmp))
            finally:
                db.close()


class StageClock(unittest.TestCase):
    def test_a_stages_seconds_are_its_session_clock_not_the_sum_of_its_request_times(self):
        from cost import evidence

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = fixtures.prepared_db(tmp, fixtures.synthetic_rows(16, empties=0, copies=0))
            try:
                classify.run(
                    db, "r1", standins.ReplayJev(latency=0.2),
                    ledger=ledger.Ledger(db, fixtures.write_billing(tmp / "billing.json"), cap_usd=Decimal("25")),
                    limiter=limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9),
                    setup=jev.load_setup(fixtures.ROOT / "prompts", 0.7), workers=16,
                )  # fmt: skip
                row = next(u for u in evidence.usage_rows(db, "r1", "cold") if u["stage"] == "classify")
                summed = db.execute("SELECT SUM(seconds) FROM calls").fetchone()[0]
            finally:
                db.close()
        self.assertGreater(summed, 3.0)  # 16 requests of 0.2 s each
        self.assertLess(Decimal(row["seconds"]), 1.0)  # all at once: about 0.2 s on the clock
        self.assertEqual(int(row["workers"]), 16)


class InstructorTests(PilotCase):
    def doubled(self):
        return [{**r, "usd_per_unit": str(Decimal(r["usd_per_unit"]) * 2) if r["usd_per_unit"] else ""} for r in self.inputs["rates"]]

    def test_doubling_every_api_rate_doubles_the_api_subtotal_exactly(self):
        base, double = self.measured(), self.measured(rates=self.doubled())
        for which in ("cold", "warm"):
            self.assertEqual(double[which]["api_usd"], base[which]["api_usd"] * 2)
        self.assertGreater(base["cold"]["api_usd"], 0)
        self.assertEqual(base["warm"]["api_usd"], 0)

    def test_doubling_rates_leaves_local_compute_and_measured_time_unchanged(self):
        base, double = self.measured(), self.measured(rates=self.doubled())
        for which in ("cold", "warm"):
            self.assertEqual(double[which]["local_usd_estimate"], base[which]["local_usd_estimate"])
            self.assertEqual(double[which]["seconds"], base[which]["seconds"])
            self.assertEqual(
                {s: v["seconds"] for s, v in double[which]["stages"].items()}, {s: v["seconds"] for s, v in base[which]["stages"].items()}
            )

    def test_doubling_rates_doubles_the_projected_api_cost_too(self):
        base = calc.project(self.measured(), **self.projection())
        double = calc.project(self.measured(rates=self.doubled()), **self.projection(rates=self.doubled()))
        self.assertEqual(double["base"]["api_usd"], base["base"]["api_usd"] * 2)

    def projection(self, **changes):
        return {**calc.projection_inputs(self.inputs), **changes}

    def test_changing_the_projected_row_count_leaves_the_measured_results_unchanged(self):
        measured = self.measured()
        frozen = json.dumps(measured, default=str, sort_keys=True)
        small = calc.project(measured, **self.projection(rows=1000, nonempty=1000, distinct=900))
        big = calc.project(measured, **self.projection())
        self.assertEqual(json.dumps(measured, default=str, sort_keys=True), frozen)
        self.assertEqual(json.dumps(self.measured(), default=str, sort_keys=True), frozen)
        self.assertLess(small["base"]["api_usd"], big["base"]["api_usd"])

    def test_costs_are_exact_decimals_never_rounded_before_the_tests(self):
        cost = self.measured()["cold"]["api_usd"]
        self.assertIsInstance(cost, Decimal)
        tokens = sum(int(c["input_tokens"]) for c in self.inputs["calls"] if c.get("role") == "enrich" and c["run_id"] == "cold")
        self.assertEqual(cost, tokens * Decimal("0.000000042"))
        self.assertLess(cost, Decimal("0.01"))  # under one cent: rounding to cents would make it zero


class KnownAnswer(PilotCase):
    def test_the_replayed_pilot_costs_what_the_probe_measured(self):
        """Known answer from outside this code: $0.0039 per 100 reviews, measured on 2026-10-04 (CLAUDE.md).
        The stand-in replays those same 100 answers with their real token counts."""
        self.assertEqual(self.measured()["cold"]["api_usd"].quantize(Decimal("0.0001")), Decimal("0.0039"))

    def test_the_base_projection_is_about_what_the_spec_estimated(self):
        """The spec estimates one full pass at about $19. A descent must not read as a climb."""
        base = calc.project(self.measured(), **calc.projection_inputs(self.inputs))["base"]["api_usd"]
        self.assertTrue(Decimal(17) < base < Decimal(21), base)


class Totals(PilotCase):
    def blank_output_rate(self):
        """The rates with the output-token price left blank, as it was until the usage page settled it."""
        return [{**r, "usd_per_unit": ""} if r["item"] == "jev_output_tokens" else r for r in self.inputs["rates"]]

    def test_api_spend_local_compute_and_unknown_costs_are_three_separate_totals(self):
        cold = self.measured(rates=self.blank_output_rate())["cold"]
        self.assertEqual(set(cold) >= {"api_usd", "local_usd_estimate", "unknown"}, True)
        self.assertGreater(cold["local_usd_estimate"], 0)
        self.assertTrue(any("output" in item["what"] for item in cold["unknown"]))

    def test_an_unknown_rate_stays_unknown_and_is_never_counted_as_zero_dollars(self):
        cold = self.measured(rates=self.blank_output_rate())["cold"]
        unknown = next(item for item in cold["unknown"] if "output" in item["what"])
        self.assertGreater(unknown["units"], 0)
        self.assertNotIn("usd", unknown)
        priced = [{**r, "usd_per_unit": "0.000000042"} if r["item"] == "jev_output_tokens" else r for r in self.inputs["rates"]]
        with_rate = self.measured(rates=priced)["cold"]
        self.assertEqual([i for i in with_rate["unknown"] if "output" in i["what"]], [])
        self.assertEqual(with_rate["api_usd"] - cold["api_usd"], unknown["units"] * Decimal("0.000000042"))

    def test_local_compute_is_seconds_times_the_editable_assumptions(self):
        cold = self.measured()["cold"]
        local = {r["item"]: Decimal(r["value"]) for r in self.inputs["local"]}
        seconds = sum(v["seconds"] for s, v in cold["stages"].items() if s != "classify")
        expected = seconds * local["power_draw_watts"] / 3_600_000 * local["electricity_usd_per_kwh"]
        places = Decimal("1e-20")  # a division is involved, so the last digits depend on the order of operations
        self.assertEqual(cold["local_usd_estimate"].quantize(places), expected.quantize(places))
        self.assertGreater(expected, 0)

    def test_a_pilot_with_zero_tokens_raises(self):
        empty = [{**c, "input_tokens": 0, "output_tokens": 0} if "input_tokens" in c else c for c in self.inputs["calls"]]
        with self.assertRaises(calc.Degenerate):
            self.measured(calls=empty)

    def test_per_stage_counts_match_the_call_log(self):
        cold = self.measured()["cold"]["stages"]
        self.assertEqual((cold["classify"]["requests"], cold["classify"]["attempts"], cold["classify"]["failed"]), (100, 100, 0))
        self.assertEqual(cold["verify"]["requests"], 100)
        self.assertEqual(cold["memo"]["requests"], 1)


class Projection(PilotCase):
    def project(self, **changes):
        return calc.project(self.measured(), **{**calc.projection_inputs(self.inputs), **changes})

    def test_each_stage_is_projected_from_its_own_work_count(self):
        p = self.project()
        self.assertEqual(p["base"]["stages"]["classify"]["requests"], 484_189)
        self.assertEqual(p["no_reuse"]["stages"]["classify"]["requests"], 660_609)
        self.assertEqual(p["base"]["stages"]["verify"]["requests"], 5_000)
        self.assertEqual(p["base"]["stages"]["memo"]["requests"], 1)
        self.assertLessEqual(p["base"]["stages"]["group"]["requests"], 8)

    def test_the_memo_is_added_once_not_scaled_with_the_rows(self):
        small, big = self.project(rows=1000, nonempty=1000, distinct=900), self.project()
        self.assertEqual(small["base"]["stages"]["memo"]["seconds"], big["base"]["stages"]["memo"]["seconds"])

    def test_the_conservative_case_costs_more_than_the_base_case(self):
        p = self.project()
        self.assertGreater(p["conservative"]["api_usd"], p["base"]["api_usd"])

    def test_a_case_that_passes_the_cap_carries_a_warning(self):
        self.assertTrue(any("cap" in w for w in self.project(cap=Decimal("1"))["warnings"]))
        self.assertEqual([w for w in self.project(cap=Decimal("1000"))["warnings"] if "passes the cap" in w], [])

    def test_longer_full_file_texts_raise_the_projected_tokens_per_request(self):
        p = self.project()
        pilot_tokens = self.measured()["cold"]["stages"]["classify"]["input_tokens"] / Decimal(100)
        volume = self.inputs["text_volume"]
        longer = volume["full_distinct_text_bytes"] / volume["full_distinct_texts"] > volume["pilot_text_bytes"] / volume["pilot_rows"]
        self.assertEqual(p["base"]["stages"]["classify"]["input_tokens_per_request"] > pilot_tokens, longer)


class Replay(PilotCase):
    def replay(self, cwd, *args):
        code = (
            "import runpy, sys\n"
            f"sys.argv = ['cost', 'replay', '--dir', {str(self.dir)!r}, *{list(args)!r}]\n"
            "try:\n    runpy.run_module('cost', run_name='__main__')\nexcept SystemExit as e:\n    assert not e.code, e.code\n"
            "bad = sorted(m for m in sys.modules if m == 'sqlite3' or m.startswith('pipeline') or m.startswith('urllib.request'))\n"
            "print('LOADED', bad)\n"
        )
        done = subprocess.run([sys.executable, "-c", code], cwd=cwd, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return done.stdout

    def test_replay_opens_no_state_file_and_imports_no_client(self):
        out = self.replay(fixtures.ROOT)
        self.assertIn("LOADED []", out)

    def test_replay_writes_a_report_with_the_measured_table_and_the_projection(self):
        self.replay(fixtures.ROOT)
        report = (self.dir / "report.md").read_text()
        for needed in ("Measured on the 100-review pilot", "Cold", "Warm", "cost per 1,000 rows", "unknown", "estimate", "660,622", "484,189", "docs.typesafe.ai"):
            self.assertIn(needed, report)

    def test_replay_twice_gives_the_same_bytes_and_so_does_a_clean_copy_of_the_repo(self):
        self.replay(fixtures.ROOT)
        first = (self.dir / "report.md").read_bytes()
        self.replay(fixtures.ROOT)
        self.assertEqual((self.dir / "report.md").read_bytes(), first)
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "clone"
            (clone / "cost").mkdir(parents=True)
            for name in ("__init__.py", "__main__.py", "calc.py"):
                shutil.copy2(COST / name, clone / "cost" / name)
            self.replay(clone)  # no pipeline package, no state file, no .env in this copy
            self.assertEqual((self.dir / "report.md").read_bytes(), first)

    def test_changing_the_row_count_on_the_command_line_changes_only_the_projection(self):
        self.replay(fixtures.ROOT)
        full = (self.dir / "report.md").read_text()
        self.replay(fixtures.ROOT, "--rows", "1000", "--nonempty", "1000", "--distinct", "900")
        small = (self.dir / "report.md").read_text()
        cut = "## Estimated before the full run"
        self.assertEqual(full.split(cut)[0], small.split(cut)[0])
        self.assertNotEqual(full.split(cut)[1], small.split(cut)[1])


class Pilot(unittest.TestCase):
    def test_the_paid_pilot_refuses_without_go_and_starts_nothing(self):
        done = subprocess.run([sys.executable, "-m", "cost", "pilot"], cwd=fixtures.ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("--go", done.stdout)
        self.assertFalse((COST / "pilot_calls.jsonl").exists())

    def test_replay_with_no_pilot_evidence_says_so_instead_of_inventing_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("rates.csv", "local_compute.csv", "assumptions.csv", "text_volume.json"):
                shutil.copy2(COST / name, Path(tmp) / name)
            done = subprocess.run([sys.executable, "-m", "cost", "replay", "--dir", tmp], cwd=fixtures.ROOT, capture_output=True, text=True)
            self.assertEqual(done.returncode, 1)
            self.assertIn("no pilot", done.stdout)
            self.assertFalse((Path(tmp) / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
