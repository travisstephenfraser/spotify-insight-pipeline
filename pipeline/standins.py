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

    def __init__(self, path=None, *, script=None, latency=0.0, sleep=time.sleep):
        self._saved = {}
        if path is not None:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._saved[row["request"]["state"]] = row["response"]
        self._script = {text: list(steps) for text, steps in (script or {}).items()}
        self._latency, self._sleep = latency, sleep
        self._lock = threading.Lock()
        self.sent = []  # every text sent, in order: tests assert a completed text is never sent again

    def label(self, text, request):
        with self._lock:
            self.sent.append(text)
            step = self._script[text].pop(0) if self._script.get(text) else None
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
