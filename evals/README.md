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

The golden label columns are never read into a prompt, an example, a cut-off or grouping. Scripts that read them print counts and review IDs only.

## Scripts

| Script | What it does | Paid? |
|---|---|---|
| `planted_cases.py` | 25 made-up reviews with expected answers written from the contract, scored case by case | Yes, with `--go` |
| `wording_trial.py` | The probe's intent wording against a candidate, on the 4 planted slogans and the `tune` half only. Refuses a held-back row | Yes, with `--go` |
| `holdout_score.py` | The 30 held-back boycott reviews and the 25 planted cases, once, with the frozen wording | Yes, with `--go` |
| `cutoff_table.py` | For each candidate cut-off: what the review flag marks, against every reference side by side | No |
| `score_golden.py` | A run against the golden 50, once, in two readings | No |
| `compare_check.py` | Changes labels on purpose in a copy and checks the comparison flags each one | No |
| `feature_words.py` | Counts candidate feature words over the full file and drafts `prompts/features-v1.txt` | No |

Every paid call goes through the same spend ledger as the pipeline, so the $35 cap covers it. `--standin` runs a script with the stand-in labeler and saves nothing here.

## Results

None from a real model with this code yet. Earlier measurements, made with throwaway scripts on 2026-10-04, are in `experiments/2026-10-04/README.md` and `docs/validation-log.md`.
