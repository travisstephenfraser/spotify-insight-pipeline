"""The state file: one SQLite database that holds every run.

Nothing here commits on its own. A caller that needs several writes to land together
wraps them in `tx(db)`; a single statement outside `tx` commits by itself.
"""

import contextlib
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run TEXT PRIMARY KEY, created_utc TEXT NOT NULL,
  input_path TEXT NOT NULL, input_sha256 TEXT NOT NULL, seed TEXT NOT NULL,
  verify_seed TEXT NOT NULL, verify_size INTEGER NOT NULL, sample_seed TEXT NOT NULL,
  code_commit TEXT NOT NULL, code_hash TEXT NOT NULL,   -- code_hash: SHA-256 over the path and bytes of every pipeline/*.py
  label_config TEXT NOT NULL,
  hashes_json TEXT NOT NULL,      -- content hash of each prompt, schema, word list, splitter, and the cut-off
  configs_json TEXT NOT NULL      -- verify, group and memo model, settings and prompt version
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id INTEGER PRIMARY KEY, run TEXT NOT NULL, stage TEXT NOT NULL, workers INTEGER NOT NULL,
  started_utc TEXT NOT NULL, started_mono REAL NOT NULL, last_mono REAL, ended_mono REAL, ended_how TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  run TEXT NOT NULL, review_id TEXT NOT NULL,
  review_text TEXT NOT NULL, review_rating TEXT NOT NULL, review_likes TEXT NOT NULL,
  app_version TEXT NOT NULL, review_timestamp TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, text_key TEXT NOT NULL, run_order INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','completed','quarantined')),
  reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  cache_source_id TEXT,           -- NULL on an original; the original's review_id on a copy
  completed_session INTEGER, in_verify_sample INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (run, review_id)
);
CREATE INDEX IF NOT EXISTS reviews_by_text ON reviews (run, text_key);
CREATE INDEX IF NOT EXISTS reviews_by_order ON reviews (run, status, run_order);
CREATE TABLE IF NOT EXISTS results (
  run TEXT NOT NULL, text_key TEXT NOT NULL,
  topic TEXT NOT NULL, intent TEXT NOT NULL, severity INTEGER NOT NULL, sentiment REAL NOT NULL,
  entities_json TEXT NOT NULL, evidence_quote TEXT NOT NULL, needs_review INTEGER NOT NULL,
  min_top_probability REAL NOT NULL, raw_json TEXT NOT NULL, model TEXT NOT NULL,
  PRIMARY KEY (run, text_key)
);
CREATE TABLE IF NOT EXISTS calls (
  request_id TEXT PRIMARY KEY, run TEXT NOT NULL, role TEXT NOT NULL,
  review_ids_json TEXT NOT NULL, model TEXT NOT NULL, label_config TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('pending','succeeded','failed')),
  input_tokens INTEGER, output_tokens INTEGER, usage_known INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER, error TEXT, started_utc TEXT NOT NULL, seconds REAL, session_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, run TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('opening','reserve','actual','kept','adjust')),
  input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL DEFAULT 0,
  usd_per_mtok_in TEXT NOT NULL, usd_per_mtok_out TEXT NOT NULL,   -- the rates in force when the row was written
  usd_fixed TEXT, note TEXT, created_utc TEXT NOT NULL             -- usd_fixed: a dollar amount on 'opening' and 'adjust' rows
);
CREATE UNIQUE INDEX IF NOT EXISTS ledger_settled ON ledger (request_id) WHERE kind IN ('actual','kept');
CREATE INDEX IF NOT EXISTS ledger_by_request ON ledger (request_id, kind);
CREATE TABLE IF NOT EXISTS verify (
  run TEXT NOT NULL, review_id TEXT NOT NULL, outcome TEXT NOT NULL,   -- 'predicted' or 'failed'
  topic TEXT, intent TEXT, severity INTEGER, reason TEXT, request_id TEXT,
  PRIMARY KEY (run, review_id)
);
CREATE TABLE IF NOT EXISTS issues (run TEXT NOT NULL, issue_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL, model TEXT, PRIMARY KEY (run, issue_id));
CREATE TABLE IF NOT EXISTS membership (run TEXT NOT NULL, issue_id TEXT NOT NULL, review_id TEXT NOT NULL, PRIMARY KEY (run, issue_id, review_id));
CREATE TABLE IF NOT EXISTS artifacts (key TEXT PRIMARY KEY, run TEXT NOT NULL, role TEXT NOT NULL, input_json TEXT NOT NULL, output_json TEXT NOT NULL, model TEXT NOT NULL, created_utc TEXT NOT NULL);
"""


class RunExists(Exception):
    pass


class NoSuchRun(Exception):
    pass


class ResumeRefused(Exception):
    """Something that shapes a label changed since the run was created."""

    def __init__(self, names):
        super().__init__("changed since this run started: " + ", ".join(names))
        self.names = names


class DirtyTree(Exception):
    pass


class DuplicateRequest(Exception):
    pass


class AlreadySettled(Exception):
    """This request already has its outcome. A request is settled exactly once."""


class Locked(Exception):
    def __init__(self, pid):
        super().__init__(f"the state file is in use by process {pid}")
        self.pid = pid


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path, *, synchronous="FULL"):
    """Open the state file, creating the schema if it is new. Write-ahead mode, rows by name.

    `synchronous` FULL waits for the disk on every commit, so a saved response survives a power cut.
    Tests pass OFF: a killed process still loses nothing, and they run many times faster.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(
        path, timeout=30, isolation_level=None, check_same_thread=False
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    assert synchronous in ("FULL", "NORMAL", "OFF"), synchronous
    db.execute(f"PRAGMA synchronous={synchronous}")
    db.executescript(SCHEMA)
    return db


@contextlib.contextmanager
def tx(db):
    """All writes inside land together or not at all."""
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


class RunLock:
    """One process per state file. The lock file holds the holder's PID."""

    def __init__(self, path):
        self.file = Path(str(path) + ".lock")
        self.held = False

    def acquire(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pid = self._holder()
                if pid is not None and _alive(pid):
                    raise Locked(pid) from None
                print(
                    f"clearing a lock left by process {pid}, which is no longer running",
                    file=sys.stderr,
                )
                self.file.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            self.held = True
            return
        raise Locked(self._holder())

    def release(self):
        if self.held:
            self.file.unlink(missing_ok=True)
            self.held = False

    def _holder(self):
        try:
            return int(self.file.read_text().strip())
        except (OSError, ValueError):
            return None


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def create_run(
    db, name, *, input_path, input_sha256, seed, verify_seed, verify_size, sample_seed,
    code_commit, code_hash, label_config, hashes, configs,
):  # fmt: skip
    try:
        db.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                name, now_utc(), str(input_path), input_sha256, seed, verify_seed, verify_size, sample_seed,
                code_commit, code_hash, label_config, json.dumps(hashes, sort_keys=True), json.dumps(configs, sort_keys=True),
            ),
        )  # fmt: skip
    except sqlite3.IntegrityError:
        raise RunExists(name) from None


def load_run(db, name):
    row = db.execute("SELECT * FROM runs WHERE run=?", (name,)).fetchone()
    if row is None:
        raise NoSuchRun(name)
    return row


def check_resume(
    db,
    name,
    *,
    input_sha256,
    seed,
    code_hash,
    hashes,
    allow_code=None,
    code_commit=None,
):
    """Refuse to resume when the input, the seed, any hashed setting or the code differs.

    Changed code alone can be allowed by naming its hash. The override is logged in the
    run's configs and the new code becomes the run's code.
    """
    row = load_run(db, name)
    names = []
    if row["input_sha256"] != input_sha256:
        names.append("input")
    if row["seed"] != seed:
        names.append("seed")
    saved = json.loads(row["hashes_json"])
    names += sorted(
        k for k in saved.keys() | hashes.keys() if saved.get(k) != hashes.get(k)
    )
    code_changed = row["code_hash"] != code_hash
    if code_changed and allow_code != code_hash:
        names.append("code")
    if names:
        raise ResumeRefused(names)
    if code_changed:
        configs = json.loads(row["configs_json"])
        configs.setdefault("code_overrides", []).append(
            {"from": row["code_hash"], "to": code_hash, "at": now_utc()}
        )
        db.execute(
            "UPDATE runs SET code_hash=?, code_commit=?, configs_json=? WHERE run=?",
            (
                code_hash,
                code_commit or row["code_commit"],
                json.dumps(configs, sort_keys=True),
                name,
            ),
        )


def code_fingerprint(root):
    """(git commit, code hash, tree is clean).

    The code hash covers the path and bytes of every pipeline/*.py, so two different
    uncommitted edits never look the same. Clean means no change under pipeline/ or prompts/.
    """
    root = Path(root)
    h = hashlib.sha256()
    for path in sorted((root / "pipeline").rglob("*.py")):
        h.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        h.update(path.read_bytes() + b"\0")

    def git(*args):
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True
        )
        return out.stdout.strip() if out.returncode == 0 else None

    commit = git("rev-parse", "HEAD") or "unknown"
    status = git("status", "--porcelain", "--", "pipeline", "prompts")
    return commit, h.hexdigest(), status == ""


def require_clean_tree(root, *, real):
    """A run that calls a real model must run committed code, so its recorded commit is the code that ran."""
    if real and not code_fingerprint(root)[2]:
        raise DirtyTree(
            "commit the changes under pipeline/ and prompts/ before a real run"
        )


def open_session(db, run, stage, workers, clock):
    cur = db.execute(
        "INSERT INTO sessions (run, stage, workers, started_utc, started_mono) VALUES (?,?,?,?,?)",
        (run, stage, workers, now_utc(), clock()),
    )
    return cur.lastrowid


def heartbeat(db, session_id, clock):
    db.execute(
        "UPDATE sessions SET last_mono=? WHERE session_id=?", (clock(), session_id)
    )


def close_session(db, session_id, ended_how, clock):
    now = clock()
    db.execute(
        "UPDATE sessions SET last_mono=?, ended_mono=?, ended_how=? WHERE session_id=?",
        (now, now, ended_how, session_id),
    )


def close_crashed_sessions(db, run):
    """A session with no end belongs to a process that died. It ended at its last heartbeat."""
    cur = db.execute(
        "UPDATE sessions SET ended_mono=COALESCE(last_mono, started_mono), ended_how='crashed' "
        "WHERE run=? AND ended_mono IS NULL",
        (run,),
    )
    return cur.rowcount


# ---- The save protocol (spec section 4, "How a request is saved") ----


def begin_attempt(db, ledger, *, request_id, run, role, review_ids, model, label_config, session_id, reserve_tokens, reserve_output_tokens=0):
    """Commit the intent to send one request, with its reservation. No commit, no send.

    `ledger` is None for calls to the local model, which spend no money. Raises the ledger's
    CapReached, writing nothing, when the reservation would pass the cap.
    """
    try:
        with tx(db):
            if ledger is not None:
                ledger.reserve(request_id, run, reserve_tokens, reserve_output_tokens)
            try:
                db.execute(
                    "INSERT INTO calls (request_id, run, role, review_ids_json, model, label_config, outcome, started_utc, "
                    "session_id) VALUES (?,?,?,?,?,?,'pending',?,?)",
                    (request_id, run, role, json.dumps(list(review_ids)), model, label_config, now_utc(), session_id),
                )
            except sqlite3.IntegrityError:
                raise DuplicateRequest(request_id) from None
    except BaseException:
        if ledger is not None:
            ledger.reload()
        raise


def finish_attempt(
    db, request_id, *, outcome, input_tokens=None, output_tokens=None, http_status=None, error=None, seconds,
    result=None, ledger=None, not_sent=False,
):  # fmt: skip
    """Save everything one response brought, in one transaction.

    The call row and the charge are always saved. With `result` (a validated answer) the
    result row is saved too, and the original and every copy of its text become completed.
    """
    try:
        with tx(db):
            call = db.execute("SELECT * FROM calls WHERE request_id=?", (request_id,)).fetchone()
            if call is None or call["outcome"] != "pending":
                raise AlreadySettled(request_id)
            db.execute(
                "UPDATE calls SET outcome=?, input_tokens=?, output_tokens=?, usage_known=?, http_status=?, error=?, "
                "seconds=? WHERE request_id=?",
                (outcome, input_tokens, output_tokens, int(input_tokens is not None), http_status, error, seconds, request_id),
            )
            if ledger is not None:
                # A request that never left this machine cost nothing: its reservation is released, not kept.
                ledger.settle(request_id, *((0, 0) if not_sent else (input_tokens, output_tokens)))
            if result is not None:
                (review_id,) = json.loads(call["review_ids_json"])
                review = db.execute(
                    "SELECT text_key FROM reviews WHERE run=? AND review_id=?", (call["run"], review_id)
                ).fetchone()
                db.execute(
                    "INSERT INTO results (run, text_key, topic, intent, severity, sentiment, entities_json, evidence_quote, "
                    "needs_review, min_top_probability, raw_json, model) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        call["run"], review["text_key"], result["topic"], result["intent"], result["severity"],
                        result["sentiment"], json.dumps(result["entities"], ensure_ascii=False), result["evidence_quote"],
                        int(result["needs_review"]), result["min_top_probability"],
                        json.dumps(result["raw"], ensure_ascii=False), result["model"],
                    ),
                )  # fmt: skip
                db.execute(
                    "UPDATE reviews SET status='completed', completed_session=? WHERE run=? AND text_key=? AND status='pending'",
                    (call["session_id"], call["run"], review["text_key"]),
                )
    except BaseException:
        if ledger is not None:
            ledger.reload()
        raise


def recover_orphans(db, run, *, ledger=None, roles=None):
    """Close the calls a dead process left open. Returns how many, by role.

    Each becomes a failed call with usage unknown, and its reservation stays counted as
    spent. No review's status changes: every stage finds its own unfinished work.
    """
    counts = {}
    with tx(db):
        for call in db.execute("SELECT request_id, role FROM calls WHERE run=? AND outcome='pending'", (run,)).fetchall():
            if roles is not None and call["role"] not in roles:
                continue  # another stage's open call: that stage closes it, with its own ledger
            db.execute(
                "UPDATE calls SET outcome='failed', usage_known=0, error=? WHERE request_id=?",
                ("the process ended before a response was saved", call["request_id"]),
            )
            if ledger is not None:
                ledger.settle(call["request_id"])
            counts[call["role"]] = counts.get(call["role"], 0) + 1
    if ledger is not None:
        ledger.reload()
    return counts


def return_to_pending(db, run, review_id):
    """A review whose attempts all failed for now. It stays pending and is tried again later."""
    db.execute("UPDATE reviews SET attempts = attempts + 1 WHERE run=? AND review_id=?", (run, review_id))


def quarantine(db, run, review_id, reason):
    """The original and every copy of its text. A copy keeps its pointer; export leaves it off."""
    db.execute(
        "UPDATE reviews SET status='quarantined', reason=? WHERE run=? AND status='pending' AND text_key = "
        "(SELECT text_key FROM reviews WHERE run=? AND review_id=?)",
        (reason, run, run, review_id),
    )
