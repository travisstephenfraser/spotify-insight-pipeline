"""THROWAWAY checks of two claims in the outside review of the implementation plan. No model call.

Claim 1: of the four planted slogan cases, only two expect `unclear`.
Claim A: the saved Jev answers name the sentence question `evidence`, never `quote`,
and their tone scores are mostly fractional.
"""

import ast
import json
from collections import Counter
from pathlib import Path

T = Path(__file__).resolve().parents[3] / "experiments/2026-10-04/tool-choice"


def main():
    tree = ast.parse((T / "three_tests.py").read_text(encoding="utf-8"))
    cases = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "CASES"
    )
    slogans = [c for c in cases if c[1] == "slogan"]
    assert len(cases) == 25 and len(slogans) == 4, (len(cases), len(slogans))
    print("planted slogan cases, accepted intent:")
    for cid, _, text, _, intents, _ in slogans:
        print(f"  {cid}: {sorted(intents)}  {text!r}")
    print("accepted intents across the four:", dict(Counter(i for c in slogans for i in c[4])))

    rows = [json.loads(line) for line in (T / "simple.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 100, len(rows)
    extra = Counter(k for r in rows for k in r["response"]["answers"] if k not in ("topic", "intent", "severity", "tone"))
    print("saved Jev answers: 100; fifth question by name:", dict(extra))
    scores = [r["response"]["answers"]["tone"]["score"] for r in rows]
    print(
        "tone scores: types", dict(Counter(type(s).__name__ for s in scores)),
        "| fractional", sum(float(s) != int(s) for s in scores),
        "| lowest", min(scores), "| highest", max(scores),
    )


if __name__ == "__main__":
    main()
