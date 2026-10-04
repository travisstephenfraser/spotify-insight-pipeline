"""Shared loader. Read-only against the dataset folder."""

import csv
import sys

csv.field_size_limit(sys.maxsize)

DATA = "/Users/travis/Developer/pepeclass/assign5-multiagent/feed/Final Assignment - Spotify Reviews Dataset"
FULL = DATA + "/spotify_reviews_18months.csv"
FIELDS = [
    "review_id",
    "review_text",
    "review_rating",
    "review_likes",
    "app_version",
    "review_timestamp",
]


def load(path=FULL):
    """Return (header, rows) where rows are lists of strings, exactly as csv parses them."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        rows = list(r)
    return header, rows


def trunc(s, n=80):
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return s[:n] + ("..." if len(s) > n else "")
