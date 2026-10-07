"""THROWAWAY Jev accuracy probe on the 100 pilot reviews. Not pipeline code.

Two question styles against TypeSafe's direct API, pinned model:
  simple   - one request per review, one broad question per label (the brief's suggestion)
  sentence - one request per sentence, narrow literal questions, contract rules applied in code

Default is a dry run that sends nothing. Paid calls need --go.
Prints operational numbers only. Label answers are saved to files and held
until the human labels exist, so nothing here spoils blind labeling.
"""

import csv
import hashlib
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "feed/Final Assignment - Spotify Reviews Dataset/cost_100.csv"
OUT = Path(__file__).parent
URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
PRICE_PER_M = (
    0.042  # USD per million input tokens, docs.typesafe.ai/models, checked 2026-10-04
)

TOPICS = {
    "access": "Login, signup, password or account access",
    "usability": "Navigation, controls, layout, queue or playlist management, ad interruptions",
    "playback": "Playback failure, crashes, lag, connection failures, audio quality, resource use",
    "downloads": "Downloading, saved music, offline listening, disappearing downloads",
    "catalog": "Missing songs or artists, search and discovery, recommendations, lyrics availability",
    "billing": "Price, charges, subscriptions, paywalls, premium entitlement, controls that are explicitly premium-only",
    "support": "Contacting support and the support response",
    "other": "General praise or criticism, unrelated content, or no specific topic",
}
INTENTS = {
    "cancellation": "The writer says they are leaving, uninstalling or cancelling, or threatens to",
    "complaint": "A negative experience, including mixed praise and criticism",
    "request": "A desired change with no failure reported",
    "praise": "Positive, with no problem reported",
    "unclear": "Meaningless or unrelated text, or a bare boycott slogan",
}
SEVERITY = {  # named keys, never digits
    "no_problem": (
        1,
        "No problem reported: praise, unclear text, or a pure feature request",
    ),
    "annoyance": (
        2,
        "Dislike, generic criticism, a minor annoyance or a cosmetic issue; nothing stops working",
    ),
    "degraded": (
        3,
        "A function is degraded or restricted, but some use or a workaround remains",
    ),
    "blocked": (
        4,
        "A core task is clearly blocked, such as being unable to log in or play music",
    ),
    "serious_harm": (5, "Explicit serious financial, privacy or data harm"),
}
TONE = ["Very negative", "Negative", "Neutral or mixed", "Positive", "Very positive"]
KINDS = {
    "problem": "Reports a problem, failure or criticism",
    "leaving": "Says the writer is leaving, uninstalling or cancelling, or threatens to",
    "request": "Asks for a change or feature without reporting a failure",
    "praise": "Praises the app or a feature",
    "none": "None of these: unrelated, meaningless, or a bare slogan",
}


def api_key():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(
            r"\s*(?:export\s+)?(TYPESAFE_API_KEY|TYPESAFE_API)\s*=\s*(.+)$", line
        )
        if m:
            return m.group(2).strip().strip("'\"")
    raise SystemExit("No TypeSafe key found in .env")


def shuffled(d, text, salt):
    """Repeatable option order derived from the review text."""
    return dict(
        sorted(
            d.items(),
            key=lambda kv: hashlib.sha256(
                f"{salt}:{text}:{kv[0]}".encode()
            ).hexdigest(),
        )
    )


SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+|(?<=[।。！？؟۔])\s*")


def pieces(text):
    """Sentence pieces, each an exact substring of the text. Content-free pieces are dropped."""
    parts = [p.strip() for p in SPLIT.split(text)]
    parts = [p for p in parts if p]
    assert all(p in text for p in parts), "piece is not an exact substring"
    content = [p for p in parts if any(c.isalnum() for c in p)]
    return content or [text.strip()]


def simple_request(text):
    ps = pieces(text)
    q = {
        "topic": {
            "type": "choice",
            "instructions": "Which topic is the review mainly about? Choose the topic of the most serious specific problem; on a tie choose the first one mentioned. For a positive review choose the first specific feature praised.",
            "criteria": shuffled(TOPICS, text, "topic"),
        },
        "intent": {
            "type": "choice",
            "instructions": "What is the writer's intent? If several apply, prefer cancellation, then complaint, then request, then praise, then unclear.",
            "criteria": shuffled(INTENTS, text, "intent"),
        },
        "severity": {
            "type": "choice",
            "instructions": "How severe is the worst problem the review reports?",
            "criteria": shuffled(
                {k: v[1] for k, v in SEVERITY.items()}, text, "severity"
            ),
        },
        "tone": {
            "type": "score",
            "instructions": "How positive or negative is the review overall?",
            "criteria": TONE,
        },
    }
    state = text
    if len(ps) > 1:
        tags = {
            f"part_{chr(97 + i // 26)}{chr(97 + i % 26)}": p for i, p in enumerate(ps)
        }
        q["evidence"] = {
            "type": "choice",
            "instructions": "Which part of the review states the most serious problem? If there is no problem, which part gives the most specific praise?",
            "criteria": shuffled(tags, text, "evidence"),
        }
    return {"state": state, "model": MODEL, "questions": q}, ps


def sentence_request(text, piece, first):
    q = {
        "about": {
            "type": "choice",
            "instructions": "Which product area is `sentence` about?",
            "criteria": shuffled(TOPICS, piece, "about"),
        },
        "kind": {
            "type": "choice",
            "instructions": "What does `sentence` do?",
            "criteria": shuffled(KINDS, piece, "kind"),
        },
        "impact": {
            "type": "choice",
            "instructions": "How much does the problem stated in `sentence` limit use of the app?",
            "criteria": shuffled(
                {k: v[1] for k, v in SEVERITY.items()}, piece, "impact"
            ),
        },
    }
    if first:
        q["tone"] = {
            "type": "score",
            "instructions": "How positive or negative is `review` overall?",
            "criteria": TONE,
        }
    return {
        "state": {"review": text, "sentence": piece},
        "model": MODEL,
        "questions": q,
    }


def post(payload, key, tries=4):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    attempts = []
    for n in range(tries):
        req = urllib.request.Request(
            URL,
            data=data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
            attempts.append({"status": 200, "secs": time.perf_counter() - t0})
            return body, attempts
        except urllib.error.HTTPError as e:
            attempts.append(
                {
                    "status": e.code,
                    "secs": time.perf_counter() - t0,
                    "error": e.read().decode("utf-8", "replace")[:300],
                }
            )
            if e.code not in (429, 500, 502, 503, 529):
                return None, attempts
        except Exception as e:  # network trouble: outcome unknown, recorded as such
            attempts.append(
                {
                    "status": None,
                    "secs": time.perf_counter() - t0,
                    "error": f"{type(e).__name__}: {e}"[:300],
                }
            )
        time.sleep(min(8, 0.5 * 2**n))
    return None, attempts


def unwrap(body):
    for _ in range(2):  # tolerate an envelope if one exists
        if (
            isinstance(body, dict)
            and "answers" not in body
            and isinstance(body.get("result"), dict)
        ):
            body = body["result"]
    return body


def main():
    go = "--go" in sys.argv
    probe = "--probe" in sys.argv
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig", newline="")))
    assert len(rows) == 100
    plan = {"simple": [], "sentence": []}
    for r in rows:
        payload, ps = simple_request(r["review_text"])
        plan["simple"].append((r["review_id"], None, payload))
        for i, p in enumerate(ps):
            plan["sentence"].append(
                (r["review_id"], i, sentence_request(r["review_text"], p, i == 0))
            )
    chars = {
        k: sum(len(json.dumps(p, ensure_ascii=False)) for _, _, p in v)
        for k, v in plan.items()
    }
    print(
        f"reviews=100  simple requests={len(plan['simple'])}  sentence requests={len(plan['sentence'])}  "
        f"payload chars: simple={chars['simple']} sentence={chars['sentence']}  "
        f"rough tokens at 4 chars each={sum(chars.values()) // 4}  rough cost=${sum(chars.values()) / 4 / 1e6 * PRICE_PER_M:.4f}"
    )
    if not (go or probe):
        print(
            "Dry run. Nothing sent. Use --probe for one request or --go for the full test."
        )
        return
    key = api_key()
    if probe:
        body, attempts = post(plan["simple"][0][2], key)
        body = unwrap(body) if body else None
        print("probe attempts:", [(a["status"], round(a["secs"], 2)) for a in attempts])
        if body:
            print(
                "top-level keys:",
                sorted(body.keys()),
                "| model:",
                body.get("model"),
                "| usage:",
                body.get("usage"),
            )
            print(
                "answer keys per question:",
                {k: sorted(v.keys()) for k, v in body.get("answers", {}).items()},
            )
        else:
            print("probe failed:", attempts[-1].get("error"))
        return
    for style, items in plan.items():
        path = OUT / f"{style}.jsonl"
        t0 = time.perf_counter()
        ok = fail = retries = tokens_in = tokens_out = 0
        lat, models = [], set()
        with open(path, "w", encoding="utf-8") as f:
            for rid, idx, payload in items:
                body, attempts = post(payload, key)
                body = unwrap(body) if body else None
                retries += len(attempts) - 1
                if body and "answers" in body:
                    ok += 1
                    lat.append(attempts[-1]["secs"])
                    usage = body.get("usage") or {}
                    tokens_in += usage.get("input_tokens") or 0
                    tokens_out += usage.get("output_tokens") or 0
                    models.add(body.get("model"))
                else:
                    fail += 1
                f.write(
                    json.dumps(
                        {
                            "review_id": rid,
                            "piece_index": idx,
                            "request": payload,
                            "response": body,
                            "attempts": attempts,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        wall = time.perf_counter() - t0
        lat.sort()
        print(
            f"{style:<9} requests={len(items)} ok={ok} failed={fail} retries={retries} wall={wall:.1f}s "
            f"req/s={len(items) / wall:.1f} latency median={statistics.median(lat):.2f}s p95={lat[int(len(lat) * 0.95) - 1]:.2f}s "
            f"input_tokens={tokens_in} (mean {tokens_in / max(ok, 1):.0f}/request) output_tokens={tokens_out} "
            f"cost=${tokens_in / 1e6 * PRICE_PER_M:.5f} model={sorted(m for m in models if m)}",
            flush=True,
        )


if __name__ == "__main__":
    main()
