# runs/

This folder holds two things.

- **`state.sqlite`** (and its `-wal`, `-shm` and `.lock` files): the state file for every real run. It is not committed; `.gitignore` excludes it.
- **Run evidence**, one folder per run, written by `python3 -m pipeline export --run NAME --evidence runs/NAME`. This is committed, so a reader never needs the state file.

| File | What it holds |
|---|---|
| `run_manifest.json` | Source checksum, code commit and hash, prompts' hashes, model IDs, settings, and the checksum of every exported file |
| `run_log.jsonl` | Every attempted call: role, reviews, model, outcome, usage, status, error, time, session |
| `run_summary.json` | Stage timing, statuses, attempts and failures, usage, spend from the ledger, the spending limit, resume evidence, the checker's result |
| `quarantine.jsonl` | Each quarantined review with its reason and attempt count |
| `verify_predictions.jsonl` | Every verifier prediction |
| `artifacts.jsonl` | Each naming and memo input and output |
| `memo.md` | The memo |

Each folder has its grading export in `grading/`. The repo's root [`grading/`](../grading/run.json) is a copy of `full/grading/`, file for file: it is the one folder the grading contract asks for.

- `pilot-cold/`: the first 100-review pilot of 2026-10-05, with the local model writing the memo.
- `pilot2-cold/`: the pilot run again the same day after the memo model changed.
- `pilot3-cold/`: the pilot of 2026-10-06 with the contract's severity rule, made before the state-file fix of validation log entry 34.
- `pilot4-cold/`: the pilot again an hour later, on the code the full run uses. `cost/` is built from this one.
- `gate-500/`: the 500-review gate.
- `gate-10k/`: the 10,000-review gate of 2026-10-06, the first run with the contract's severity rule in code.
- `full/`: the full file, 660,622 reviews, on the night of 2026-10-06. In `run_full_screenshot.png` and `run_full_text.txt` the laptop's name in the shell prompt is covered (a grey box in the picture, `[laptop]` in the text; validation log entry 42). Its three largest files are gzipped (`records.jsonl.gz`, `calls.jsonl.gz`, `run_log.jsonl.gz`). As for every run, the checker's own outputs (`local-reference.json`, 161.5 MB here, and `self-check.json`) are not committed; `python3 -m pipeline export` writes them again from the state file.
- `demo-100b/`: the 100-review file again on 2026-10-07, stopped by hand after 5.4 seconds and resumed, to put a stop and resume on video (`stop_resume.mov`). 38 completed at the stop, 100 at the end. It is not a gate and nothing is measured from it. An earlier take, `demo-100`, was stopped too early to show and has no folder.

The warm passes made no call and have no folder.
