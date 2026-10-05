"""Gemma through LM Studio's OpenAI-compatible server: the verify, group and memo roles.

A problem with the server halts the stage (ServerProblem). A bad answer is a property of
one request (InvalidOutput). The two are never confused, because an export with no
succeeded call of a role is flagged.
"""

import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

MODEL = "google/gemma-4-26b-a4b-qat"
REFUSED_REQUEST = (400, 413, 422)  # statuses that say "not this request", as against "not now" or "not here"
# Chat-template tokens that can leak into a string that is otherwise valid for the schema.
LEAK = re.compile(r"<start_of_turn>|<end_of_turn>|<bos>|<eos>|<pad>|<unused\d+>|<\|[^|<>\n]{1,40}\|>|<[a-z_]{2,20}\|>|<\|[a-z_]{2,20}>")


class ServerProblem(Exception):
    """The server did not answer, answered with an error, or is serving another model."""


class InvalidOutput(Exception):
    """This one answer cannot be used: not a JSON object, cut off, or carrying a template token."""


@dataclass(frozen=True)
class Reply:
    data: dict
    model: str
    input_tokens: int | None
    output_tokens: int | None


def _leaks(value):
    if isinstance(value, str):
        return LEAK.search(value)
    if isinstance(value, dict):
        return next((m for v in value.values() if (m := _leaks(v))), None)
    if isinstance(value, list):
        return next((m for v in value if (m := _leaks(v))), None)
    return None


class Client:
    def __init__(self, base_url="http://localhost:1234/v1", model=MODEL, timeout=120):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout

    def _send(self, path, payload=None, *, one_request=False):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            with e:
                detail = e.read().decode("utf-8", "replace")[:300]
            if one_request and e.code in REFUSED_REQUEST:
                # The server is up and refused this request, most likely for its size. Retrying it forever would
                # stall the stage, so it is one invalid answer and the stage goes on.
                raise InvalidOutput(f"the model server refused this request with HTTP {e.code}: {detail}") from None
            raise ServerProblem(f"HTTP {e.code} from the model server: {detail}") from None
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
            raise ServerProblem(f"the model server at {self.base_url} did not answer: {type(e).__name__}: {e}") from None

    def check(self):
        """Raise ServerProblem unless the server answers and has the expected model loaded."""
        listed = self._send("/models")
        names = [m.get("id") for m in listed.get("data", [])] if isinstance(listed, dict) else []
        if self.model not in names:
            raise ServerProblem(f"the model server is not serving {self.model}; it lists {names}")

    def ask(self, system, user, schema, *, max_tokens):
        body = self._send(
            "/chat/completions",
            {
                "model": self.model,
                "temperature": 0,
                "reasoning_effort": "none",  # otherwise reasoning tokens eat max_tokens
                "max_tokens": max_tokens,
                "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            one_request=True,
        )
        if not isinstance(body, dict) or body.get("model") != self.model:
            named = body.get("model") if isinstance(body, dict) else body
            raise ServerProblem(f"the response names model {named!r}, not {self.model}")
        try:
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise InvalidOutput("the response has no message") from None
        if choice.get("finish_reason") == "length":
            raise InvalidOutput(f"the answer was cut off at max_tokens={max_tokens}")
        try:
            data = json.loads(content)
        except (TypeError, ValueError):
            raise InvalidOutput("the answer is not JSON") from None
        if not isinstance(data, dict):
            raise InvalidOutput("the answer is not a JSON object")
        leak = _leaks(data)
        if leak:
            raise InvalidOutput(f"the answer carries a template token: {leak.group(0)}")
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        tokens = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
        if not all(type(t) is int and t >= 0 for t in tokens):
            tokens = (None, None)
        return Reply(data, body["model"], *tokens)
