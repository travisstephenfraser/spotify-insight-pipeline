"""Child process for the crash test: classify with a slow stand-in until the parent kills it."""

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import classify, jev, ledger, limits, standins, state  # noqa: E402


def main(state_path, billing_path, log_path):
    db = state.connect(state_path)
    classify.run(
        db, "r1", standins.ReplayJev(latency=0.2, log_path=log_path),
        ledger=ledger.Ledger(db, billing_path, cap_usd=Decimal("25")),
        limiter=limits.Limiter(requests_per_second=10_000, tokens_per_second=10**9),
        setup=jev.load_setup(ROOT / "prompts", 0.7), workers=4,
    )  # fmt: skip


if __name__ == "__main__":
    main(*sys.argv[1:])
