import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline import jev
from tests import fixtures

KEY = "fake-key-for-tests-0123456789"
GOOD = {
    "model": "jev-1.13.0",
    "answers": {"topic": {"choice": "playback", "probabilities": {"playback": 1.0}}},
    "usage": {"input_tokens": 926, "output_tokens": 215},
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        server = self.server
        length = int(self.headers.get("Content-Length", 0))
        server.seen.append({"auth": self.headers.get("Authorization"), "body": self.rfile.read(length), "path": self.path})
        if server.delay:
            time.sleep(server.delay)
        body = server.body
        if server.echo_auth:
            body = json.dumps({"error": f"bad credentials: {self.headers.get('Authorization')}"})
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        try:
            self.send_response(server.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client gave up waiting, which is what the timeout test wants

    def log_message(self, *args):
        pass


class ClientCase(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.status, self.server.body, self.server.delay, self.server.echo_auth, self.server.seen = 200, json.dumps(GOOD), 0, False, []
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/systemone"
        self.client = jev.Client(KEY, url=self.url, timeout=5)
        self.request = jev.build_request("Bad app \U0001f621. It crashes.", jev.load_setup(fixtures.ROOT / "prompts", 0.7).prompt)

    def ask(self, client=None):
        return (client or self.client).label(self.request["state"], self.request)


class Good(ClientCase):
    def test_a_good_response_becomes_a_reply_with_usage(self):
        reply = self.ask()
        self.assertEqual(reply.answer, GOOD["answers"])
        self.assertEqual((reply.model, reply.input_tokens, reply.output_tokens, reply.http_status), ("jev-1.13.0", 926, 215, 200))

    def test_the_request_goes_out_as_utf8_json_with_a_bearer_key(self):
        self.ask()
        (seen,) = self.server.seen
        self.assertEqual(seen["auth"], f"Bearer {KEY}")
        self.assertEqual(json.loads(seen["body"].decode("utf-8")), self.request)
        self.assertEqual(seen["body"], jev.body_bytes(self.request))
        self.assertEqual(seen["path"], "/v1/systemone")

    def test_an_envelope_around_the_answer_is_unwrapped(self):
        self.server.body = json.dumps({"result": GOOD})
        self.assertEqual(self.ask().answer, GOOD["answers"])

    def test_a_response_with_no_usage_has_unknown_token_counts(self):
        self.server.body = json.dumps({k: v for k, v in GOOD.items() if k != "usage"})
        reply = self.ask()
        self.assertEqual((reply.input_tokens, reply.output_tokens), (None, None))

    def test_token_counts_that_are_not_whole_numbers_are_unknown_not_guessed(self):
        self.server.body = json.dumps({**GOOD, "usage": {"input_tokens": "926", "output_tokens": 2.5}})
        reply = self.ask()
        self.assertEqual((reply.input_tokens, reply.output_tokens), (None, None))


class Errors(ClientCase):
    def test_each_status_maps_to_the_right_error(self):
        cases = {429: jev.Temporary, 500: jev.Temporary, 502: jev.Temporary, 503: jev.Temporary, 529: jev.Temporary,
                 401: jev.Fatal, 402: jev.Fatal, 403: jev.Fatal, 400: jev.Rejected, 404: jev.Rejected}  # fmt: skip
        for status, error in cases.items():
            self.server.status, self.server.body = status, json.dumps({"error": "nope"})
            with self.subTest(status=status), self.assertRaises(error) as caught:
                self.ask()
            self.assertEqual(caught.exception.status, status)

    def test_a_slow_response_times_out_as_temporary(self):
        self.server.delay = 1.0
        with self.assertRaises(jev.Temporary) as caught:
            self.ask(jev.Client(KEY, url=self.url, timeout=0.2))
        self.assertIsNone(caught.exception.status)

    def test_a_refused_connection_is_temporary(self):
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaises(jev.Temporary):
            self.ask()

    def test_a_body_that_is_not_json_is_temporary(self):
        self.server.body = "<html>gateway hiccup</html>"
        with self.assertRaises(jev.Temporary):
            self.ask()

    def test_a_json_body_that_is_not_an_object_is_temporary(self):
        self.server.body = json.dumps(["not", "an", "object"])
        with self.assertRaises(jev.Temporary):
            self.ask()


class Secrets(ClientCase):
    def test_an_error_that_echoes_the_authorization_header_is_stored_without_the_key(self):
        self.server.status, self.server.echo_auth = 401, True
        with self.assertRaises(jev.Fatal) as caught:
            self.ask()
        text = str(caught.exception)
        self.assertNotIn(KEY, text)
        self.assertIn("bad credentials", text)

    def test_the_client_never_shows_its_key(self):
        self.assertNotIn(KEY, repr(self.client))
        self.assertNotIn(KEY, str(vars(self.client).keys()))

    def test_scrub_removes_the_key_and_any_bearer_token(self):
        self.assertEqual(jev.scrub(f"sent Bearer {KEY} and {KEY}", KEY), "sent Bearer [removed] and [removed]")
        self.assertEqual(jev.scrub("Authorization: Bearer abc.def-123", KEY), "Authorization: Bearer [removed]")

    def test_a_client_without_a_key_refuses_to_be_built(self):
        with self.assertRaises(ValueError):
            jev.Client("")


if __name__ == "__main__":
    unittest.main()
