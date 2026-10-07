"""The memo written by a paid Claude model instead of the local one (Travis's ruling, 2026-10-05).

A memo is one small call a run. Its spend goes through the same ledger and the same cap as
Jev's, at the memo model's own rates, and the calculator reports it as API spend.
"""

import json
import tempfile
import threading
import unittest
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pipeline import claude, gemma, ledger, memo, standins, state
from tests import fixtures

KEY = "fake-anthropic-key-for-tests-0123456789"
MILLION = Decimal(1_000_000)


def billing(path, memo_in="2", memo_out="10", model="claude-test-model"):
    path.write_text(json.dumps({
        "jev": {"usd_per_mtok_in": "0.042", "usd_per_mtok_out": "0"},
        "memo": {"model": model, "usd_per_mtok_in": memo_in, "usd_per_mtok_out": memo_out},
    }))
    return path


def answer(text="## Recommendation\nok", model="claude-test-model", stop="end_turn", tin=6000, tout=700):
    return {"model": model, "stop_reason": stop, "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": text}],
            "usage": {"input_tokens": tin, "output_tokens": tout}}  # fmt: skip


class ServerCase(unittest.TestCase):
    def serve(self, status=200, body=None):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": json.loads(raw)})
                data = json.dumps(answer() if body is None else body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/v1/messages", seen

    def client(self, url, **options):
        return claude.Client(KEY, "claude-test-model", url=url, timeout=5, **options)


class Client(ServerCase):
    def test_the_request_is_a_messages_call_with_the_key_in_its_header(self):
        url, seen = self.serve()
        reply = self.client(url).ask("the system text", "the user text", memo.SCHEMA, max_tokens=1500)
        sent = seen[0]
        self.assertEqual(sent["headers"]["x-api-key"], KEY)
        self.assertEqual(sent["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(sent["body"]["model"], "claude-test-model")
        self.assertEqual(sent["body"]["system"], "the system text")
        self.assertEqual(sent["body"]["messages"], [{"role": "user", "content": "the user text"}])
        self.assertEqual(sent["body"]["output_config"], {"effort": "low"})
        self.assertNotIn(KEY, json.dumps(sent["body"]))
        self.assertEqual((reply.data, reply.model, reply.input_tokens, reply.output_tokens), ({"memo": "## Recommendation\nok"}, "claude-test-model", 6000, 700))

    def test_thinking_counts_against_max_tokens_so_room_is_added_and_the_ceiling_is_known(self):
        url, seen = self.serve()
        client = self.client(url)
        client.ask("s", "u", memo.SCHEMA, max_tokens=1500)
        self.assertEqual(seen[0]["body"]["max_tokens"], client.output_ceiling(1500))
        self.assertGreater(client.output_ceiling(1500), 1500)

    def test_a_dated_model_name_in_the_response_is_the_same_model(self):
        url, _ = self.serve(body=answer(model="claude-test-model-20261001"))
        self.assertEqual(self.client(url).ask("s", "u", memo.SCHEMA, max_tokens=10).model, "claude-test-model-20261001")

    def test_another_model_in_the_response_is_a_server_problem(self):
        url, _ = self.serve(body=answer(model="claude-other"))
        with self.assertRaises(gemma.ServerProblem):
            self.client(url).ask("s", "u", memo.SCHEMA, max_tokens=10)

    def test_an_error_status_halts_the_stage_and_never_shows_the_key(self):
        for status in (401, 403, 429, 500, 529):
            url, _ = self.serve(status, {"type": "error", "error": {"type": "x", "message": f"bad key {KEY}"}})
            with self.subTest(status=status), self.assertRaises(gemma.ServerProblem) as caught:
                self.client(url).ask("s", "u", memo.SCHEMA, max_tokens=10)
            self.assertNotIn(KEY, str(caught.exception))
            self.assertIn(str(status), str(caught.exception))

    def test_a_refusal_a_cut_off_answer_or_an_answer_with_no_text_is_one_invalid_answer(self):
        for body in (answer(stop="refusal"), answer(stop="max_tokens"), {**answer(), "content": [{"type": "thinking", "thinking": "x"}]}):
            url, _ = self.serve(body=body)
            with self.subTest(stop=body["stop_reason"]), self.assertRaises(gemma.InvalidOutput):
                self.client(url).ask("s", "u", memo.SCHEMA, max_tokens=10)

    def test_no_server_is_a_server_problem(self):
        with self.assertRaises(gemma.ServerProblem):
            self.client("http://127.0.0.1:9/v1/messages").ask("s", "u", memo.SCHEMA, max_tokens=10)

    def test_a_missing_key_is_caught_before_any_request(self):
        with self.assertRaises(gemma.ServerProblem):
            claude.Client("", "claude-test-model").check()


class Spend(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.db = state.connect(self.dir / "state.sqlite", synchronous="OFF")
        self.addCleanup(self.db.close)
        self.billing = billing(self.dir / "billing.json")
        self.session = state.open_session(self.db, "r", "memo", 1, fixtures.FakeClock())

    def begin(self, led, request_id, tokens, out=0):
        state.begin_attempt(self.db, led, request_id=request_id, run="r", role="memo", review_ids=[], model="m", label_config="c",
                            session_id=self.session, reserve_tokens=tokens, reserve_output_tokens=out)  # fmt: skip

    def test_a_memo_reservation_holds_the_worst_case_of_input_and_output(self):
        led = ledger.Ledger(self.db, self.billing, provider="memo")
        self.begin(led, "q", 20_000, 4_000)
        self.assertEqual(led.reserved_usd(), (20_000 * Decimal(2) + 4_000 * Decimal(10)) / MILLION)
        state.finish_attempt(self.db, "q", outcome="succeeded", input_tokens=6_000, output_tokens=700, seconds=1.0, ledger=led)
        self.assertEqual(led.reserved_usd(), 0)
        self.assertEqual(led.spent_usd(), (6_000 * Decimal(2) + 700 * Decimal(10)) / MILLION)

    def test_a_memo_call_with_no_usage_keeps_its_whole_reservation_as_spent(self):
        led = ledger.Ledger(self.db, self.billing, provider="memo")
        self.begin(led, "q", 20_000, 4_000)
        state.finish_attempt(self.db, "q", outcome="failed", seconds=1.0, ledger=led)
        self.assertEqual(led.spent_usd(), (20_000 * Decimal(2) + 4_000 * Decimal(10)) / MILLION)
        self.assertEqual(ledger.Ledger(self.db, self.billing).spent_usd(), led.spent_usd())  # rebuilt from the file

    def test_jev_and_the_memo_model_spend_against_one_cap(self):
        jev_led = ledger.Ledger(self.db, self.billing, cap_usd=Decimal("0.05"))
        self.begin(jev_led, "j", 1_000_000)  # 4.2 cents reserved for Jev
        memo_led = ledger.Ledger(self.db, self.billing, cap_usd=Decimal("0.05"), provider="memo")
        self.assertEqual(memo_led.reserved_usd(), jev_led.reserved_usd())
        with self.assertRaises(ledger.CapReached):
            self.begin(memo_led, "m", 6_000, 4_000)  # 5.2 cents more would pass 5 cents
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM calls WHERE request_id='m'").fetchone()[0], 0)

    def test_each_row_keeps_the_rates_of_its_own_provider(self):
        ledger.Ledger(self.db, self.billing)  # jev
        led = ledger.Ledger(self.db, self.billing, provider="memo")
        self.begin(led, "q", 100, 10)
        row = self.db.execute("SELECT usd_per_mtok_in, usd_per_mtok_out FROM ledger WHERE request_id='q'").fetchone()
        self.assertEqual((row[0], row[1]), ("2", "10"))


class PaidFake(standins.StandinGemma):
    """A stand-in that answers like the memo stand-in but is a paid client to the pipeline."""

    paid = True

    def __init__(self, **options):
        super().__init__(**options)
        self.model = "claude-test-model"

    def output_ceiling(self, max_tokens):
        return max_tokens + 2000


class MemoStage(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.db = fixtures.grouped_db(self.dir / "a")
        self.addCleanup(self.db.close)
        self.billing = billing(self.dir / "billing.json")

    def test_a_paid_memo_books_its_usage_at_the_memo_models_rates(self):
        led = ledger.Ledger(self.db, self.billing, provider="memo")
        before = led.spent_usd()
        memo.write(self.db, "r1", PaidFake(), ledger=led)
        call = self.db.execute("SELECT * FROM calls WHERE run='r1' AND role='memo' AND outcome='succeeded'").fetchone()
        self.assertEqual(call["model"], "claude-test-model")
        self.assertEqual(led.spent_usd() - before, (call["input_tokens"] * Decimal(2) + call["output_tokens"] * Decimal(10)) / MILLION)
        self.assertEqual(led.reserved_usd(), 0)

    def test_a_memo_that_would_pass_the_cap_is_not_sent(self):
        led = ledger.Ledger(self.db, self.billing, cap_usd=Decimal("0.0001"), provider="memo")
        fake = PaidFake()
        with self.assertRaises(ledger.CapReached):
            memo.write(self.db, "r1", fake, ledger=led)
        self.assertEqual(fake.calls, [])
        self.assertIsNone(memo.final(self.db, "r1"))

    def test_the_local_model_still_writes_a_memo_with_no_ledger(self):
        self.assertTrue(memo.write(self.db, "r1", standins.StandinGemma()).strip())
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM ledger WHERE run='r1' AND request_id IN (SELECT request_id FROM calls WHERE role='memo')").fetchone()[0], 0)

    def test_the_text_of_a_rejected_memo_is_kept_with_its_problems(self):
        """The pilot of 2026-10-05 lost three rejected memos; only their problems were saved."""
        bad = {"memo": "## Recommendation\nSpend on issue-usability because churn will fall.\n\n## Limits\nNone."}
        asked = []

        def respond(system, user, schema):
            asked.append(user)
            return bad if len(asked) == 1 else standins.memo_responder(system, user, schema)

        memo.write(self.db, "r1", standins.StandinGemma(respond=respond))
        rows = self.db.execute("SELECT output_json FROM artifacts WHERE run='r1' AND role='memo-rejected'").fetchall()
        self.assertEqual(len(rows), 1)
        saved = json.loads(rows[0][0])
        self.assertEqual(saved["memo"], bad["memo"])
        self.assertTrue(any("churn" in p or "revenue" in p for p in saved["problems"]))
        self.assertNotEqual(memo.final(self.db, "r1"), bad["memo"])


class CommandLine(unittest.TestCase):
    """A real run writes its memo with the paid model the billing file names; a stand-in run spends nothing."""

    def test_the_repos_billing_file_names_the_memo_model_and_its_rates(self):
        entry = json.loads((fixtures.ROOT / "pipeline/billing.json").read_text(encoding="utf-8"))["memo"]
        self.assertEqual(entry["model"], "claude-sonnet-5-5")
        self.assertEqual((Decimal(entry["usd_per_mtok_in"]), Decimal(entry["usd_per_mtok_out"])), (Decimal(2), Decimal(10)))
        self.assertEqual(entry["checked"], "2026-10-05")

    def test_a_real_run_gets_a_paid_memo_client_for_that_model(self):
        import os
        from unittest import mock

        from pipeline import cli

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": KEY}):
            client = cli.memo_client(fixtures.ROOT / "pipeline/billing.json", real=True, local=standins.StandinGemma())
        self.assertIsInstance(client, claude.Client)
        self.assertEqual(client.model, "claude-sonnet-5-5")

    def test_a_real_run_with_no_key_for_the_memo_model_is_refused_before_anything_is_sent(self):
        import os
        from unittest import mock

        from pipeline import cli

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}), mock.patch.object(cli, "ROOT", Path(tempfile.gettempdir()) / "no-env-here"):
            with self.assertRaises(cli.Refused):
                cli.memo_client(fixtures.ROOT / "pipeline/billing.json", real=True, local=standins.StandinGemma())

    def test_a_stand_in_run_keeps_its_stand_in_and_books_no_memo_spend(self):
        from pipeline import cli
        from tests.test_review_fixes import run_cli

        local = standins.StandinGemma()
        self.assertIs(cli.memo_client(fixtures.ROOT / "pipeline/billing.json", real=False, local=local), local)
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "input.csv"
            fixtures.write_csv(csv_path, fixtures.synthetic_rows(30, empties=1, copies=2))
            code, text = run_cli("run", "--run", "s", "--new", "--input", csv_path, "--standin", "--verify-size", "10", "--state", Path(tmp) / "state.sqlite")
            self.assertEqual(code, 0, text)
            db = state.connect(Path(tmp) / "state.sqlite", synchronous="OFF")
            self.addCleanup(db.close)
            memo_requests = [r[0] for r in db.execute("SELECT request_id FROM calls WHERE role='memo'")]
            self.assertTrue(memo_requests)
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM ledger WHERE request_id IN ({','.join('?' * len(memo_requests))})", memo_requests).fetchone()[0], 0)


class Calculator(unittest.TestCase):
    """A paid memo is API spend in the cost report; a local memo is a local estimate, as before."""

    @classmethod
    def setUpClass(cls):
        from cost import calc
        from tests import test_cost

        cls._tmp = tempfile.TemporaryDirectory()
        cls.calc = calc
        cls.inputs = calc.load(test_cost.make_pilot(Path(cls._tmp.name)))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def as_paid(self):
        """The stand-in pilot's evidence with its memo calls renamed to the paid model: same tokens, another provider."""
        rates = {r["item"]: r for r in self.inputs["rates"]}
        model = rates["memo_input_tokens"]["model"]
        calls = [{**c, "model": model} if c.get("role") == "memo" else c for c in self.inputs["calls"]]
        usage = [{**u, "model": model, "provider": "Anthropic"} if u["stage"] == "memo" else u for u in self.inputs["usage"]]
        return {**self.inputs, "calls": calls, "usage": usage}, rates

    def test_the_rates_file_prices_the_memo_model(self):
        rates = {r["item"]: r for r in self.inputs["rates"]}
        self.assertEqual(rates["memo_input_tokens"]["model"], "claude-sonnet-5-5")
        self.assertEqual((Decimal(rates["memo_input_tokens"]["usd_per_unit"]), Decimal(rates["memo_output_tokens"]["usd_per_unit"])), (Decimal("0.000002"), Decimal("0.00001")))

    def test_a_memo_by_the_local_model_is_a_local_estimate_with_no_api_cost(self):
        memo_stage = self.calc.measured(**self.inputs)["cold"]["stages"]["memo"]
        self.assertEqual(memo_stage["api_usd"], 0)
        self.assertGreater(memo_stage["local_usd_estimate"], 0)

    def test_a_memo_by_the_paid_model_is_api_spend_and_no_local_estimate(self):
        inputs, rates = self.as_paid()
        cold = self.calc.measured(**inputs)["cold"]
        stage = cold["stages"]["memo"]
        expected = stage["input_tokens"] * Decimal(rates["memo_input_tokens"]["usd_per_unit"]) + stage["output_tokens"] * Decimal(rates["memo_output_tokens"]["usd_per_unit"])
        self.assertGreater(expected, 0)
        self.assertEqual(stage["api_usd"], expected)
        self.assertEqual(stage["local_usd_estimate"], 0)
        self.assertEqual(cold["api_usd"], cold["stages"]["classify"]["api_usd"] + expected)

    def test_doubling_the_rates_doubles_the_subtotal_with_a_paid_memo_in_it(self):
        inputs, _ = self.as_paid()
        doubled = [{**r, "usd_per_unit": str(Decimal(r["usd_per_unit"]) * 2)} if r["usd_per_unit"].strip() else r for r in inputs["rates"]]
        once, twice = self.calc.measured(**inputs)["cold"], self.calc.measured(**{**inputs, "rates": doubled})["cold"]
        self.assertEqual(twice["api_usd"], 2 * once["api_usd"])
        self.assertEqual(twice["local_usd_estimate"], once["local_usd_estimate"])

    def test_the_projection_adds_the_paid_memo_once_whatever_the_row_count(self):
        inputs, _ = self.as_paid()
        measured = self.calc.measured(**inputs)
        memo_cost = measured["cold"]["stages"]["memo"]["api_usd"]
        plan = self.calc.projection_inputs(inputs)
        big = self.calc.project(measured, **plan)["base"]
        small = self.calc.project(measured, **{**plan, "rows": 1000, "nonempty": 1000, "distinct": 733})["base"]
        self.assertEqual(big["stages"]["memo"]["api_usd"], memo_cost)
        self.assertEqual(small["stages"]["memo"]["api_usd"], memo_cost)
        self.assertEqual(big["api_usd"], big["stages"]["classify"]["api_usd"] + memo_cost)


if __name__ == "__main__":
    unittest.main()
