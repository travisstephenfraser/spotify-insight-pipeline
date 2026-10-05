"""THROWAWAY check, not pipeline code. No model call.

Counts the most sentence pieces any review gives under the probe's splitter
(jev_spike.pieces), over the full file. Jev's documented limit is 255 options.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/2026-10-04/tool-choice"))
import jev_spike  # noqa: E402

n = most = over = 0
with open(ROOT / "feed/Final Assignment - Spotify Reviews Dataset/spotify_reviews_18months.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f, strict=True):
        if r["review_text"].strip():
            n += 1
            k = len(jev_spike.pieces(r["review_text"]))
            most = max(most, k)
            over += k > 255
assert n == 660609, n  # known count from manifest.json
print(f"nonempty reviews {n} | most sentence pieces {most} | reviews over 255 pieces {over}")
