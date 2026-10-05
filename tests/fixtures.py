"""Shared test helpers: the supplied checker, the supplied sample files, synthetic CSVs."""

import csv
import importlib.util
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "feed/Final Assignment - Spotify Reviews Dataset"
CHECKER = DATA / "check_submission.py"
SEED = "berkeley-fall-2026-assignment-5-v1"
FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")

AWKWARD = (
    "First line.\nSecond line, after a newline.",
    'She said "it never plays" and I agree, it\'s broken',
    "\U0001f621\U0001f621\U0001f621",
    "None",
    "playback stops " * 2000,
)


@cache
def checker():
    """The instructor's check_submission.py, loaded as a module by path."""
    spec = importlib.util.spec_from_file_location("check_submission", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def supplied(name):
    """Rows of one supplied sample file, read the way the checker reads them."""
    return list(checker().csv_rows(DATA / name))


def synthetic_rows(n, *, empties=1, copies=2):
    """n rows in all: distinct texts first, then copies of the first texts, then empty texts."""
    distinct = n - empties - copies
    assert distinct >= max(copies, 1), "not enough distinct rows to copy from"
    kinds = (
        "The app crashes every time I open playlist {i}",
        "I love the lyrics feature, number {i}",
        "Please add a sleep timer, request {i}",
        "Too many ads, I am cancelling my subscription, case {i}",
        "Cannot log in since update {i}",
    )
    texts = [kinds[i % len(kinds)].format(i=i) for i in range(distinct)]
    texts += texts[:copies]
    texts += ["", "   ", "\n\t"][:empties] if empties <= 3 else [" "] * empties
    return [
        {
            "review_id": f"00000000-0000-4000-8000-{i:012d}",
            "review_text": text,
            "review_rating": str(i % 5 + 1),
            "review_likes": str(i % 3),
            "app_version": "" if i % 4 == 0 else f"8.9.{i % 50}",
            "review_timestamp": f"2024-{i % 12 + 1:02d}-15 10:00:00",
        }
        for i, text in enumerate(texts)
    ]


def write_csv(path, rows, *, fields=FIELDS, bom=False, eol="\n"):
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields), lineterminator=eol, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


RUN_ARGS = dict(
    input_path="input.csv",
    input_sha256="a" * 64,
    seed=SEED,
    verify_seed="verify-v1",
    verify_size=5000,
    sample_seed="sample-v1",
    code_commit="c" * 40,
    code_hash="d" * 64,
    label_config="jev-1.13.0/prompt-v1/schema-v1/cut-0.70",
    hashes={"prompt:enrich-v1.json": "1" * 64, "features": "2" * 64, "splitter": "3" * 64, "cutoff": "0.70"},
    configs={"verify": {"model": "gemma", "prompt": "verify-v1"}},
)


def new_run(db, name="r1", **overrides):
    from pipeline import state

    state.create_run(db, name, **{**RUN_ARGS, **overrides})


class FakeClock:
    """A monotonic clock a test can move by hand."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def prepared_db(directory, rows=None, *, run="r1", verify_size=5000):
    """A state file with one run prepared from a synthetic CSV (20 rows: 3 empty, 4 copies)."""
    from pipeline import prepare, state

    db = state.connect(directory / "state.sqlite", synchronous="OFF")
    path = directory / f"{run}.csv"
    write_csv(path, rows if rows is not None else synthetic_rows(20, empties=3, copies=4))
    with state.tx(db):
        new_run(db, run)
        prepare.prepare(db, run, path, seed=SEED, verify_seed="verify-v1", verify_size=verify_size)
    return db


def write_billing(path, rate_in="0.042", rate_out="0.042"):
    import json

    path.write_text(json.dumps({"jev": {"usd_per_mtok_in": rate_in, "usd_per_mtok_out": rate_out}}))
    return path


def result_for(text, **changes):
    """A valid classify result for `text`, in the shape the classify loop hands to finish_attempt."""
    return {
        "topic": "playback",
        "intent": "complaint",
        "severity": 3,
        "sentiment": -0.5,
        "entities": [],
        "evidence_quote": text.strip(),
        "needs_review": False,
        "min_top_probability": 0.9,
        "raw": {"answers": {}},
        "model": "jev-1.13.0",
        **changes,
    }


PROBE = ROOT / "experiments/2026-10-04/tool-choice"


@cache
def saved_jev():
    """The 100 exchanges saved by the Jev probe on 2026-10-04: request, response, review_id."""
    import json

    lines = (PROBE / "simple.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@cache
def probe_records():
    """What the probe's own scoring script made of those answers: an outside known answer."""
    import sys

    import gc
    import warnings

    sys.path.insert(0, str(PROBE))
    from score_spike import simple_records

    # The probe script leaves its input file for the collector to close. It is saved evidence
    # and is not edited, so its warning is silenced here and nowhere else.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        records = simple_records()
        gc.collect()
    return records


def classified_db(directory, rows=None, *, verify_size=10, labeler=None, cutoff=0.7):
    """A prepared run taken through classify with the stand-in Jev. Returns (db, outcome)."""
    from decimal import Decimal

    from pipeline import classify, jev, ledger, limits, standins

    directory.mkdir(parents=True, exist_ok=True)
    db = prepared_db(directory, rows if rows is not None else synthetic_rows(30, empties=2, copies=5), verify_size=verify_size)
    outcome = classify.run(
        db, "r1", labeler or standins.ReplayJev(PROBE / "simple.jsonl"),
        ledger=ledger.Ledger(db, write_billing(directory / "billing.json"), cap_usd=Decimal("25")),
        limiter=limits.Limiter(requests_per_second=100_000, tokens_per_second=10**9),
        setup=jev.load_setup(ROOT / "prompts", cutoff), backoff=(0, 0, 0),
    )  # fmt: skip
    return db, outcome


def record_for(row, **label):
    """A completed grading record for a source row, valid for the checker."""
    from pipeline import hashing

    base = {
        "topic": "playback", "intent": "complaint", "sentiment": -0.5, "severity": 3, "entities": [],
        "evidence_quote": row["review_text"].strip(), "needs_review": False,
        "label_config": RUN_ARGS["label_config"],
    }  # fmt: skip
    return {"review_id": row["review_id"], "source_sha256": hashing.row_sha(row), "status": "completed", **base, **label}


def reference_for(rows):
    """What the checker's `reference` step would build for these rows, without reading a file."""
    from pipeline import hashing

    return {
        "rows": {r["review_id"]: {"source_sha256": hashing.row_sha(r), "review_text": r["review_text"]} for r in rows},
        "analysis_sha256": "x",
        "ingestion": {},
    }
