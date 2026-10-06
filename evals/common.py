"""Shared by the evaluation scripts: the label sheets, the two halves, and paid calls through the ledger."""

import argparse
import contextlib
import csv
import hashlib
import sys
import tempfile
import time
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from pipeline import jev, labels, ledger, limits, standins, state  # noqa: E402

RUN = "evals"  # eval calls are logged under this name and are never exported to grading/
FIELDS = ("topic", "intent", "severity")
ATTEMPTS = 4


def _sheet(name, encoding="utf-8-sig"):
    with open(ROOT / "evals" / name, encoding=encoding, newline="") as f:
        return list(csv.DictReader(f))


def _labels(rows):
    return {
        r["review_id"]: {"topic": r["topic"].strip(), "intent": r["intent"].strip(), "severity": int(r["severity"])}
        for r in rows
        if r["intent"].strip()
    }


def boycott(split):
    """The 60 real boycott reviews: 30 marked `tune` to tune on, 30 marked `holdout` to score once."""
    return [{"id": r["review_id"], "text": r["review_text"], "split": r["split"]} for r in _sheet("boycott_60.csv") if r["split"] == split]


def dev_labels():
    """The 29 development labels Travis wrote on 2026-10-04 (five revised after seeing Jev)."""
    return _labels(_sheet("dev_150_labeled.csv"))


def adjudication_labels():
    """The 39 blind labels of 2026-10-05, frozen before any rater answer was shown."""
    return _labels(_sheet("adjudication_sheet.csv"))


def rater_labels(effort="medium"):
    """(Fable's labels, Astra's labels) by review ID, from the saved outside-rater answers."""
    sys.path.insert(0, str(ROOT / "experiments/2026-10-04/outside-raters"))
    import raters

    return tuple(
        {r["id"]: {f: r["labels"][f] for f in FIELDS} for r in raters.saved(provider, effort) if r["labels"]}
        for provider in ("anthropic", "openai")
    )


def shared_rater_labels():
    """Reviews where the two raters give the same topic, intent and severity."""
    fable, astra = rater_labels()
    return {k: v for k, v in fable.items() if astra.get(k) == v}


def disputed_by_raters():
    fable, astra = rater_labels()
    return {k for k, v in fable.items() if k in astra and astra[k] != v}


def halves():
    """(wording half, cut-off half): the 121 development rows not labeled earlier, split by hash (spec item 24)."""
    earlier = set(dev_labels())
    rest = [r["review_id"] for r in _sheet("dev_150_labeled.csv") if r["review_id"] not in earlier]
    rest.sort(key=lambda i: hashlib.sha256(f"halves-v1:{i}".encode()).hexdigest())
    cut = (len(rest) + 1) // 2
    return rest[:cut], rest[cut:]


class Paid:
    """Labeler calls for an evaluation, each one through the spend ledger and the call log.

    `ask(item_id, text)` returns the record, or {"invalid": reason} for an answer that fails
    validation. The ledger's CapReached is raised before anything is sent.
    """

    def __init__(self, db, spend, labeler, setup, purpose, *, limiter=None, clock=time.monotonic):
        self.db, self.ledger, self.labeler, self.setup = db, spend, labeler, setup
        self.limiter = limiter or limits.Limiter(requests_per_second=5)
        self.clock = clock
        # An eval call a killed process left open would stay reserved for good: close it and keep its reservation as spent.
        state.recover_orphans(db, RUN, ledger=spend, roles=("enrich",))
        self.session = state.open_session(db, RUN, f"eval: {purpose}", 1, clock)

    def ask(self, item_id, text):
        request = jev.build_request(text, self.setup.prompt)
        size = len(jev.body_bytes(request))
        last = None
        for _ in range(ATTEMPTS):
            request_id = uuid.uuid4().hex
            state.begin_attempt(
                self.db, self.ledger, request_id=request_id, run=RUN, role="enrich", review_ids=[item_id], model=jev.MODEL,
                label_config=self.setup.label_config, session_id=self.session, reserve_tokens=size,
            )  # fmt: skip
            self.limiter.acquire(size)
            sent = time.monotonic()

            def finish(outcome, reply=None, error=None, status=None):
                state.finish_attempt(
                    self.db, request_id, outcome=outcome, seconds=time.monotonic() - sent, error=error,
                    input_tokens=reply.input_tokens if reply else None, output_tokens=reply.output_tokens if reply else None,
                    http_status=reply.http_status if reply else status, ledger=self.ledger,
                )  # fmt: skip

            try:
                reply = self.labeler.label(text, request)
            except jev.Temporary as e:
                finish("failed", error=str(e)[:500], status=e.status)
                last = e
                continue
            except jev.Rejected as e:
                # The provider refused this one request as sent. The same request would be refused again, so the
                # item has no answer and the script goes on to the next.
                finish("failed", error=str(e)[:500], status=e.status)
                return {"invalid": f"the provider refused this request: {e}"}
            except jev.Fatal as e:
                finish("failed", error=str(e)[:500], status=e.status)
                raise
            if reply.model != jev.MODEL:
                finish("failed", reply, f"the response names model {reply.model!r}, not the pinned {jev.MODEL}")
                raise jev.Fatal(f"the response names model {reply.model!r}")
            try:
                record = jev.to_record(
                    text, reply.answer, features=self.setup.features, cutoff=self.setup.cutoff, label_config=self.setup.label_config
                )
            except labels.InvalidAnswer as e:
                finish("failed", reply, str(e)[:500])
                return {"invalid": str(e)}
            finish("succeeded", reply)
            return record
        raise last

    def close(self):
        state.close_session(self.db, self.session, "finished", self.clock)


def add_arguments(ap):
    ap.add_argument("--go", action="store_true", help="really call Jev; without it nothing is sent")
    ap.add_argument("--standin", action="store_true", help="use the stand-in labeler: no network, no cost")
    ap.add_argument("--state", default=str(ROOT / "runs/state.sqlite"), help="the state file whose ledger these calls are charged to")
    ap.add_argument("--prompt-file", default=jev.PROMPT_FILE)
    ap.add_argument("--cutoff", type=float, default=0.70)
    ap.add_argument("--cap", default=str(ledger.CAP_USD))


@contextlib.contextmanager
def session(a, purpose, prompt_file=None):
    """A Paid caller for a script's arguments, or None (with a message) when neither --go nor --standin was given."""
    if not (a.go or a.standin):
        print("Nothing was sent. This script makes paid calls to Jev: add --go to run it, or --standin for a dry run.")
        yield None
        return
    setup = jev.load_setup(ROOT / "prompts", a.cutoff, prompt_name=prompt_file or a.prompt_file)
    if a.standin:
        state_path = Path(tempfile.mkdtemp(prefix="standin-evals-")) / "state.sqlite"  # never the real ledger
        labeler = standins.ReplayJev()
    else:
        from pipeline import cli

        state_path = Path(a.state)
        labeler = jev.Client(cli._env_key("TYPESAFE_API_KEY"))
    lock = state.RunLock(state_path)
    lock.acquire()
    db = state.connect(state_path)
    try:
        if not a.standin:
            from pipeline import cli

            cli._one_kind_per_state_file(db, standin=False)  # the cap must not split across two ledgers
        spend = ledger.Ledger(db, ROOT / "pipeline/billing.json", cap_usd=Decimal(a.cap))
        if not a.standin and not db.execute("SELECT 1 FROM ledger WHERE kind='opening'").fetchone():
            spend.opening(*cli.OPENING_SPEND)  # the probes made before the ledger existed count against the cap
        paid = Paid(db, spend, labeler, setup, purpose)
        try:
            yield paid
        finally:
            paid.close()
            kind = "stand-in spend, made up" if a.standin else "Jev spend so far"
            print(f"{kind}: ${paid.ledger.spent_usd():.4f} of ${a.cap}")
    finally:
        db.close()
        lock.release()
