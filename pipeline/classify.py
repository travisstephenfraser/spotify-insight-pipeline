"""Stage 2: classify every original text with the labeler, saving after every response.

The calling thread owns the database and decides everything. Worker threads only wait for
the rate limiter and send one request. Every attempt gets its own intent row before it is
sent and its own outcome after, so a kill at any point loses nothing that was saved.
"""

import heapq
import json
import queue
import random
import threading
import time
import uuid
from dataclasses import dataclass, field, replace

from pipeline import jev, labels, prepare, state
from pipeline import ledger as ledger_module

ATTEMPTS = 4  # tries per round on temporary errors
MAX_WORKERS = 16  # the design's ceiling on requests in flight
BREAKER_FLOOR = 8  # failures in a row, with no success between, after which no new review is admitted
BACKOFF = (
    0.5,
    2.0,
    8.0,
)  # seconds before tries 2, 3 and 4, each with up to 25% jitter added
NO_SUCCESS_SECONDS = (
    60  # stop when requests are being sent and none has succeeded for this long
)
GUARD_MIN = 500  # the degenerate-label guards apply from this many labeled texts


class GuardFailed(Exception):
    """The labels look like a measurement reading itself. The run stops before the next stage."""

    def __init__(self, names, supplied):
        how = (
            "This is a supplied file, so there is no way past it."
            if supplied
            else "Restart with --accept-guard NAME if the input truly is like this."
        )
        super().__init__(f"guard failed: {', '.join(names)}. {how}")
        self.names, self.supplied = names, supplied


@dataclass
class Outcome:
    ended_how: str  # finished, time_box, stop_after, interrupted, cap, fatal, no_success_60s, outage, stuck
    completed: int
    pending: int
    quarantined: int
    new_completions: int  # originals completed in this session
    session_id: int
    stuck: list = field(
        default_factory=list
    )  # originals whose requests kept failing; still pending


@dataclass(frozen=True)
class _Job:
    review_id: str
    text: str
    request: dict
    size: (
        int  # request body in bytes: the reservation, and the limiter's token estimate
    )
    attempt: int = 1  # try number within this round, for temporary errors
    invalid_tries: int = 0
    round: int = 1


def _worker(labeler, limiter, jobs, done):
    while True:
        item = jobs.get()
        if item is None:
            return
        request_id, job = item
        limiter.acquire(job.size)
        started = time.monotonic()
        try:
            out = ("reply", labeler.label(job.text, job.request))
        except jev.Temporary as e:
            out = ("temporary", e)
        except jev.Rejected as e:
            out = ("rejected", e)
        except jev.Fatal as e:
            out = ("fatal", e)
        except Exception as e:  # a bug in a client must halt the run, not spin it
            out = ("fatal", e)
        done.put((request_id, *out, time.monotonic() - started))


def _pending_originals(db, run):
    """Pending originals in run order, read a page at a time."""
    last = -1
    while True:
        page = db.execute(
            "SELECT review_id, review_text, run_order FROM reviews WHERE run=? AND status='pending' "
            "AND cache_source_id IS NULL AND run_order>? ORDER BY run_order LIMIT 1000",
            (run, last),
        ).fetchall()
        if not page:
            return
        yield from page
        last = page[-1]["run_order"]


def run(
    db, run, labeler, *, ledger, limiter, setup, workers=1, max_hours=None, stop_after=None,
    clock=time.monotonic, stop_event=None, backoff=BACKOFF, accept_guards=(),
):  # fmt: skip
    """Classify until nothing is pending or a stop condition is met. Safe to call again to resume."""
    state.close_crashed_sessions(db, run)
    state.recover_orphans(db, run, ledger=ledger, roles=("enrich",))
    session = state.open_session(db, run, "classify", workers, clock)
    started = last_success = last_beat = clock()

    jobs, done = queue.Queue(), queue.Queue(maxsize=workers * 4)
    threads = [
        threading.Thread(
            target=_worker, args=(labeler, limiter, jobs, done), daemon=True
        )
        for _ in range(workers)
    ]
    for t in threads:
        t.start()

    source = _pending_originals(db, run)
    inflight, retries, later, stuck = {}, [], [], []
    tiebreak = 0
    new_completions = 0
    stopping = ended_how = None
    # An outage must not walk through the file booking a failed call for every review. After this many failures
    # in a row with no success between, only requests already begun are retried; nothing new is admitted.
    since_success, breaker = 0, max(2 * workers, BREAKER_FLOOR)

    def new_job(row, round_number=1):
        """The job for one original, or None after quarantining a review Jev cannot take."""
        try:
            request = jev.build_request(row["review_text"], setup.prompt)
        except jev.TooLarge:
            state.quarantine(db, run, row["review_id"], "request_over_limit")
            return None
        return _Job(
            row["review_id"],
            row["review_text"],
            request,
            len(jev.body_bytes(request)),
            round=round_number,
        )

    def next_job(admit_new):
        nonlocal source, later
        if retries and retries[0][0] <= clock():
            return heapq.heappop(retries)[2]
        while admit_new:
            row = next(source, None)
            if row is None:
                # Everything else is done: give the reviews that failed a whole round one more round.
                if later and not retries and not inflight:
                    source, later = (
                        iter([replace(job, attempt=1, round=2) for job in later]),
                        [],
                    )
                    continue
                return None
            job = row if isinstance(row, _Job) else new_job(row)
            if job is not None:
                return job
        return None

    def finish(
        request_id,
        outcome,
        reply=None,
        error=None,
        status=None,
        seconds=0.0,
        result=None,
        not_sent=False,
    ):
        state.finish_attempt(
            db, request_id, outcome=outcome, seconds=seconds, error=error,
            input_tokens=reply.input_tokens if reply else None,
            output_tokens=reply.output_tokens if reply else None,
            http_status=reply.http_status if reply else status,
            result=result, ledger=ledger, not_sent=not_sent,
        )  # fmt: skip

    def retry(job, delay=0.0):
        nonlocal tiebreak
        tiebreak += 1
        heapq.heappush(retries, (clock() + delay, tiebreak, job))

    while True:
        now = clock()
        if stopping is None:
            if stop_event is not None and stop_event.is_set():
                stopping = "interrupted"
            elif max_hours is not None and now - started >= max_hours * 3600:
                stopping = "time_box"
            elif stop_after is not None and new_completions >= stop_after:
                stopping = "stop_after"

        while stopping is None and len(inflight) < workers:
            job = next_job(since_success < breaker)
            if job is None:
                break
            request_id = uuid.uuid4().hex
            try:
                state.begin_attempt(
                    db, ledger, request_id=request_id, run=run, role="enrich", review_ids=[job.review_id],
                    model=jev.MODEL, label_config=setup.label_config, session_id=session, reserve_tokens=job.size,
                )  # fmt: skip
            except ledger_module.CapReached:
                stopping = "cap"
                break
            inflight[request_id] = job
            jobs.put((request_id, job))

        if not inflight:
            if stopping:
                ended_how = stopping
                break
            if not retries and since_success >= breaker:
                ended_how = "outage"  # what failed stays pending; the same command resumes
                break
            if not retries:
                ended_how = "stuck" if stuck or later else "finished"
                stuck += [job.review_id for job in later]
                break
            time.sleep(
                min(0.05, max(0.0, retries[0][0] - now))
            )  # only delayed retries are left
            continue

        try:
            request_id, kind, payload, seconds = done.get(timeout=0.05)
        except queue.Empty:
            continue
        job = inflight.pop(request_id)

        if kind == "reply" and payload.model != jev.MODEL:
            finish(
                request_id,
                "failed",
                payload,
                f"the response names model {payload.model!r}, not the pinned {jev.MODEL}",
                seconds=seconds,
            )
            stopping = "fatal"
        elif kind == "reply":
            try:
                record = jev.to_record(
                    job.text,
                    payload.answer,
                    features=setup.features,
                    cutoff=setup.cutoff,
                    label_config=setup.label_config,
                )
            except labels.InvalidAnswer as e:
                finish(request_id, "failed", payload, str(e), seconds=seconds)
                if job.invalid_tries == 0:
                    retry(
                        replace(job, invalid_tries=1)
                    )  # the brief's limit: one retry of an invalid answer
                else:
                    state.quarantine(db, run, job.review_id, "invalid_model_output")
            else:
                finish(
                    request_id,
                    "succeeded",
                    payload,
                    seconds=seconds,
                    result={**record, "raw": payload.answer, "model": payload.model},
                )
                new_completions += 1
                last_success = clock()
                since_success = 0
        elif kind == "temporary":
            status = getattr(payload, "status", None)
            finish(
                request_id,
                "failed",
                error=f"{type(payload).__name__}: {payload}"[:500],
                status=status,
                seconds=seconds,
                not_sent=not getattr(payload, "sent", True),
            )
            since_success += 1
            if status == 429:
                limiter.on_429()
            if clock() - last_success >= NO_SUCCESS_SECONDS:
                stopping = stopping or "no_success_60s"
            if job.attempt < ATTEMPTS:
                base = backoff[min(job.attempt - 1, len(backoff) - 1)]
                retry(
                    replace(job, attempt=job.attempt + 1),
                    base * (1 + random.random() / 4),
                )
            else:
                state.return_to_pending(db, run, job.review_id)
                (later if job.round == 1 else stuck).append(
                    job if job.round == 1 else job.review_id
                )
        elif kind == "rejected":
            # The server refused this one request as sent. Trying it again now would get the same answer, so the
            # review waits for the second round and is then listed as stuck. Other reviews go on.
            finish(
                request_id,
                "failed",
                error=f"{type(payload).__name__}: {payload}"[:500],
                status=getattr(payload, "status", None),
                seconds=seconds,
            )
            since_success += 1
            state.return_to_pending(db, run, job.review_id)
            (later if job.round == 1 else stuck).append(job if job.round == 1 else job.review_id)
        else:  # fatal: 401, 402, 403, or a client error we do not understand
            finish(
                request_id,
                "failed",
                error=f"{type(payload).__name__}: {payload}"[:500],
                status=getattr(payload, "status", None),
                seconds=seconds,
            )
            stopping = "fatal"

        if clock() - last_beat >= 1:
            state.heartbeat(db, session, clock)
            last_beat = clock()

    for _ in threads:
        jobs.put(None)
    for t in threads:
        t.join()
    state.close_session(db, session, ended_how, clock)

    counts = dict(
        db.execute(
            "SELECT status, COUNT(*) FROM reviews WHERE run=? GROUP BY status", (run,)
        ).fetchall()
    )
    outcome = Outcome(
        ended_how, counts.get("completed", 0), counts.get("pending", 0), counts.get("quarantined", 0),
        new_completions, session, stuck,
    )  # fmt: skip
    if ended_how == "finished":
        check_guards(db, run, accept=accept_guards)
    return outcome


def check_guards(db, run, *, accept=()):
    """Raise GuardFailed when the labels are degenerate. Returns the guards that failed and were accepted.

    A supplied file has no way past a guard. Any other input may accept one by name, because
    a small or one-sided CSV can truly be all one topic; the acceptance is written to the run.
    """
    total = db.execute("SELECT COUNT(*) FROM results WHERE run=?", (run,)).fetchone()[0]
    if total < GUARD_MIN:
        return []
    top = db.execute(
        "SELECT COUNT(*) AS n FROM results WHERE run=? GROUP BY topic ORDER BY n DESC LIMIT 1",
        (run,),
    ).fetchone()["n"]
    flagged = db.execute(
        "SELECT COALESCE(SUM(needs_review), 0) FROM results WHERE run=?", (run,)
    ).fetchone()[0]
    failed = [
        name
        for name, bad in (
            ("one_topic_over_95", top > 0.95 * total),
            ("needs_review_all_true", flagged == total),
            ("needs_review_all_false", flagged == 0),
        )
        if bad
    ]
    return settle_guards(db, run, failed, accept)


def settle_guards(db, run, failed, accept=()):
    """Raise GuardFailed for the guards that are not accepted; log the ones that are. Returns `failed`."""
    if not failed:
        return []
    row = state.load_run(db, run)
    supplied = prepare.is_supplied(row["input_sha256"])
    blocked = [name for name in failed if supplied or name not in accept]
    if blocked:
        raise GuardFailed(blocked, supplied)
    configs = json.loads(row["configs_json"])
    configs.setdefault("accepted_guards", []).extend({"guard": name, "at": state.now_utc()} for name in failed)
    db.execute("UPDATE runs SET configs_json=? WHERE run=?", (json.dumps(configs, sort_keys=True), run))
    return failed
