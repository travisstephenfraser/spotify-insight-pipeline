"""THROWAWAY sample picker. No model call. Not pipeline code.

Picks 60 real reviews that contain "boycott", by hash, for the slogan test set.
Distinct texts only, so one repeated slogan cannot fill the sample.
Excludes every golden and development review, by ID and by text.
Writes evals/boycott_60.csv: review_id, review_text, split (tune or holdout).
"""

import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "feed/Final Assignment - Spotify Reviews Dataset"
SEED = "boycott-v1"
N = 60


def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f, strict=True)


def main():
    held = {"golden": list(rows(D / "golden_50_to_label.csv")), "dev": list(rows(ROOT / "evals/dev_150_labeled.csv"))}
    skip_ids = {r["review_id"] for rs in held.values() for r in rs}
    skip_texts = {r["review_text"] for rs in held.values() for r in rs}
    assert len(skip_ids) == 200, len(skip_ids)

    total = hits = 0
    first = {}  # exact text -> first review_id in file order
    for r in rows(D / "spotify_reviews_18months.csv"):
        total += 1
        t = r["review_text"]
        if "boycott" not in t.lower():
            continue
        hits += 1
        if r["review_id"] in skip_ids or t in skip_texts:
            continue
        first.setdefault(t, r["review_id"])
    assert total == 660622, total  # known count from manifest.json
    assert hits > N * 10, f"only {hits} boycott rows; the search is not reading the text"

    ranked = sorted(first, key=lambda t: hashlib.sha256(f"{SEED}:{t}".encode()).hexdigest())[:N]
    out = ROOT / "evals/boycott_60.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["review_id", "review_text", "split"])
        for i, t in enumerate(ranked):
            w.writerow([first[t], t, "tune" if i % 2 == 0 else "holdout"])

    lens = sorted(len(t) for t in ranked)
    print(f"rows read {total} | rows containing 'boycott' {hits} | distinct eligible texts {len(first)}")
    print(f"picked {len(ranked)} (30 tune, 30 holdout) -> {out.relative_to(ROOT)}")
    print(f"picked text length: min {lens[0]}, median {lens[len(lens) // 2]}, max {lens[-1]} characters")


if __name__ == "__main__":
    main()
