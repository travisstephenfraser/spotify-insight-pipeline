"""The cost and runtime calculator.

  python3 -m cost                      offline replay (the default): reads saved files only, needs no key
  python3 -m cost replay --rows N      the same, with another projected row count
  python3 -m cost pilot --go           the paid 100-review pilot: cold run, warm run, then the evidence files

Importing or opening this starts nothing. The pilot makes real calls only when asked by name with --go.
"""

import argparse
import sys
from pathlib import Path

from cost import calc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def replay(a):
    try:
        inputs = calc.load(a.dir)
    except calc.NoPilot as e:
        print(f"{e}.")
        print("There is no pilot to replay yet, and no number is made up in its place. The pilot is: python3 -m cost pilot --go")
        return 1
    measured = calc.measured(**inputs)
    plan = calc.projection_inputs(inputs)
    for name in ("rows", "nonempty", "distinct"):
        if getattr(a, name) is not None:
            plan[name] = getattr(a, name)
    projection = calc.project(measured, **plan)
    Path(a.dir, "report.md").write_text(calc.report(inputs, measured, projection), encoding="utf-8")
    print(f"report written: {Path(a.dir) / 'report.md'}")
    print(f"cold: API ${measured['cold']['api_usd']:.6f}, {measured['cold']['seconds']} s; warm: API ${measured['warm']['api_usd']:.6f}, {measured['warm']['seconds']} s")
    print(f"full run, base case: about ${projection['base']['api_usd']:.2f} (estimate)")
    for warning in projection["warnings"]:
        print(f"WARNING: {warning}")
    return 0


def pilot(a):
    if not a.go and not a.standin:
        print("The pilot sends the 100 reviews of cost_100.csv to Jev and runs every stage: a paid run of well under one cent.")
        print("Nothing was started. Add --go to run it.")
        return 2
    import subprocess

    from cost import evidence
    from pipeline import state

    pilot_csv = ROOT / "feed/Final Assignment - Spotify Reviews Dataset/cost_100.csv"
    mode = ["--standin"] if a.standin else ["--go"]
    base = [sys.executable, "-m", "pipeline", "run", "--state", a.state, *mode]
    steps = (
        ([*base, "--run", a.cold, "--new", "--input", str(pilot_csv), "--workers", "1", "--stop-after", "50"], 3),
        ([*base, "--run", a.cold], 0),
        ([*base, "--run", a.warm, "--new", "--input", str(pilot_csv), "--warm-from", a.cold], 0),
    )
    for command, expected in steps:
        done = subprocess.run(command, cwd=ROOT)
        if done.returncode != expected:
            print(f"the pilot stopped: a step ended with code {done.returncode}, expected {expected}. Nothing was written to {a.dir}.")
            return 3
    db = state.connect(a.state)
    try:
        evidence.write(db, a.cold, a.warm, a.dir)
    finally:
        db.close()
    print(f"pilot evidence written to {a.dir}. Now: python3 -m cost replay")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m cost", description=(__doc__ or "").split("\n")[0])
    p.add_argument("command", nargs="?", default="replay", choices=("replay", "pilot"))
    p.add_argument("--dir", default=str(HERE), help="the folder holding the pilot and rate files (default cost/)")
    p.add_argument("--rows", type=int, help="projected rows in the full file")
    p.add_argument("--nonempty", type=int)
    p.add_argument("--distinct", type=int)
    p.add_argument("--go", action="store_true", help="pilot only: really call the models")
    p.add_argument("--standin", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--state", default=str(ROOT / "runs/state.sqlite"))
    p.add_argument("--cold", default="pilot-cold")
    p.add_argument("--warm", default="pilot-warm")
    a = p.parse_args(argv)
    return replay(a) if a.command == "replay" else pilot(a)


if __name__ == "__main__":
    sys.exit(main())
