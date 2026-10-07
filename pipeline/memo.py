"""Stage 6: the decision memo. A model writes; code checks every ID and every number.

The model sees the ranked table, the claims, a bounded pack of quotes and the run's facts,
never the raw file. The check proves the memo copied its numbers correctly. It does not
prove the argument is sound: that is the human read.
"""

import json
import math
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipeline import gemma, group, hashing, rank, state, verify
from pipeline.ledger import CapReached

ROLE = "memo"
PROMPT = Path(__file__).resolve().parents[1] / "prompts/memo-v1.md"
MAX_TOKENS = 1500
PER_ISSUE = 5
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")
SCHEMA = {"type": "object", "properties": {"memo": {"type": "string"}}, "required": ["memo"], "additionalProperties": False}
KNOWN_LIMITS = (
    "The labels come from a model and were checked against a small hand-labeled set.",
    "The quote and the topic come from separate questions and can point at different sentences.",
    "Each issue is a whole topic, not a single defect.",
    "Agreement between the two engines is not accuracy.",
    "The quotes are the most severe examples and a few picked by hash, not typical ones.",
)

CLAIM = re.compile(r"\[(CL-\d{3})\]")
REVIEW = re.compile(r"\[review:([^\]\s]+)\]")
ISSUE = re.compile(r"\bissue-[a-z]+")
QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”')
NUMBER = re.compile(r"(?<![\w.\-])\d[\d,]*(?:\.\d+)?")
RANK_WORD = re.compile(r"(?:\brank(?:s|ed)?|\bnumber|#)\s*\d+\b", re.I)
LIST_NUMBER = re.compile(r"^\s*(?:[-*]\s+)?\d+[.)]\s")
UNSUPPORTED = re.compile(r"\b(revenue|churn|arpu|ltv|lifetime value)\b|[$€£]\s?\d", re.I)


class MemoFailed(Exception):
    """Two memos in a row failed the check. No final memo is saved; Travis decides what to do."""

    def __init__(self, problems):
        super().__init__("the memo failed its check: " + "; ".join(problems))
        self.problems = problems


class NothingToWrite(Exception):
    """A run with no complaint or cancellation has no issue to write about."""


def claims(ranking):
    """One claim for each issue and metric, in rank order. The value is the ranking's own string."""
    out = []
    for row in ranking:
        for metric in METRICS:
            out.append({"claim_id": f"CL-{len(out) + 1:03d}", "issue_id": row["issue_id"], "metric": metric, "value": row[metric]})
    return out


def cited_claims(text, all_claims):
    cited = set(CLAIM.findall(text))
    return [c for c in all_claims if c["claim_id"] in cited]


def evidence_pack(db, run, *, per_issue=PER_ISSUE):
    """Everything the memo model is given. Built by code from saved results."""
    run_row = state.load_run(db, run)
    members = db.execute(
        "SELECT m.issue_id, r.review_id, r.cache_source_id, s.intent, s.severity, s.evidence_quote FROM membership m "
        "JOIN reviews r ON r.run=m.run AND r.review_id=m.review_id "
        "JOIN results s ON s.run=r.run AND s.text_key=r.text_key WHERE m.run=?",
        (run,),
    ).fetchall()
    ranking = rank.rank(
        [{"review_id": m["review_id"], "status": "completed", "intent": m["intent"], "severity": m["severity"]} for m in members],
        [(m["issue_id"], m["review_id"]) for m in members],
    )
    named = {r["issue_id"]: r for r in db.execute("SELECT * FROM issues WHERE run=?", (run,))}
    severe_n = math.ceil(per_issue * 3 / 5)
    evidence = {}
    for row in ranking:
        originals = [m for m in members if m["issue_id"] == row["issue_id"] and m["cache_source_id"] is None and len(m["evidence_quote"]) <= group.MAX_QUOTE]
        originals.sort(key=lambda m: hashing.order_key(run_row["sample_seed"], m["review_id"]))
        severe = sorted(originals, key=lambda m: -m["severity"])[:severe_n]
        severe_ids = {m["review_id"] for m in severe}
        hashed = [m for m in originals if m["review_id"] not in severe_ids][: per_issue - len(severe)]
        evidence[row["issue_id"]] = [
            {"review_id": m["review_id"], "quote": m["evidence_quote"], "severity": m["severity"], "kind": kind}
            for kind, group_ in (("most_severe", severe), ("picked_by_hash", hashed))
            for m in group_
        ]
    counts = dict(db.execute("SELECT status, COUNT(*) FROM reviews WHERE run=? GROUP BY status", (run,)).fetchall())
    completed = counts.get("completed", 0)
    flagged = db.execute(
        "SELECT COUNT(*) FROM reviews r JOIN results s ON s.run=r.run AND s.text_key=r.text_key "
        "WHERE r.run=? AND r.status='completed' AND s.needs_review=1",
        (run,),
    ).fetchone()[0]
    agreement = verify.report(db, run)["by_group"]
    return {
        "ranking": ranking,
        "issues": [
            {"issue_id": r["issue_id"], "name": named[r["issue_id"]]["name"], "description": named[r["issue_id"]]["description"]}
            for r in ranking
            if r["issue_id"] in named
        ],
        "claims": claims(ranking),
        "evidence": evidence,
        "evidence_note": "These quotes are the most severe examples and a few picked by hash. They are not typical.",
        "run_facts": {
            "completed": completed,
            "quarantined": counts.get("quarantined", 0),
            "needs_review_flagged": flagged,
            "needs_review_share_percent": f"{100 * flagged / completed:.1f}" if completed else "0.0",
            "verifier_agreement": {
                name: {"pairs": a["pairs"], "all_three": a["all_three"]} for name, a in agreement.items()
            },
            "known_limits": list(KNOWN_LIMITS),
        },
    }


def _numbers(value):
    """Every number inside the run facts, as Decimals."""
    if isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        return {Decimal(str(value))}
    if isinstance(value, str):
        try:
            return {Decimal(value)}
        except InvalidOperation:
            return set()
    if isinstance(value, dict):
        return set().union(*(_numbers(v) for k, v in value.items() if k != "known_limits")) if value else set()
    if isinstance(value, list):
        return set().union(*map(_numbers, value)) if value else set()
    return set()


def _paragraphs(text):
    """Each paragraph or list item (one line of the memo) with its sentences."""
    for line in text.split("\n"):
        line = LIST_NUMBER.sub("", line)  # "1. " at the start of a line numbers a list item; it is not a claim
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
        if sentences:
            yield line, sentences


def _section(text, title):
    """The text under the heading that starts with `title`, up to the next heading. None when absent."""
    lines, inside, found = [], False, False
    for line in text.split("\n"):
        if line.lstrip().startswith("#"):
            inside = line.lstrip("# ").strip().lower().startswith(title.lower())
            found = found or inside
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines) if found else None


def check(text, pack):
    """Problems with a memo, as sentences a model or a person can act on. Empty means it passes."""
    problems = []
    plain = QUOTED.sub('""', text)  # quoted customer text is evidence: its numbers and words are not the memo's claims
    known_claims = {c["claim_id"]: c for c in pack["claims"]}
    known_issues = {r["issue_id"] for r in pack["ranking"]}
    known_reviews = {q["review_id"] for quotes in pack["evidence"].values() for q in quotes}

    for claim_id in sorted(set(CLAIM.findall(plain)) - known_claims.keys()):
        problems.append(f"{claim_id} is not a claim ID in the input")
    for review_id in sorted(set(REVIEW.findall(text)) - known_reviews):
        problems.append(f"[review:{review_id}] is not a review ID in the input")
    for issue_id in sorted(set(ISSUE.findall(plain)) - known_issues):
        problems.append(f"{issue_id} is not an issue ID in the input")
    if not CLAIM.search(plain):
        problems.append("the memo cites no claim ID")
    if not REVIEW.search(text):
        problems.append("the memo cites no review ID")

    recommendation = _section(plain, "Recommendation")
    if recommendation is None:
        problems.append("there is no Recommendation section")
    elif pack["ranking"] and pack["ranking"][0]["issue_id"] not in recommendation:
        problems.append(f"the Recommendation does not name rank 1 ({pack['ranking'][0]['issue_id']}) or say why not")
    if _section(plain, "Limits") is None:
        problems.append("there is no Limits section")
    if UNSUPPORTED.search(plain):
        problems.append("the memo speaks of revenue, churn or money, which this data cannot support")

    facts = _numbers(pack["run_facts"])
    for paragraph, sentences in _paragraphs(plain):
        if paragraph.lstrip().startswith("#"):
            continue
        # A claim's issue must be named in the paragraph or list item that cites it. The first version asked for the
        # same sentence, which rejected "issue-x ranks first. It has 37 [CL-004]." from every model that wrote it.
        named = set(ISSUE.findall(paragraph))
        for sentence in sentences:
            cited = [known_claims[c] for c in CLAIM.findall(sentence) if c in known_claims]
            for claim in cited:
                if claim["issue_id"] not in named:
                    problems.append(f"{claim['claim_id']} is not in the same paragraph as its issue {claim['issue_id']}")
            bare = sentence
            for pattern in (CLAIM, REVIEW, ISSUE, RANK_WORD):
                bare = pattern.sub(" ", bare)
            # A number still answers to its own sentence: it must be the value of a claim cited there, or a run fact.
            allowed = {Decimal(c["value"]) for c in cited} | facts
            for token in NUMBER.findall(bare):
                if Decimal(token.replace(",", "")) not in allowed:
                    problems.append(f"the number {token} is neither the value of a claim cited in its sentence nor a run fact")
    return list(dict.fromkeys(problems))


def config(client, per_issue, prompt_path=PROMPT):
    """The memo setup, the prompt's content included, so an edited prompt is never answered from an old memo."""
    name = getattr(client, "label", client.model)  # a paid client's label also names its effort setting
    return f"{name}/memo-v1-{hashing.short_sha(prompt_path)}/schema-v1/max-{MAX_TOKENS}/quotes-{per_issue}"


def recheck(db, run, text):
    """Problems with a memo against the run's numbers as they stand now. Used at export and for a hand edit."""
    pointer = db.execute("SELECT input_json FROM artifacts WHERE key=?", (f"final-memo:{run}",)).fetchone()
    saved = db.execute("SELECT input_json FROM artifacts WHERE key=?", (pointer["input_json"],)).fetchone() if pointer else None
    per_issue = PER_ISSUE
    if saved:
        try:
            per_issue = max([per_issue, *(len(quotes) for quotes in json.loads(saved["input_json"])["evidence"].values())])
        except (ValueError, KeyError, TypeError):
            pass
    return check(text, evidence_pack(db, run, per_issue=per_issue))


def save_edited(db, run, text):
    """Make a hand-edited memo the run's memo, if it passes the same check a model's memo must pass."""
    problems = recheck(db, run, text)
    if problems:
        raise MemoFailed(problems)
    key = f"{run}:edited:{hashing.text_key(text)}"
    with state.tx(db):
        db.execute(
            "INSERT OR REPLACE INTO artifacts (key, run, role, input_json, output_json, model, created_utc) VALUES (?,?,?,?,?,?,?)",
            (key, run, "memo-edited", json.dumps(evidence_pack(db, run), ensure_ascii=False, sort_keys=True),
             json.dumps({"memo": text}, ensure_ascii=False), "edited by hand", state.now_utc()),
        )  # fmt: skip
        _set_final(db, run, key, text, "edited by hand")


def final(db, run):
    """The memo saved for this run, or None."""
    row = db.execute("SELECT output_json FROM artifacts WHERE key=?", (f"final-memo:{run}",)).fetchone()
    return json.loads(row["output_json"])["memo"] if row else None


def _set_final(db, run, key, text, model):
    db.execute(
        "INSERT OR REPLACE INTO artifacts (key, run, role, input_json, output_json, model, created_utc) VALUES (?,?,?,?,?,?,?)",
        (f"final-memo:{run}", run, "memo-final", key, json.dumps({"memo": text}, ensure_ascii=False), model, state.now_utc()),
    )


def write(db, run, client, *, per_issue=PER_ISSUE, clock=time.monotonic, prompt_path=PROMPT, warm_from=None, ledger=None):
    """Write the memo for the run and return it. Raises MemoFailed after two memos that fail the check.

    `ledger` is given when the memo model is a paid one: each call then reserves its worst case
    and settles its reported usage, and the ledger's CapReached is raised before a call that would pass the cap."""
    state.recover_orphans(db, run, ledger=ledger, roles=(ROLE,))  # before anything else: an open call would make export refuse
    pack = evidence_pack(db, run, per_issue=per_issue)
    if not pack["ranking"]:
        raise NothingToWrite("no complaint or cancellation in this run, so there is nothing to rank or recommend")
    label_config = config(client, per_issue, prompt_path)
    content = group.artifact_key(ROLE, label_config, pack)
    key = f"{run}:{content}"
    saved = group.cached(db, run, content, warm_from)
    if saved:
        text = json.loads(saved["output_json"])["memo"]
        _set_final(db, run, saved["key"], text, saved["model"])
        return text

    session = state.open_session(db, run, ROLE, 1, clock)
    try:
        client.check()
    except gemma.ServerProblem:
        state.close_session(db, session, "server_problem", clock)
        raise
    system = Path(prompt_path).read_text(encoding="utf-8").strip("\n")
    user = json.dumps(pack, ensure_ascii=False, sort_keys=True)
    problems = []
    for _ in range(2):  # one retry, with the problems listed
        message = user
        if problems:
            message += "\n\nYour previous memo had these problems. Fix every one and return the whole memo again:\n"
            message += "\n".join(f"- {p}" for p in problems)
        request_id = uuid.uuid4().hex
        # A paid call reserves its worst case: a byte is never less than a token, and the output has a ceiling.
        ceiling = getattr(client, "output_ceiling", lambda limit: limit)(MAX_TOKENS)
        try:
            state.begin_attempt(
                db, ledger, request_id=request_id, run=run, role=ROLE, review_ids=[], model=client.model,
                label_config=label_config, session_id=session,
                reserve_tokens=len((system + message).encode("utf-8")) if ledger else 0, reserve_output_tokens=ceiling if ledger else 0,
            )  # fmt: skip
        except CapReached:
            state.close_session(db, session, "cap", clock)
            raise
        sent, reply = time.monotonic(), None
        try:
            reply = client.ask(system, message, SCHEMA, max_tokens=MAX_TOKENS)
        except gemma.ServerProblem as e:
            state.finish_attempt(db, request_id, outcome="failed", error=str(e)[:500], seconds=time.monotonic() - sent, ledger=ledger)
            state.close_session(db, session, "server_problem", clock)
            raise
        except gemma.InvalidOutput as e:
            state.finish_attempt(db, request_id, outcome="failed", error=str(e)[:500], seconds=time.monotonic() - sent, ledger=ledger)
            problems = [str(e)]
            continue
        text = reply.data.get("memo")
        problems = ["the answer holds no memo text"] if not isinstance(text, str) or not text.strip() else check(text, pack)
        if problems:
            with state.tx(db):
                # A rejected memo is evidence of what the model wrote; without its text the rejection cannot be read.
                db.execute(
                    "INSERT OR REPLACE INTO artifacts (key, run, role, input_json, output_json, model, created_utc) VALUES (?,?,?,?,?,?,?)",
                    (f"{run}:rejected:{request_id}", run, "memo-rejected", key,
                     json.dumps({"memo": text if isinstance(text, str) else None, "problems": problems}, ensure_ascii=False), reply.model, state.now_utc()),
                )  # fmt: skip
            state.finish_attempt(
                db, request_id, outcome="failed", error="; ".join(problems)[:500], seconds=time.monotonic() - sent,
                input_tokens=reply.input_tokens, output_tokens=reply.output_tokens, ledger=ledger,
            )  # fmt: skip
            continue
        with state.tx(db):
            db.execute(
                "INSERT OR REPLACE INTO artifacts (key, run, role, input_json, output_json, model, created_utc) VALUES (?,?,?,?,?,?,?)",
                (key, run, ROLE, user, json.dumps({"memo": text}, ensure_ascii=False), reply.model, state.now_utc()),
            )
            _set_final(db, run, key, text, reply.model)
        state.finish_attempt(
            db, request_id, outcome="succeeded", seconds=time.monotonic() - sent,
            input_tokens=reply.input_tokens, output_tokens=reply.output_tokens, ledger=ledger,
        )  # fmt: skip
        state.close_session(db, session, "finished", clock)
        return text
    state.close_session(db, session, "failed", clock)
    raise MemoFailed(problems)
