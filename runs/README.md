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

No real run has been made yet, so no evidence folder is here.
