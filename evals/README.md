# evals/

Label sheets, the planted cases, and the scripts that score against them. Nothing here enters `grading/` or a business total.

## Label sheets

| File | What it is | State |
|---|---|---|
| `golden_50_labeled.csv` | The golden 50, labeled by hand | Frozen 2026-10-05 before any model saw the texts. Never changes. Scored once |
| `golden_labeling_guide.md` | The guide the labels were written with | |
| `adjudication_sheet.csv`, `adjudication_key.json` | 39 reviews labeled blind, and which were disputed by the outside raters | Frozen 2026-10-05 before any rater answer was shown |
| `dev_150_labeled.csv`, `dev_sets.json` | 150 development reviews; 29 carry hand labels, five of them revised after seeing a model | Both scores are always reported |
| `boycott_60.csv` | 60 real boycott reviews picked by hash: 30 marked `tune`, 30 marked `holdout` | The holdout is scored once |

The golden label columns are never read into a prompt, an example, a cut-off or grouping. Scripts that read them print counts and review IDs only. The columns were opened for reading only after the one score was saved, for the error analysis.

## Scripts

| Script | What it does | Paid? |
|---|---|---|
| `planted_cases.py` | 25 made-up reviews with expected answers written from the contract, scored case by case | Yes, with `--go` |
| `wording_trial.py` | The probe's intent wording against a candidate, on the 4 planted slogans and the `tune` half only. Refuses a held-back row | Yes, with `--go` |
| `holdout_score.py` | The 30 held-back boycott reviews and the 25 planted cases, once, with the frozen wording | Yes, with `--go` |
| `cutoff_table.py` | For each candidate cut-off: what the review flag marks, against every reference side by side | No |
| `cutoff_rows.py` | Labels the cut-off-half reviews the pilot does not cover, once | Yes, with `--go` |
| `score_golden.py` | A run against the golden 50, once, in two readings | No |
| `golden_cases.py` | Lays the saved golden score out case by case; makes no new score | No |
| `compare_check.py` | Changes labels on purpose in a copy and checks the comparison flags each one | No |
| `feature_words.py` | Counts candidate feature words over the full file and drafts `prompts/features-v1.txt` | No |

Every paid call goes through the same spend ledger as the pipeline, so the $35 cap covers it. `--standin` runs a script with the stand-in labeler and saves nothing here.

## Results

- `wording_trial_out.json`: the wording trial of 2026-10-05 (validation log entry 23). The candidate wording met every pass mark and is frozen.
- The 100-review pilot's labels against the development labels and the raters' shared answer: `experiments/2026-10-05/pilot-100/gate_read_out.txt` (validation log entry 25).
- `holdout_score_prompt-v2.json`: the holdout, scored once on 2026-10-05 (validation log entry 26).
- `cutoff_rows_out.jsonl`: the 28 cut-off-half reviews outside the pilot, labeled once (entry 27).
- The golden 50 was scored once, on the full run, on 2026-10-06: `golden_score_full.json`. All three fields right on 30 of 50. It is not scored again.
- `golden_cases_full.csv`: the same score one review to a row, written by `golden_cases.py`, which refuses unless its totals equal the saved score.
- `golden_error_analysis.md`: the 20 reviews where a field differs, read one by one on 2026-10-07 after the score was saved (validation log entry 37).

Earlier measurements, made with throwaway scripts on 2026-10-04, are in `experiments/2026-10-04/README.md` and `docs/validation-log.md`.
