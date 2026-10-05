"""Child process for the verify crash test: verify with a slow stand-in until the parent kills it."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import standins, state, verify  # noqa: E402

if __name__ == "__main__":
    db = state.connect(sys.argv[1])
    verify.run(db, "r1", standins.StandinGemma(latency=0.3))
