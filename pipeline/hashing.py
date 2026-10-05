"""Hashes the pipeline relies on. Strings are used exactly as read: no trimming, no normalization."""

import hashlib
import json
from pathlib import Path

# The six source fields, in the grading contract's order.
FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")


def row_sha(row):
    """SHA-256 of the row's six field strings as compact JSON. Same bytes as the checker's row_sha."""
    payload = json.dumps(
        [row[k] for k in FIELDS], ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def order_key(seed, review_id):
    """Sort key for run order and for every seeded sample: lowest first."""
    return hashlib.sha256(f"{seed}:{review_id}".encode("utf-8")).hexdigest()


def text_key(text):
    """Reviews share a result only when their text is byte-identical."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_sha(path):
    """The first 12 hex characters of a file's SHA-256: enough to tell two versions of a prompt apart in a config string."""
    return file_sha(path)[:12]
