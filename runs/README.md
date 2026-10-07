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

Each folder has its grading export in `grading/`.

- `pilot-cold/`: the first 100-review pilot of 2026-10-05, with the local model writing the memo.
- `pilot2-cold/`: the pilot run again the same day after the memo model changed.
- `pilot3-cold/`: the pilot of 2026-10-06 on the final code, with the contract's severity rule. `cost/` is built from this one.
- `gate-500/`: the 500-review gate.
- `gate-10k/`: the 10,000-review gate of 2026-10-06, the first run with the contract's severity rule in code.

The warm passes made no call and have no folder.
