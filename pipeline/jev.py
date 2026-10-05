"""Jev (TypeSafe): building a request for one review and turning its answer into a record.

Jev returns choices and probabilities, never text. Code supplies the quote (the sentence
Jev picked), the entities (feature words found in the text) and the review flag.
"""

import hashlib
import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pipeline import features as feature_words
from pipeline import labels, splitter

MODEL = "jev-1.13.0"
MAX_OPTIONS = 255  # Jev's documented limit on the options of one question
MAX_TOKENS = 32_000  # Jev's documented limit on one request
BYTES_PER_TOKEN = 2.4  # a request body measured 2.46 to 2.93 bytes per input token; 2.4 errs toward too many


class _ClientError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status  # the HTTP status, or None when no response came back


class Temporary(_ClientError):
    """429, 5xx, a timeout or network trouble. Worth another try."""


class Fatal(_ClientError):
    """401, 402, 403, any other refusal of the request as sent, or a wrong model. The run halts."""


class TooLarge(Exception):
    """The request would pass Jev's documented limits. The review is quarantined, never cut short."""


@dataclass(frozen=True)
class Reply:
    answer: dict
    model: str
    input_tokens: int | None
    output_tokens: int | None
    http_status: int
    request_id: str | None = None


@dataclass(frozen=True)
class Setup:
    """Everything besides the text that shapes a label."""

    prompt: dict
    features: tuple
    cutoff: float
    label_config: str
    prompt_file: Path
    features_file: Path

    def hashes(self):
        """Content hashes saved with a run. A resume is refused if any of them differs."""
        return {
            f"prompt:{self.prompt_file.name}": _sha(self.prompt_file.read_bytes()),
            "features": _sha(self.features_file.read_bytes()),
            "splitter": _sha(Path(splitter.__file__).read_bytes()),
            "cutoff": f"{self.cutoff:.2f}",
        }


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def load_setup(prompts_dir, cutoff, *, prompt_name="enrich-v1.json", features_name="features-v1.txt"):
    prompts_dir = Path(prompts_dir)
    prompt = json.loads((prompts_dir / prompt_name).read_text(encoding="utf-8"))
    return Setup(
        prompt=prompt,
        features=feature_words.load(prompts_dir / features_name),
        cutoff=float(cutoff),
        label_config=f"{prompt['model']}/{prompt['version']}/{prompt['schema']}/cut-{float(cutoff):.2f}",
        prompt_file=prompts_dir / prompt_name,
        features_file=prompts_dir / features_name,
    )


def _shuffled(options, text, salt):
    """A repeatable option order derived from the review text, so no option is always first."""
    return dict(sorted(options.items(), key=lambda kv: hashlib.sha256(f"{salt}:{text}:{kv[0]}".encode()).hexdigest()))


def _tags(parts):
    return {f"part_{chr(97 + i // 26)}{chr(97 + i % 26)}": p for i, p in enumerate(parts)}


def body_bytes(request):
    """The request as it is sent."""
    return json.dumps(request, ensure_ascii=False).encode("utf-8")


def build_request(text, prompt):
    """One request for one review: topic, intent, severity, tone, and which sentence when there are several."""
    parts = splitter.pieces(text)
    questions = {
        name: {"type": "choice", "instructions": prompt[name]["instructions"], "criteria": _shuffled(prompt[name]["criteria"], text, name)}
        for name in ("topic", "intent", "severity")
    }
    questions["tone"] = {"type": "score", "instructions": prompt["tone"]["instructions"], "criteria": prompt["tone"]["criteria"]}
    if len(parts) > 1:
        if len(parts) > MAX_OPTIONS:
            raise TooLarge(f"{len(parts)} sentence pieces, over the limit of {MAX_OPTIONS} options")
        questions["evidence"] = {
            "type": "choice",
            "instructions": prompt["evidence"]["instructions"],
            "criteria": _shuffled(_tags(parts), text, "evidence"),
        }
    request = {"state": text, "model": prompt["model"], "questions": questions}
    estimated = len(body_bytes(request)) / BYTES_PER_TOKEN
    if estimated > MAX_TOKENS:
        raise TooLarge(f"about {estimated:.0f} tokens, over the limit of {MAX_TOKENS}")
    return request


def entities(text, features):
    return feature_words.find(text, features)


def to_record(text, answer, *, features, cutoff, label_config):
    """Jev's answer for `text` as a validated record, plus `min_top_probability`. Raises labels.InvalidAnswer."""
    try:
        tops = [max(answer[q]["probabilities"].values()) for q in ("topic", "intent", "severity")]
        severity_name = answer["severity"]["choice"]
        if severity_name not in labels.SEVERITY:
            raise labels.InvalidAnswer(f"severity choice is not one of the named options: {severity_name!r}")
        parts = splitter.pieces(text)
        if len(parts) > 1:
            choice = answer["evidence"]["choice"]
            tags = _tags(parts)
            if choice not in tags:
                raise labels.InvalidAnswer(f"evidence choice names no part of the review: {choice!r}")
            quote = tags[choice]
        else:
            quote = text.strip()
        record = {
            "topic": answer["topic"]["choice"],
            "intent": answer["intent"]["choice"],
            "severity": labels.SEVERITY[severity_name],
            "sentiment": labels.sentiment_from_tone(answer["tone"]["score"]),
            "entities": entities(text, features),
            "evidence_quote": quote,
            "needs_review": min(tops) < cutoff,
            "label_config": label_config,
        }
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise labels.InvalidAnswer(f"the answer is missing a part or has the wrong shape: {type(e).__name__}: {e}") from None
    labels.validate(text, record)
    return {**record, "min_top_probability": min(tops)}


URL = "https://api.typesafe.ai/v1/systemone"
BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+")


def scrub(text, api_key):
    """Error text as it may be saved: the key and any bearer token taken out."""
    if api_key:
        text = text.replace(api_key, "[removed]")
    return BEARER.sub("Bearer [removed]", text)


class Client:
    """The real labeler: one HTTPS request per review to TypeSafe. Nothing here retries."""

    def __init__(self, api_key, *, url=URL, timeout=30):
        if not api_key:
            raise ValueError("no TypeSafe key: set TYPESAFE_API_KEY")
        self._key, self.url, self.timeout = api_key, url, timeout

    def __repr__(self):
        return f"jev.Client(url={self.url!r}, timeout={self.timeout})"

    def label(self, text, request):
        http_request = urllib.request.Request(
            self.url,
            data=body_bytes(request),
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as e:
            with e:  # the error carries the response body; close it once read
                detail = scrub(e.read().decode("utf-8", "replace")[:300], self._key)
            kind = Temporary if e.code == 429 or e.code >= 500 else Fatal
            raise kind(f"HTTP {e.code}: {detail}", e.code) from None
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:  # timeouts and network trouble
            raise Temporary(scrub(f"{type(e).__name__}: {e}", self._key)) from None
        try:
            body = json.loads(raw)
            for _ in range(2):  # tolerate an envelope around the answer
                if isinstance(body, dict) and "answers" not in body and isinstance(body.get("result"), dict):
                    body = body["result"]
            if not isinstance(body, dict):
                raise ValueError("the response is not a JSON object")
        except ValueError as e:
            raise Temporary(f"unreadable response: {e}", status) from None
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        tokens = (usage.get("input_tokens"), usage.get("output_tokens"))
        if not all(type(t) is int and t >= 0 for t in tokens):
            tokens = (None, None)  # usage unknown is saved as unknown, never guessed
        return Reply(body.get("answers"), body.get("model"), tokens[0], tokens[1], status, body.get("id"))
