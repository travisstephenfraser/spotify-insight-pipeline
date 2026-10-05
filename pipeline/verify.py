"""Stage 3: a blind second opinion from Gemma on a sample fixed before any model call.

Gemma gets the review text and the contract's definitions, never Jev's answer. Code
compares. One request at a time; a server problem halts the stage and is never counted
as a failed review.
"""

import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from pipeline import classify, gemma, hashing, labels, state

ROLE = "verify"
PROMPT = Path(__file__).resolve().parents[1] / "prompts/verify-v1.md"
MAX_TOKENS = 200
FIELDS = ("topic", "intent", "severity")
GUARD_MIN = 50
SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "enum": list(labels.TOPICS)},
        "intent": {"type": "string", "enum": list(labels.INTENTS)},
        "severity": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
    },
    "required": list(FIELDS),
    "additionalProperties": False,
}


@dataclass
class Outcome:
    ended_how: str  # finished, time_box, interrupted, server_problem, not_ready, prompt_changed
    predicted: int
    failed: int
    remaining: int
    session_id: int | None = None
    message: str = ""


def load_system(path=PROMPT):
    return Path(path).read_text(encoding="utf-8").strip("\n")


def definitions(system):
    """The contract's label section as it sits inside the prompt."""
    return system.split("<definitions>\n", 1)[1].split("\n</definitions>", 1)[0]


def config(client, prompt_path=PROMPT):
    """What a verify call was made with, the prompt's content included. Saved on every verify call row."""
    return f"{client.model}/verify-v1-{hashing.short_sha(prompt_path)}/schema-v1/max-{MAX_TOKENS}"


def _checked(data):
    if data.get("topic") not in labels.TOPICS or data.get("intent") not in labels.INTENTS:
        raise gemma.InvalidOutput("topic or intent is not one of the allowed labels")
    if type(data.get("severity")) is not int or not 1 <= data["severity"] <= 5:
        raise gemma.InvalidOutput("severity is not a whole number from 1 to 5")
    return data


def _todo(db, run):
    return db.execute(
        "SELECT r.review_id, r.review_text FROM reviews r LEFT JOIN verify v ON v.run=r.run AND v.review_id=r.review_id "
        "WHERE r.run=? AND r.in_verify_sample=1 AND v.review_id IS NULL ORDER BY r.run_order",
        (run,),
    ).fetchall()


def _counts(db, run):
    got = dict(db.execute("SELECT outcome, COUNT(*) FROM verify WHERE run=? GROUP BY outcome", (run,)).fetchall())
    return got.get("predicted", 0), got.get("failed", 0), len(_todo(db, run))


def _save(db, run, review_id, outcome, data=None, reason=None, request_id=None):
    data = data or {}
    db.execute(
        "INSERT OR REPLACE INTO verify (run, review_id, outcome, topic, intent, severity, reason, request_id) VALUES (?,?,?,?,?,?,?,?)",
        (run, review_id, outcome, data.get("topic"), data.get("intent"), data.get("severity"), reason, request_id),
    )


def run(
    db, run, client, *, max_hours=None, max_chars=20_000, clock=time.monotonic, stop_event=None,
    accept_guards=(), prompt_path=PROMPT,
):  # fmt: skip
    """Predict every sampled review that has no prediction yet. Safe to call again to resume."""
    if db.execute("SELECT 1 FROM reviews WHERE run=? AND status='pending' LIMIT 1", (run,)).fetchone():
        return Outcome("not_ready", *_counts(db, run), message="classify has not finished")
    state.close_crashed_sessions(db, run)
    state.recover_orphans(db, run, roles=(ROLE,))
    todo = _todo(db, run)
    if not todo:
        _guard(db, run, accept_guards)
        return Outcome("finished", *_counts(db, run))

    label_config = config(client, prompt_path)
    earlier = {r[0] for r in db.execute("SELECT DISTINCT label_config FROM calls WHERE run=? AND role=? AND outcome='succeeded'", (run, ROLE))}
    if earlier - {label_config}:
        # One sample under two prompts would be two measurements reported as one.
        return Outcome(
            "prompt_changed", *_counts(db, run),
            message="the verify prompt or model changed after verify started on this run; put the earlier one back to finish the sample",
        )  # fmt: skip

    session = state.open_session(db, run, ROLE, 1, clock)
    started = clock()

    def end(how, message=""):
        state.close_session(db, session, how, clock)
        return Outcome(how, *_counts(db, run), session_id=session, message=message)

    try:
        client.check()
    except gemma.ServerProblem as e:
        return end("server_problem", str(e))
    system = load_system(prompt_path)

    for review in todo:
        if stop_event is not None and stop_event.is_set():
            return end("interrupted")
        if max_hours is not None and clock() - started >= max_hours * 3600:
            return end("time_box")
        if len(review["review_text"]) > max_chars:
            _save(db, run, review["review_id"], "failed", reason="too_long")  # never sent cut short
            continue
        last = None
        for _ in range(2):  # an invalid answer is retried once
            last = request_id = uuid.uuid4().hex
            state.begin_attempt(
                db, None, request_id=request_id, run=run, role=ROLE, review_ids=[review["review_id"]],
                model=client.model, label_config=label_config, session_id=session, reserve_tokens=0,
            )  # fmt: skip
            sent = time.monotonic()
            reply = None
            try:
                reply = client.ask(system, review["review_text"], SCHEMA, max_tokens=MAX_TOKENS)
                data = _checked(reply.data)
            except gemma.ServerProblem as e:
                state.finish_attempt(db, request_id, outcome="failed", error=str(e)[:500], seconds=time.monotonic() - sent)
                return end("server_problem", str(e))
            except gemma.InvalidOutput as e:
                state.finish_attempt(
                    db, request_id, outcome="failed", error=str(e)[:500], seconds=time.monotonic() - sent,
                    input_tokens=reply.input_tokens if reply else None, output_tokens=reply.output_tokens if reply else None,
                )  # fmt: skip
                continue
            state.finish_attempt(
                db, request_id, outcome="succeeded", seconds=time.monotonic() - sent,
                input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
            )  # fmt: skip
            _save(db, run, review["review_id"], "predicted", data, request_id=request_id)
            break
        else:
            _save(db, run, review["review_id"], "failed", reason="invalid_output", request_id=last)
        state.heartbeat(db, session, clock)

    outcome = end("finished")
    _guard(db, run, accept_guards)
    return outcome


def _pairs(db, run):
    """Sampled reviews that both engines labeled: (review_id, Jev's labels, Gemma's labels)."""
    rows = db.execute(
        "SELECT r.review_id, s.topic AS jt, s.intent AS ji, s.severity AS js, v.topic AS gt, v.intent AS gi, v.severity AS gs "
        "FROM reviews r JOIN verify v ON v.run=r.run AND v.review_id=r.review_id AND v.outcome='predicted' "
        "JOIN results s ON s.run=r.run AND s.text_key=r.text_key "
        "WHERE r.run=? AND r.in_verify_sample=1 AND r.status='completed' ORDER BY r.run_order",
        (run,),
    ).fetchall()
    return [
        (r["review_id"], dict(zip(FIELDS, (r["jt"], r["ji"], r["js"]))), dict(zip(FIELDS, (r["gt"], r["gi"], r["gs"]))))
        for r in rows
    ]


def _agreement(pairs):
    out = {f: sum(j[f] == g[f] for _, j, g in pairs) for f in FIELDS}
    out["all_three"] = sum(j == g for _, j, g in pairs)
    out["pairs"] = len(pairs)
    return out


def _ranking(labels_of):
    """The contract's baseline ranking, on one engine's labels for the sampled pairs."""
    by_topic = defaultdict(list)
    for label in labels_of:
        if label["intent"] in ("complaint", "cancellation"):
            by_topic[label["topic"]].append(label["severity"])
    rows = [{"topic": t, "complaint_count": len(v), "severity_sum": sum(v)} for t, v in by_topic.items()]
    return sorted(rows, key=lambda r: (-r["severity_sum"], r["topic"]))


def _guard(db, run, accept):
    agreement = _agreement(_pairs(db, run))
    # A leak of Jev's answer into the verifier would most plainly show as perfect agreement.
    failed = ["verifier_agreement_100"] if agreement["pairs"] >= GUARD_MIN and agreement["all_three"] == agreement["pairs"] else []
    classify.settle_guards(db, run, failed, accept)


def report(db, run):
    """Everything the verify report shows. Agreement is on pairs both engines labeled, and says so."""
    sample = db.execute("SELECT COUNT(*) FROM reviews WHERE run=? AND in_verify_sample=1", (run,)).fetchone()[0]
    predicted, failed, _ = _counts(db, run)
    unlabeled = db.execute(
        "SELECT COUNT(*) FROM reviews WHERE run=? AND in_verify_sample=1 AND status!='completed'", (run,)
    ).fetchone()[0]
    pairs = _pairs(db, run)
    complaints = [p for p in pairs if p[1]["intent"] in ("complaint", "cancellation")]
    rest = [p for p in pairs if p[1]["intent"] not in ("complaint", "cancellation")]
    confusion = {f: defaultdict(Counter) for f in FIELDS}
    by_topic = defaultdict(list)
    for pair in pairs:
        _, jev_label, gemma_label = pair
        by_topic[jev_label["topic"]].append(pair)
        for f in FIELDS:
            confusion[f][str(jev_label[f])][str(gemma_label[f])] += 1
    return {
        "sample": sample,
        "predictions": predicted,
        "verify_failures": failed,
        "jev_unlabeled": unlabeled,
        "pairs": len(pairs),
        "pairs_share_of_sample": len(pairs) / sample if sample else None,
        "agreement": _agreement(pairs),
        "by_group": {"complaints_and_cancellations": _agreement(complaints), "rest": _agreement(rest)},
        "by_topic": {topic: _agreement(group) for topic, group in sorted(by_topic.items())},
        "confusion": {f: {j: dict(row) for j, row in sorted(table.items())} for f, table in confusion.items()},
        "ranking": {"jev": _ranking([j for _, j, _ in pairs]), "gemma": _ranking([g for _, _, g in pairs])},
        "disagreements": [{"review_id": rid, "jev": j, "gemma": g} for rid, j, g in pairs if j != g],
    }
