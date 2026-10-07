"""A Claude model through Anthropic's Messages API: the memo role.

The memo is one small call a run, so a paid model costs cents. It raises the same two errors
as the local client: a problem reaching the service halts the stage (ServerProblem), and an
answer that cannot be used belongs to one request (InvalidOutput). The key never reaches a
saved error.
"""

import http.client
import json
import urllib.error
import urllib.request

from pipeline import gemma

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"
# These models think before they answer, and thinking is billed and counted as output. The memo's own
# limit is small, so room for thinking is added to it; the reservation holds the whole ceiling.
THINKING_ROOM = 3000


class Client:
    paid = True  # its calls are reserved and settled in the spend ledger

    def __init__(self, api_key, model, *, url=URL, timeout=180, effort="low"):
        self._key, self.model, self.url, self.timeout, self.effort = api_key, model, url, timeout, effort
        self.label = f"{model}/effort-{effort}"  # what a memo's setup string names

    def output_ceiling(self, max_tokens):
        """The most output tokens one call can be billed for."""
        return max_tokens + THINKING_ROOM

    def _scrub(self, text):
        return text.replace(self._key, "[removed]") if self._key else text

    def check(self):
        if not self._key:
            raise gemma.ServerProblem("ANTHROPIC_API_KEY is not set, so the memo model cannot be called")

    def ask(self, system, user, schema, *, max_tokens):
        """One memo. `schema` is not sent: the answer's text is the memo, returned as {"memo": text}."""
        self.check()
        body = {
            "model": self.model,
            "max_tokens": self.output_ceiling(max_tokens),
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": self.effort},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"x-api-key": self._key, "anthropic-version": VERSION, "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                answer = json.loads(response.read())
        except urllib.error.HTTPError as e:
            with e:
                detail = self._scrub(e.read().decode("utf-8", "replace"))[:300]
            raise gemma.ServerProblem(f"HTTP {e.code} from the memo model's API: {detail}") from None
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
            raise gemma.ServerProblem(self._scrub(f"the memo model's API did not answer: {type(e).__name__}: {e}")[:300]) from None
        if not isinstance(answer, dict) or not str(answer.get("model", "")).startswith(self.model):
            named = answer.get("model") if isinstance(answer, dict) else answer
            raise gemma.ServerProblem(f"the response names model {named!r}, not {self.model}")
        usage = answer.get("usage") or {}
        stop = answer.get("stop_reason")
        if stop == "refusal":
            raise gemma.InvalidOutput("the model declined to write the memo")
        if stop == "max_tokens":
            raise gemma.InvalidOutput(f"the answer was cut off at max_tokens={body['max_tokens']}")
        blocks = answer.get("content") if isinstance(answer.get("content"), list) else []
        text = next((b.get("text") for b in blocks if isinstance(b, dict) and b.get("type") == "text"), None)
        if not isinstance(text, str) or not text.strip():
            raise gemma.InvalidOutput("the response holds no text")
        tokens = [usage.get(k) for k in ("input_tokens", "output_tokens")]
        tin, tout = (t if isinstance(t, int) and not isinstance(t, bool) and t >= 0 else None for t in tokens)
        return gemma.Reply({"memo": text.strip()}, answer["model"], tin, tout)
