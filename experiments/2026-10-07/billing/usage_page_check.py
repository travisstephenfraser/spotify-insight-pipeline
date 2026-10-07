"""The TypeSafe usage page after the full run, against the token counts our own call log saved.

Travis read the page on 2026-10-07 at about 12:35 PDT: $20.79, 602,455,939 tokens, 495,150 requests, for
everything this project has sent to Jev. He had read it once before, on 2026-10-05 after the wording trial:
$0.056, 1,640,194 tokens, 1,451 requests. This script asks whether the rise between the two readings is what
the state file logged in between, and which billing rule the dollars fit. It makes no call.

    python3 experiments/2026-10-07/billing/usage_page_check.py           # from jev_calls_by_run.json, in any clone
    python3 experiments/2026-10-07/billing/usage_page_check.py --dump    # write that file again from runs/state.sqlite, read-only

It raises, and prints nothing as a result, when no run boundary matches the page exactly or when the dollars fit
both billing rules or neither.
"""

import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SAVED = HERE / "jev_calls_by_run.json"
RATE_IN = (
    Decimal("0.042") / 1_000_000
)  # dollars per input token, docs.typesafe.ai/models, checked 2026-10-04

# Read from the usage page by Travis. The first figure has three decimals, the second two.
FIRST = {
    "usd": Decimal("0.056"),
    "tokens": 1_640_194,
    "requests": 1_451,
    "half_step": Decimal("0.0005"),
}
SECOND = {
    "usd": Decimal("20.79"),
    "tokens": 602_455_939,
    "requests": 495_150,
    "half_step": Decimal("0.005"),
}
FIRST_READING_BOOKED = (
    "2026-10-06T00:47:41"  # when the ledger row for the first reading was written, UTC
)

# The wording trial as the 2026-10-05 check counted it (validation log entries 23 and 24). The known answer for the split below.
TRIAL = {"calls": 68, "input_tokens": 64_710, "output_tokens": 14_535}


class Mismatch(Exception):
    pass


def dump():
    """Every Jev call in the state file, totalled by run in time order. The calls before the first reading are their own row."""
    db = sqlite3.connect(f"file:{ROOT / 'runs/state.sqlite'}?mode=ro", uri=True)
    rows = db.execute(
        "SELECT run, started_utc < ? AS before_first_reading, COUNT(*), SUM(outcome='succeeded'), SUM(outcome='failed'), "
        "SUM(COALESCE(input_tokens,0)), SUM(COALESCE(output_tokens,0)), MIN(started_utc), MAX(started_utc) "
        "FROM calls WHERE model LIKE 'jev%' GROUP BY run, before_first_reading ORDER BY MIN(started_utc)",
        (FIRST_READING_BOOKED,),
    ).fetchall()
    keys = (
        "run",
        "before_first_reading",
        "calls",
        "succeeded",
        "failed",
        "input_tokens",
        "output_tokens",
        "first_utc",
        "last_utc",
    )
    groups = [dict(zip(keys, row)) for row in rows]
    for g in groups:
        g["before_first_reading"] = bool(g["before_first_reading"])
    SAVED.write_text(json.dumps(groups, indent=1) + "\n", encoding="utf-8")
    return groups


def check(groups):
    before = [g for g in groups if g["before_first_reading"]]
    if [{k: g[k] for k in TRIAL} for g in before] != [TRIAL]:
        raise Mismatch(
            f"the calls logged before the first reading are not the wording trial: {before}"
        )
    after = [g for g in groups if not g["before_first_reading"]]
    rise = {
        "requests": SECOND["requests"] - FIRST["requests"],
        "tokens": SECOND["tokens"] - FIRST["tokens"],
    }

    # The page can lag, so the newest runs may not be on it yet. Only a boundary between runs, in time order, is tried.
    fits = []
    for n in range(len(after) + 1):
        on_page = after[:n]
        succeeded = sum(g["succeeded"] for g in on_page)
        tokens = sum(g["input_tokens"] + g["output_tokens"] for g in on_page)
        if (succeeded, tokens) == (rise["requests"], rise["tokens"]):
            fits.append(n)
    if len(fits) != 1:
        raise Mismatch(
            f"{len(fits)} run boundaries match the rise of {rise['requests']:,} requests and {rise['tokens']:,} tokens; one was expected"
        )
    on_page, not_yet = after[: fits[0]], after[fits[0] :]

    new_input = sum(g["input_tokens"] for g in on_page)
    input_only = FIRST["usd"] + new_input * RATE_IN
    every_token = SECOND["tokens"] * RATE_IN
    slack = FIRST["half_step"] + SECOND["half_step"]  # both readings are rounded
    a_fits = abs(input_only - SECOND["usd"]) <= slack
    b_fits = abs(every_token - SECOND["usd"]) <= slack
    if a_fits == b_fits:
        raise Mismatch(
            f"the dollars fit {'both billing rules' if a_fits else 'neither billing rule'}: {input_only:.4f} and {every_token:.4f} against {SECOND['usd']}"
        )
    return {
        "rise": rise,
        "on_page": on_page,
        "not_yet": not_yet,
        "failed_attempts_on_page_runs": sum(g["failed"] for g in on_page),
        "new_input_tokens": new_input,
        "input_only_usd": input_only,
        "every_token_usd": every_token,
        "input_only_fits": a_fits,
        "next": {
            "requests": SECOND["requests"] + sum(g["succeeded"] for g in not_yet),
            "tokens": SECOND["tokens"]
            + sum(g["input_tokens"] + g["output_tokens"] for g in not_yet),
            "usd": input_only + sum(g["input_tokens"] for g in not_yet) * RATE_IN,
        },
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    groups = (
        dump() if "--dump" in argv else json.loads(SAVED.read_text(encoding="utf-8"))
    )
    r = check(groups)
    print(
        f"usage page, 2026-10-05: ${FIRST['usd']}, {FIRST['tokens']:,} tokens, {FIRST['requests']:,} requests"
    )
    print(
        f"usage page, 2026-10-07: ${SECOND['usd']}, {SECOND['tokens']:,} tokens, {SECOND['requests']:,} requests"
    )
    print(
        f"rise between the readings: {r['rise']['requests']:,} requests, {r['rise']['tokens']:,} tokens"
    )
    print("logged by the state file after the first reading, in time order:")
    for g in r["on_page"]:
        print(
            f"  {g['run']:<12} {g['succeeded']:>7,} succeeded, {g['failed']:>2} failed, {g['input_tokens'] + g['output_tokens']:>11,} tokens"
        )
    print(f"  these sum to exactly the rise: {sum(g['succeeded'] for g in r['on_page']):,} succeeded requests and "
          f"{sum(g['input_tokens'] + g['output_tokens'] for g in r['on_page']):,} tokens, input plus output")  # fmt: skip
    print(
        f"  the {r['failed_attempts_on_page_runs']} failed attempts in these runs are not on the page"
    )
    for g in r["not_yet"]:
        print(
            f"not on the page yet: {g['run']}, {g['succeeded']} requests, last sent {g['last_utc'][:19]} UTC"
        )
    print("billing rule:")
    print(
        f"  only input tokens billed: ${r['input_only_usd']:.4f}; the page shows ${SECOND['usd']}: fits {r['input_only_fits']}"
    )
    print(
        f"  every token billed: ${r['every_token_usd']:.4f}: fits {not r['input_only_fits']}"
    )
    print(
        f"prediction for the next reading: {r['next']['requests']:,} requests, {r['next']['tokens']:,} tokens, ${r['next']['usd']:.2f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
