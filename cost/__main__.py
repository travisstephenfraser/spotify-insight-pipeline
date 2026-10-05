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
    if a.rows is not None:
        plan["rows"] = a.rows
        if a.nonempty is None and a.distinct is None:
            plan["nonempty"], plan["distinct"] = calc.scale_counts(a.rows, inputs["text_volume"])
            plan["scaled"] = True
    for name in ("nonempty", "distinct"):
        if getattr(a, name) is not None:
            plan[name] = getattr(a, name)
    if not plan["distinct"] <= plan["nonempty"] <= plan["rows"]:
        print(f"refused: {plan['rows']} rows cannot hold {plan['nonempty']} nonempty reviews and {plan['distinct']} distinct texts. Give counts that fit together.")
        return 2
    projection = calc.project(measured, **plan)
    Path(a.dir, "report.md").write_text(calc.report(inputs, measured, projection), encoding="utf-8")
    print(f"report written: {Path(a.dir) / 'report.md'}")
    print(f"cold: API ${measured['cold']['api_usd']:.6f}, {measured['cold']['seconds']} s; warm: API ${measured['warm']['api_usd']:.6f}, {measured['warm']['seconds']} s")
    print(f"full run, base case: about ${projection['base']['api_usd']:.2f} (estimate)")
    for warning in projection["warnings"]:
        print(f"WARNING: {warning}")
    return 0


def _state(a):
    return a.state or str(ROOT / ("runs/standin.sqlite" if a.standin else "runs/state.sqlite"))


def write_evidence(a):
    from cost import evidence
    from pipeline import state

    db = state.connect(_state(a))
    try:
        evidence.write(db, a.cold, a.warm, a.dir)
    except evidence.BadPilot as e:
        print(f"refused: {e}. No evidence was written.")
        return 2
    finally:
        db.close()
    print(f"pilot evidence written to {a.dir}. Now: python3 -m cost replay")
    return 0


def pilot(a):
    """Run whatever is left of the pilot. It reads the state file first, so the same command picks up where it stopped."""
    if not a.go and not a.standin:
        print("The pilot sends the 100 reviews of cost_100.csv to Jev and runs every stage: a paid run of well under one cent.")
        print("Nothing was started. Add --go to run it.")
        return 2
    import subprocess

    from cost import evidence
    from pipeline import state

    pilot_csv = str(ROOT / "feed/Final Assignment - Spotify Reviews Dataset/cost_100.csv")
    base = [sys.executable, "-m", "pipeline", "run", "--state", _state(a), "--standin" if a.standin else "--go"]
    commands = {
        "cold_start": [*base, "--run", a.cold, "--new", "--input", pilot_csv, "--workers", "1", "--stop-after", "50"],
        "cold_restart": [*base, "--run", a.cold, "--workers", "1", "--stop-after", "50"],
        "cold_resume": [*base, "--run", a.cold, "--workers", "1"],
        "warm": [*base, "--run", a.warm, "--new", "--input", pilot_csv, "--warm-from", a.cold],
    }

    def look():
        """(steps left, how the cold run's last classify session ended)."""
        db = state.connect(_state(a))
        try:
            last = db.execute(
                "SELECT ended_how FROM sessions WHERE run=? AND stage='classify' ORDER BY session_id DESC LIMIT 1", (a.cold,)
            ).fetchone()
            return evidence.pilot_steps(db, a.cold, a.warm), last["ended_how"] if last else None
        finally:
            db.close()

    done = None
    for _ in range(6):
        try:
            steps, ended = look()
        except evidence.BadPilot as e:
            print(f"refused: {e}")
            return 2
        if not steps:
            break
        step = steps[0]
        if step == done:
            # The step ran and nothing moved: an outage, a server that is down, a memo that failed its check.
            print(f"the pilot stopped at {step.replace('_', ' ')}: the run made no progress (classify last ended as {ended}).")
            print("Nothing was written to the cost folder. Fix the cause and run the same pilot command again; it picks up from here.")
            return 3
        code = subprocess.run(commands[step], cwd=ROOT).returncode
        _, ended = look() if step != "warm" else (None, None)
        if step in ("cold_start", "cold_restart") and ended != "stop_after":
            # Exit code 3 covers every unfinished ending; only a planned stop may count as the planned stop.
            print(f"the pilot's first session ended as {ended}, not at its planned stop. Fix the cause and run the same pilot command again.")
            return 3
        if step == "warm" and code != 0:
            print("the warm pass did not come out clean. Nothing was written to the cost folder.")
            return 3
        done = step
    return write_evidence(a)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m cost", description=(__doc__ or "").split("\n")[0])
    p.add_argument("command", nargs="?", default="replay", choices=("replay", "pilot", "evidence"))
    p.add_argument("--dir", default=str(HERE), help="the folder holding the pilot and rate files (default cost/)")
    p.add_argument("--rows", type=int, help="projected rows in the full file")
    p.add_argument("--nonempty", type=int)
    p.add_argument("--distinct", type=int)
    p.add_argument("--go", action="store_true", help="pilot only: really call the models")
    p.add_argument("--standin", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--state", help="the state file (default runs/state.sqlite; runs/standin.sqlite with --standin)")
    p.add_argument("--cold", default="pilot-cold")
    p.add_argument("--warm", default="pilot-warm")
    a = p.parse_args(argv)
    return {"replay": replay, "pilot": pilot, "evidence": write_evidence}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
