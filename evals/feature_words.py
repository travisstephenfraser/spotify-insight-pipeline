"""Draft the feature-word list from counts over the full file. Code only, no model.

For each candidate product feature, count the reviews that hold it (matched the same way
the pipeline matches entities), keep the ones found in at least 100 reviews, and save
every count. Travis reads the list when he gives the go for the 100 gate (spec item 5).

  python3 evals/feature_words.py [--input PATH.csv]
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import features  # noqa: E402

FULL = ROOT / "feed/Final Assignment - Spotify Reviews Dataset/spotify_reviews_18months.csv"
KEEP_AT = 100
CANDIDATES = (
    "shuffle", "smart shuffle", "playlist", "queue", "lyrics", "podcast", "audiobook", "offline", "download",
    "premium", "ads", "search", "library", "liked songs", "discover weekly", "daily mix", "wrapped", "dj", "radio",
    "autoplay", "repeat", "skip", "crossfade", "equalizer", "sleep timer", "car mode", "widget", "lock screen",
    "notification", "bluetooth", "carplay", "android auto", "chromecast", "connect", "canvas", "video", "login",
    "password", "account", "subscription", "free trial", "family plan", "student", "payment", "refund", "update",
    "recommendation",
)  # fmt: skip


def count(path):
    """(reviews read, reviews holding each candidate)."""
    counts, rows = Counter(), 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, strict=True):
            rows += 1
            counts.update(features.find(row["review_text"], CANDIDATES))
    return rows, counts


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--input", default=str(FULL))
    a = ap.parse_args()
    rows, counts = count(a.input)
    assert rows > 0, "the input has no rows"
    # A count that reads itself would show every candidate tied, or none found at all.
    assert len(set(counts.values())) > len(CANDIDATES) // 2, "counts are nearly all equal: the matcher is not reading text"
    ranked = sorted(CANDIDATES, key=lambda c: (-counts[c], c))
    kept = [c for c in ranked if counts[c] >= KEEP_AT]
    out = [
        f"# Reviews holding each candidate feature word, of {rows} reviews in {Path(a.input).name}.",
        f"# An entry matches itself or itself plus s, as a whole word or phrase; a phrase wins over a word inside it.",
        f"# Kept in prompts/features-v1.txt: the {len(kept)} found in at least {KEEP_AT} reviews.",
        *(f"{c}\t{counts[c]}" for c in ranked),
    ]
    (ROOT / "evals/feature_words_out.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    header = [
        "# Feature words, version 1. A draft from counts over the full file (evals/feature_words_out.txt).",
        "# Travis reads this list when he gives the go for the 100 gate. Changing it changes label_config's inputs.",
    ]
    (ROOT / "prompts/features-v1.txt").write_text("\n".join([*header, *kept]) + "\n", encoding="utf-8")
    print(f"{rows} reviews; {len(kept)} of {len(CANDIDATES)} candidates kept")
    for c in ranked:
        print(f"  {counts[c]:>7}  {c}{'' if counts[c] >= KEEP_AT else '   (left out)'}")


if __name__ == "__main__":
    main()
