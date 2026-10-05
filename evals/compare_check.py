"""Check the comparison code: change labels on purpose in a copy and see that each one is flagged.

This tests the code that compares the two engines. It does not test Gemma's ability to
catch Jev's mistakes. It works on a copy of the state file and never touches grading/.

  python3 evals/compare_check.py --state runs/state.sqlite --run NAME [--changes 20]
"""

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import labels, state, verify  # noqa: E402


def check(state_path, run, *, changes=20):
    """Change Jev's topic on `changes` agreeing sampled texts in a copy. Returns what was changed and what was flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        copy_path = Path(tmp) / "copy.sqlite"
        source = sqlite3.connect(state_path)
        target = sqlite3.connect(copy_path)
        with target:
            source.backup(target)
        source.close()
        target.close()

        db = state.connect(copy_path, synchronous="OFF")
        try:
            agreeing = [rid for rid, jev_label, gemma_label in verify._pairs(db, run) if jev_label == gemma_label]
            changed, seen_texts = [], set()
            for rid in agreeing:
                row = db.execute("SELECT text_key FROM reviews WHERE run=? AND review_id=?", (run, rid)).fetchone()
                if row["text_key"] in seen_texts or len(seen_texts) >= changes:
                    continue
                seen_texts.add(row["text_key"])
                topic = db.execute("SELECT topic FROM results WHERE run=? AND text_key=?", (run, row["text_key"])).fetchone()[0]
                other = next(t for t in labels.TOPICS if t != topic)
                db.execute("UPDATE results SET topic=? WHERE run=? AND text_key=?", (other, run, row["text_key"]))
            # Every sampled review that shares a changed text is changed with it.
            for rid, _, _ in verify._pairs(db, run):
                key = db.execute("SELECT text_key FROM reviews WHERE run=? AND review_id=?", (run, rid)).fetchone()[0]
                if key in seen_texts:
                    changed.append(rid)
            flagged = [d["review_id"] for d in verify.report(db, run)["disagreements"] if d["review_id"] in set(changed)]
        finally:
            db.close()
    return {"texts": len(seen_texts), "changed": changed, "flagged": flagged}


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--changes", type=int, default=20)
    a = ap.parse_args()
    result = check(a.state, a.run, changes=a.changes)
    missed = sorted(set(result["changed"]) - set(result["flagged"]))
    print(f"changed on purpose: {len(result['changed'])}; flagged by the comparison: {len(result['flagged'])}")
    if not result["changed"]:
        raise SystemExit("nothing could be changed: no sampled review where the two engines agree")
    if missed:
        raise SystemExit(f"the comparison missed {len(missed)} changed labels: {missed[:5]}")


if __name__ == "__main__":
    main()
