"""Stand-ins for the model clients, so every stage runs in tests with no network and no cost.

ReplayJev answers a pilot review with the answer Jev really gave on 2026-10-04 and any
other text with a fixed keyword rule. A script can make named texts misbehave.
"""

import copy
import json
import threading
import time
from pathlib import Path

from pipeline import jev

STEPS = ("temporary", "fatal", "wrong_model", "invalid")

# First match wins, in the contract's precedence order.
INTENT_RULES = (
    ("cancellation", ("cancel", "uninstall", "leaving")),
    ("complaint", ("crash", "cannot", "can't", "too many", "bad", "broken", "stops")),
    ("request", ("please add", "wish", "would be nice")),
    ("praise", ("love", "great", "best")),
)
TOPIC_RULES = (
    ("access", ("log in", "login", "password")),
    ("playback", ("crash", "stops", "lag")),
    ("usability", ("ads", "playlist", "queue", "shuffle")),
    ("billing", ("subscription", "premium", "price")),
    ("catalog", ("lyrics", "search")),
    ("downloads", ("download", "offline")),
    ("support", ("support",)),
)


def _first(rules, low, default):
    return next((label for label, words in rules if any(w in low for w in words)), default)


class ReplayJev:
    """A labeler: `label(text, request) -> jev.Reply`, or raises jev.Temporary or jev.Fatal."""

    def __init__(self, path=None, *, script=None, latency=0.0, sleep=time.sleep, log_path=None):
        self._saved = {}
        if path is not None:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._saved[row["request"]["state"]] = row["response"]
        self._script = {text: list(steps) for text, steps in (script or {}).items()}
        self._latency, self._sleep = latency, sleep
        self._log_path = log_path  # one JSON line per text sent, written before the answer
        self._lock = threading.Lock()
        self.sent = []  # every text sent, in order: tests assert a completed text is never sent again

    def label(self, text, request):
        with self._lock:
            self.sent.append(text)
            step = self._script[text].pop(0) if self._script.get(text) else None
            if self._log_path:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(text) + "\n")
        if step is not None and step not in STEPS:
            raise ValueError(f"unknown script step: {step!r}")
        if self._latency:
            self._sleep(self._latency)
        if step == "temporary":
            raise jev.Temporary("scripted temporary failure")
        if step == "fatal":
            raise jev.Fatal("scripted fatal response")
        response = self._saved.get(text) or self._rule(text, request)
        answers = copy.deepcopy(response["answers"])
        if step == "invalid":
            answers["topic"]["choice"] = "pricing"
        return jev.Reply(
            answer=answers,
            model="jev-9.9.9" if step == "wrong_model" else response.get("model", jev.MODEL),
            input_tokens=response["usage"]["input_tokens"],
            output_tokens=response["usage"]["output_tokens"],
            http_status=200,
        )

    @staticmethod
    def _rule(text, request):
        low = text.lower()
        intent = _first(INTENT_RULES, low, "unclear")
        topic = _first(TOPIC_RULES, low, "other")
        if intent == "complaint":
            severity, tone = ("blocked" if ("cannot" in low or "crash" in low) else "annoyance"), 0.5
        elif intent == "cancellation":
            severity, tone = "annoyance", 0.5
        else:
            severity, tone = "no_problem", 3.5 if intent == "praise" else 2.0
        chosen = {"topic": topic, "intent": intent, "severity": severity}
        questions = request["questions"]
        if "evidence" in questions:
            chosen["evidence"] = min(questions["evidence"]["criteria"])
        answers = {}
        for name, choice in chosen.items():
            options = list(questions[name]["criteria"])
            rest = 0.1 / max(1, len(options) - 1)
            answers[name] = {
                "type": "choice",
                "choice": choice,
                "confidence": 0.9,
                "probabilities": {o: (0.9 if o == choice else rest) for o in options},
            }
        answers["tone"] = {"type": "score", "score": tone, "confidence": 0.9, "probabilities": {}}
        size = len(jev.body_bytes(request))
        return {"model": jev.MODEL, "answers": answers, "usage": {"input_tokens": max(1, size * 10 // 26), "output_tokens": 215}}


class StandinGemma:
    """A stand-in for gemma.Client: `check()` and `ask(system, user, schema, *, max_tokens)`.

    It answers inside the schema it is given. Topic, intent and severity follow the same
    keyword rule as the stand-in Jev, read from the user message alone. `respond` replaces
    the answer for roles that need more (the memo); `script` makes calls fail in order.
    """

    GEMMA_STEPS = ("server_problem", "invalid")
    SEVERITY_NUMBER = {"no_problem": 1, "annoyance": 2, "degraded": 3, "blocked": 4, "serious_harm": 5}

    def __init__(self, *, script=None, respond=None, loaded=True, latency=0.0):
        from pipeline import gemma

        self._gemma = gemma
        self.model = gemma.MODEL
        self._script = list(script or [])
        self._respond = respond
        self._loaded = loaded
        self._latency = latency
        self._lock = threading.Lock()
        self.calls = []  # (system, user, schema, max_tokens) for every call

    def check(self):
        if not self._loaded:
            raise self._gemma.ServerProblem(f"the stand-in server is not serving {self.model}")

    def ask(self, system, user, schema, *, max_tokens):
        with self._lock:
            self.calls.append((system, user, schema, max_tokens))
            step = self._script.pop(0) if self._script else None
        if step is not None and step not in self.GEMMA_STEPS:
            raise ValueError(f"unknown script step: {step!r}")
        if self._latency:
            time.sleep(self._latency)
        if step == "server_problem":
            raise self._gemma.ServerProblem("scripted server problem")
        if step == "invalid":
            raise self._gemma.InvalidOutput("scripted invalid output")
        data = self._respond(system, user, schema) if self._respond else self._by_rule(user, schema)
        return self._gemma.Reply(data, self.model, max(1, (len(system) + len(user)) // 4), 20)

    def _by_rule(self, user, schema):
        low = user.lower()
        intent = _first(INTENT_RULES, low, "unclear")
        if intent == "complaint":
            severity = "blocked" if ("cannot" in low or "crash" in low) else "annoyance"
        else:
            severity = "annoyance" if intent == "cancellation" else "no_problem"
        rule = {"topic": _first(TOPIC_RULES, low, "other"), "intent": intent, "severity": self.SEVERITY_NUMBER[severity]}
        data = {}
        for name, spec in schema.get("properties", {}).items():
            choices = spec.get("enum")
            if choices:
                data[name] = rule[name] if rule.get(name) in choices else choices[0]
            elif spec.get("type") == "integer":
                data[name] = 1
            elif spec.get("type") == "boolean":
                data[name] = False
            else:
                data[name] = f"stand-in {name}"
        return data


def memo_responder(system, user, schema):
    """A memo built by rule from the evidence pack, for `StandinGemma(respond=memo_responder)`.

    It cites only what the pack holds, so it passes the memo check. It is test scaffolding:
    nothing a stand-in writes is ever submitted.
    """
    pack = json.loads(user.split("\n\nYour previous memo", 1)[0])
    names = {i["issue_id"]: i["name"] for i in pack["issues"]}
    claim = {(c["issue_id"], c["metric"]): c for c in pack["claims"]}

    def cite(issue_id, metric):
        c = claim[(issue_id, metric)]
        return f"{c['value']} [{c['claim_id']}]"

    top = pack["ranking"][0]["issue_id"]
    lines = [
        "# Decision memo",
        "",
        "## Recommendation",
        f"Put the next quarter of product effort into {names.get(top, top)} ({top}): it ranks first, with a priority score of {cite(top, 'priority_score')} for {top}.",
        "",
        "## Supporting numbers",
    ]
    for row in pack["ranking"]:
        iid = row["issue_id"]
        lines.append(f"- {iid} has {cite(iid, 'complaint_count')} complaints and a severity sum of {cite(iid, 'severity_sum')} for {iid}.")
    lines += ["", "## Alternatives"]
    for row in pack["ranking"][1:]:
        iid = row["issue_id"]
        lines.append(f"- {iid} ranks {row['rank']}, with a priority score of {cite(iid, 'priority_score')} for {iid}.")
    if len(pack["ranking"]) == 1:
        lines.append("- No other issue has a complaint in this run.")
    lines += ["", "## Representative reviews"]
    for iid, quotes in pack["evidence"].items():
        for q in quotes[:2]:
            text = q["quote"].replace('"', "'").replace("\n", " ")
            lines.append(f'- {iid} [review:{q["review_id"]}] "{text}"')
    lines += ["", "## Limits"] + [f"- {limit}" for limit in pack["run_facts"]["known_limits"]]
    return {"memo": "\n".join(lines)}
