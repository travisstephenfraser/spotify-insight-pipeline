"""Which model writes the memo? Three paid Claude models on the pilot's own evidence pack.

Travis asked on 2026-10-05 whether the memo needs a local model at all: it is one call of
about 5,000 input tokens a run. Local Gemma 26B needed four attempts on the pilot. This sends
the same request the pipeline sends (same system prompt, same pack, same retry message) to
each candidate, and judges every answer with the pipeline's own memo check.

The rule for choosing, written before any call:
  1. the cheapest model whose first attempt passes the check in both trials;
  2. if none, the cheapest that passes within two attempts in both trials;
  3. if none, no paid model is chosen.
Whether the chosen memo reads well is Travis's call, not this script's.

    python3 experiments/2026-10-05/memo-model/bakeoff.py            what it would send; no call
    python3 experiments/2026-10-05/memo-model/bakeoff.py --go       paid: 6 to 12 calls, under $1.50
"""

import argparse
import json
import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from pipeline import claude, cli, gemma, memo  # noqa: E402

RUN = "pilot-cold"
TRIALS = 2
CAP_USD = Decimal("1.50")
# USD per million tokens, platform.claude.com/docs/en/about-claude/pricing, checked 2026-10-05.
MODELS = {
    "claude-sonnet-5-5": (Decimal(2), Decimal(10)),
    "claude-opus-5-5": (Decimal(4), Decimal(20)),
    "claude-fable-5-1": (Decimal(10), Decimal(50)),
}


def usd(model, tin, tout):
    rin, rout = MODELS[model]
    return (tin * rin + tout * rout) / 1_000_000


def trial(client, system, user, pack):
    """One run of what the pipeline does: an attempt, then one retry with the problems listed."""
    attempts, problems = [], []
    for n in (1, 2):
        message = user
        if problems:
            message += "\n\nYour previous memo had these problems. Fix every one and return the whole memo again:\n" + "\n".join(f"- {p}" for p in problems)
        started = time.monotonic()
        try:
            reply = client.ask(system, message, memo.SCHEMA, max_tokens=memo.MAX_TOKENS)
            text, problems = reply.data["memo"], None
            problems = memo.check(text, pack)
            row = {"attempt": n, "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens, "model": reply.model, "memo": text, "problems": problems}
        except gemma.InvalidOutput as e:
            problems = [str(e)]
            row = {"attempt": n, "input_tokens": None, "output_tokens": None, "model": None, "memo": None, "problems": problems}
        row["seconds"] = round(time.monotonic() - started, 2)
        attempts.append(row)
        if not problems:
            break
    return attempts


def choose(results):
    """The rule in this file's docstring. `results` maps a model to its trials, each a list of attempts."""
    cheapest_first = sorted(results, key=lambda m: MODELS[m])
    for passes in (lambda t: not t[0]["problems"], lambda t: not t[-1]["problems"]):
        for model in cheapest_first:
            if len(results[model]) == TRIALS and all(passes(t) for t in results[model]):
                return model
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--go", action="store_true")
    a = ap.parse_args(argv)
    db = sqlite3.connect(f"file:{ROOT / 'runs/state.sqlite'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    pack = memo.evidence_pack(db, RUN, per_issue=memo.PER_ISSUE)
    system = Path(memo.PROMPT).read_text(encoding="utf-8").strip("\n")
    user = json.dumps(pack, ensure_ascii=False, sort_keys=True)
    size = len((system + user).encode("utf-8"))
    print(f"request: {size:,} bytes; the local model counted 5,052 input tokens for it")
    if not a.go:
        for model, (rin, rout) in MODELS.items():
            print(f"  {model}: at most ${usd(model, size, claude.Client('', model).output_ceiling(memo.MAX_TOKENS)):.3f} a call if a byte were a token and the output hit its ceiling")
        print("Nothing was sent. Add --go to run it.")
        return 2
    key = cli._env_key("ANTHROPIC_API_KEY")
    results, spent = {}, Decimal(0)
    for model in MODELS:
        client = claude.Client(key, model)
        results[model] = []
        for n in range(TRIALS):
            if spent >= CAP_USD:
                print(f"stopped: ${spent:.4f} spent, the script's cap is ${CAP_USD}")
                break
            attempts = trial(client, system, user, pack)
            for row in attempts:
                row["usd"] = str(usd(model, row["input_tokens"] or 0, row["output_tokens"] or 0))
                spent += Decimal(row["usd"])
                if row["memo"]:
                    (HERE / f"{model}-trial{n + 1}-attempt{row['attempt']}.md").write_text(row["memo"] + "\n", encoding="utf-8")
            results[model].append(attempts)
            first, last = attempts[0], attempts[-1]
            print(f"{model} trial {n + 1}: first attempt {'passes' if not first['problems'] else 'rejected: ' + '; '.join(first['problems'])[:160]}"
                  + ("" if len(attempts) == 1 else f" | retry {'passes' if not last['problems'] else 'rejected'}")
                  + f" | {first['input_tokens']} in, {first['output_tokens']} out, {first['seconds']} s, ${sum(Decimal(r['usd']) for r in attempts):.4f}")
    chosen = choose(results)
    (HERE / "bakeoff_out.json").write_text(json.dumps({"run": RUN, "request_bytes": size, "spent_usd": str(spent), "chosen": chosen, "results": results}, indent=1) + "\n", encoding="utf-8")
    print(f"spent ${spent:.4f}; chosen by the rule: {chosen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
