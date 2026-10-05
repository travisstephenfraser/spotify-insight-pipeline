import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline import gemma, standins

SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string", "enum": ["playback", "other"]}, "note": {"type": "string"}},
    "required": ["topic", "note"],
    "additionalProperties": False,
}


def completion(content, *, model=gemma.MODEL, finish="stop", usage=True):
    body = {"model": model, "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": content}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 310, "completion_tokens": 24}
    return body


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.server.seen.append(("GET", self.path, None))
        self.reply(200, {"data": [{"id": name} for name in self.server.models]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        self.server.seen.append(("POST", self.path, body))
        if self.server.delay:
            time.sleep(self.server.delay)
        self.reply(self.server.status, self.server.body)

    def log_message(self, *args):
        pass


class GemmaCase(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        s = self.server
        s.models, s.status, s.delay, s.seen = [gemma.MODEL, "other/model"], 200, 0, []
        s.body = completion(json.dumps({"topic": "playback", "note": "music stops"}))
        thread = threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(s.server_close)
        self.addCleanup(s.shutdown)
        self.client = gemma.Client(base_url=f"http://127.0.0.1:{s.server_address[1]}/v1", timeout=5)

    def ask(self, client=None):
        return (client or self.client).ask("You label reviews.", "The music stops.", SCHEMA, max_tokens=200)


class Ask(GemmaCase):
    def test_the_request_carries_the_three_settings_and_the_bound(self):
        self.ask()
        method, path, body = self.server.seen[-1]
        self.assertEqual((method, path), ("POST", "/v1/chat/completions"))
        self.assertEqual((body["temperature"], body["reasoning_effort"], body["max_tokens"], body["model"]), (0, "none", 200, gemma.MODEL))
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["schema"], SCHEMA)
        self.assertIs(body["response_format"]["json_schema"]["strict"], True)
        self.assertEqual(body["messages"], [{"role": "system", "content": "You label reviews."}, {"role": "user", "content": "The music stops."}])

    def test_a_good_answer_becomes_a_reply_with_usage(self):
        reply = self.ask()
        self.assertEqual(reply.data, {"topic": "playback", "note": "music stops"})
        self.assertEqual((reply.model, reply.input_tokens, reply.output_tokens), (gemma.MODEL, 310, 24))

    def test_no_usage_means_unknown_token_counts(self):
        self.server.body = completion(json.dumps({"topic": "other", "note": "x"}), usage=False)
        reply = self.ask()
        self.assertEqual((reply.input_tokens, reply.output_tokens), (None, None))

    def test_a_response_naming_another_model_is_a_server_problem(self):
        self.server.body = completion(json.dumps({"topic": "other", "note": "x"}), model="google/gemma-4-e4b")
        with self.assertRaises(gemma.ServerProblem) as caught:
            self.ask()
        self.assertIn("gemma-4-e4b", str(caught.exception))

    def test_a_leaked_template_token_is_invalid_output(self):
        for leaked in ("music stops<end_of_turn>", "<start_of_turn>model", "ok <|im_end|>", "<unused12> ok", "<bos>ok"):
            self.server.body = completion(json.dumps({"topic": "other", "note": leaked}))
            with self.subTest(leaked=leaked), self.assertRaises(gemma.InvalidOutput):
                self.ask()

    def test_an_ordinary_angle_bracket_is_not_a_leak(self):
        self.server.body = completion(json.dumps({"topic": "other", "note": "volume < 3 and > 1, <3 this app"}))
        self.assertEqual(self.ask().data["note"], "volume < 3 and > 1, <3 this app")

    def test_a_reply_cut_off_at_max_tokens_is_invalid_output(self):
        self.server.body = completion('{"topic": "playback", "note": "music st', finish="length")
        with self.assertRaises(gemma.InvalidOutput) as caught:
            self.ask()
        self.assertIn("max_tokens", str(caught.exception))

    def test_content_that_is_not_a_json_object_is_invalid_output(self):
        for content in ("not json", "[1, 2]", ""):
            self.server.body = completion(content)
            with self.subTest(content=content), self.assertRaises(gemma.InvalidOutput):
                self.ask()

    def test_an_error_status_is_a_server_problem(self):
        for status in (400, 500, 503):
            self.server.status = status
            with self.subTest(status=status), self.assertRaises(gemma.ServerProblem):
                self.ask()

    def test_a_slow_server_is_a_server_problem(self):
        self.server.delay = 1.0
        with self.assertRaises(gemma.ServerProblem):
            self.ask(gemma.Client(base_url=self.client.base_url, timeout=0.2))

    def test_a_refused_connection_is_a_server_problem(self):
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaises(gemma.ServerProblem):
            self.ask()
        with self.assertRaises(gemma.ServerProblem):
            self.client.check()


class Check(GemmaCase):
    def test_check_passes_when_the_expected_model_is_listed(self):
        self.client.check()
        self.assertEqual(self.server.seen[-1][:2], ("GET", "/v1/models"))

    def test_check_fails_when_the_expected_model_is_not_loaded(self):
        self.server.models = ["google/gemma-4-e4b"]
        with self.assertRaises(gemma.ServerProblem) as caught:
            self.client.check()
        self.assertIn(gemma.MODEL, str(caught.exception))


class Standin(unittest.TestCase):
    def test_the_stand_in_answers_within_the_schemas_choices_and_logs_the_call(self):
        fake = standins.StandinGemma()
        fake.check()
        reply = fake.ask("definitions", "The app crashes every time", SCHEMA, max_tokens=200)
        self.assertIn(reply.data["topic"], SCHEMA["properties"]["topic"]["enum"])
        self.assertIsInstance(reply.data["note"], str)
        self.assertEqual(reply.model, gemma.MODEL)
        self.assertEqual(fake.calls, [("definitions", "The app crashes every time", SCHEMA, 200)])

    def test_the_stand_in_labels_by_the_same_keyword_rule_as_the_stand_in_jev(self):
        schema = {"type": "object", "properties": {
            "topic": {"type": "string", "enum": ["access", "usability", "playback", "downloads", "catalog", "billing", "support", "other"]},
            "intent": {"type": "string", "enum": ["cancellation", "complaint", "request", "praise", "unclear"]},
            "severity": {"type": "integer", "enum": [1, 2, 3, 4, 5]}}}  # fmt: skip
        data = standins.StandinGemma().ask("defs", "Cannot log in since update 4", schema, max_tokens=200).data
        self.assertEqual(data, {"topic": "access", "intent": "complaint", "severity": 4})

    def test_a_scripted_stand_in_can_be_down_or_return_invalid_output(self):
        fake = standins.StandinGemma(script=["server_problem", "invalid"])
        with self.assertRaises(gemma.ServerProblem):
            fake.ask("s", "u", SCHEMA, max_tokens=10)
        with self.assertRaises(gemma.InvalidOutput):
            fake.ask("s", "u", SCHEMA, max_tokens=10)
        self.assertEqual(fake.ask("s", "u", SCHEMA, max_tokens=10).model, gemma.MODEL)

    def test_a_stand_in_with_the_wrong_model_loaded_fails_its_check(self):
        with self.assertRaises(gemma.ServerProblem):
            standins.StandinGemma(loaded=False).check()


if __name__ == "__main__":
    unittest.main()
