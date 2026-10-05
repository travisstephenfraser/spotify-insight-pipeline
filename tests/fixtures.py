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
