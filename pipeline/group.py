"""Stage 4: group complaints into issues. Code assigns; a model only names.

Every completed complaint or cancellation joins exactly one issue, the one for its topic.
Names and descriptions never change membership or ranking.
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from pipeline import gemma, hashing, labels, state

ROLE = "group"
PROMPT = Path(__file__).resolve().parents[1] / "prompts/group-v1.md"
MAX_TOKENS = 300
MAX_QUOTE = 500  # a longer quote is left out, never cut: a cut quote is not an exact piece of the review
MAX_NAME, MAX_DESCRIPTION = 80, 300
SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
    "required": ["name", "description"],
    "additionalProperties": False,
}


@dataclass
class Outcome:
    ended_how: str  # finished, no_complaints, server_problem, no_success
    named: int = 0  # issues named by a call in this session
    cached: int = 0  # issues whose name was reused from a saved artifact
    fallbacks: int = 0  # issues given the topic name and the contract's definition
    session_id: int | None = None
    message: str = ""


def assign(db, run):
    """Rebuild membership for the run: one row per completed complaint or cancellation. Returns the count."""
    with state.tx(db):
        db.execute("DELETE FROM membership WHERE run=?", (run,))
        cur = db.execute(
            "INSERT INTO membership (run, issue_id, review_id) "
            "SELECT r.run, 'issue-' || s.topic, r.review_id FROM reviews r "
            "JOIN results s ON s.run=r.run AND s.text_key=r.text_key "
            "WHERE r.run=? AND r.status='completed' AND s.intent IN ('complaint','cancellation')",
            (run,),
        )
    return cur.rowcount


def config(client, quotes_per_issue):
    return f"{client.model}/group-v1/schema-v1/max-{MAX_TOKENS}/quotes-{quotes_per_issue}"


def artifact_key(role, config_string, payload):
    """Names and memos are cached by what went in: the same input under the same setup is never asked twice."""
    blob = json.dumps({"role": role, "config": config_string, "input": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def quotes_for(db, run, issue_id, limit, sample_seed):
    """Up to `limit` quotes from the issue's originals, in the order of the sample seed."""
    rows = db.execute(
        "SELECT r.review_id, s.evidence_quote FROM membership m "
        "JOIN reviews r ON r.run=m.run AND r.review_id=m.review_id "
        "JOIN results s ON s.run=r.run AND s.text_key=r.text_key "
        "WHERE m.run=? AND m.issue_id=? AND r.cache_source_id IS NULL",
        (run, issue_id),
    ).fetchall()
    rows.sort(key=lambda r: hashing.order_key(sample_seed, r["review_id"]))
    fitting = [{"review_id": r["review_id"], "quote": r["evidence_quote"]} for r in rows if len(r["evidence_quote"]) <= MAX_QUOTE]
    return fitting[:limit]


def _checked(data):
    name, description = data.get("name"), data.get("description")
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME:
        raise gemma.InvalidOutput(f"the name is blank or over {MAX_NAME} characters")
    if not isinstance(description, str) or not description.strip() or len(description) > MAX_DESCRIPTION:
        raise gemma.InvalidOutput(f"the description is blank or over {MAX_DESCRIPTION} characters")
    return {"name": name.strip(), "description": description.strip()}


def name_issues(db, run, client, *, quotes_per_issue=30, clock=time.monotonic, prompt_path=PROMPT):
    """Name every issue that has members. Safe to call again: saved names are reused."""
    issue_ids = [r[0] for r in db.execute("SELECT DISTINCT issue_id FROM membership WHERE run=? ORDER BY issue_id", (run,))]
    if not issue_ids:
        return Outcome("no_complaints", message="no complaint or cancellation in this run, so there is no issue to name")
    run_row = state.load_run(db, run)
    state.recover_orphans(db, run, roles=(ROLE,))
    session = state.open_session(db, run, ROLE, 1, clock)
    out = Outcome("finished", session_id=session)
    system, label_config = Path(prompt_path).read_text(encoding="utf-8").strip("\n"), config(client, quotes_per_issue)

    def end(how, message=""):
        out.ended_how, out.message = how, message
        state.close_session(db, session, how, clock)
        return out

    def save(issue_id, data, model):
        db.execute(
            "INSERT OR REPLACE INTO issues (run, issue_id, name, description, model) VALUES (?,?,?,?,?)",
            (run, issue_id, data["name"], data["description"], model),
        )

    checked_server = False
    for issue_id in issue_ids:
        topic = issue_id.removeprefix("issue-")
        payload = {
            "issue_id": issue_id,
            "topic": topic,
            "definition": labels.TOPIC_DEFINITIONS.get(topic, ""),
            "quotes": quotes_for(db, run, issue_id, quotes_per_issue, run_row["sample_seed"]),
        }
        key = artifact_key(ROLE, label_config, payload)
        saved = db.execute("SELECT output_json, model FROM artifacts WHERE key=?", (key,)).fetchone()
        if saved:
            save(issue_id, json.loads(saved["output_json"]), saved["model"])
            out.cached += 1
            continue
        if not checked_server:
            try:
                client.check()
            except gemma.ServerProblem as e:
                return end("server_problem", str(e))
            checked_server = True
        user = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        data = None
        for _ in range(2):  # retry once
            request_id = uuid.uuid4().hex
            state.begin_attempt(
                db, None, request_id=request_id, run=run, role=ROLE, review_ids=[], model=client.model,
                label_config=label_config, session_id=session, reserve_tokens=0,
            )  # fmt: skip
            sent, reply = time.monotonic(), None
            try:
                reply = client.ask(system, user, SCHEMA, max_tokens=MAX_TOKENS)
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
            with state.tx(db):
                db.execute(
                    "INSERT OR REPLACE INTO artifacts (key, run, role, input_json, output_json, model, created_utc) VALUES (?,?,?,?,?,?,?)",
                    (key, run, ROLE, user, json.dumps(data, ensure_ascii=False), reply.model, state.now_utc()),
                )
                save(issue_id, data, reply.model)
            state.finish_attempt(
                db, request_id, outcome="succeeded", seconds=time.monotonic() - sent,
                input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
            )  # fmt: skip
            out.named += 1
            break
        else:
            # Two invalid answers: the topic's own name and the contract's definition stand in, and it is logged.
            save(issue_id, {"name": topic, "description": labels.TOPIC_DEFINITIONS.get(topic, topic)}, None)
            out.fallbacks += 1
        state.heartbeat(db, session, clock)

    succeeded = db.execute("SELECT 1 FROM calls WHERE run=? AND role=? AND outcome='succeeded' LIMIT 1", (run, ROLE)).fetchone()
    if not succeeded and not out.cached:
        return end("no_success", "no naming call succeeded; the checker needs one succeeded group call")
    return end("finished")
