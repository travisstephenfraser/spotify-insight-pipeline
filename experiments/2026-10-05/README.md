# Experiments, 2026-10-05

Throwaway scripts and saved output, not pipeline code. No model call was made on this day.

Numbers below were copied from terminal output at run time.

## labels/

The two hand-labeled files were imported from Numbers, frozen, and the blind sheet was scored. Validation log entries 16 and 18.

| File | What it is |
|---|---|
| `import_numbers.py` | Exports a copy of a Numbers document as CSV, fills the repo CSV by review ID, and runs the format check. It prints row numbers, column names and counts, never a label value. Review text always comes from the repo. It writes nothing unless the check is clean |
| `score_adjudication.py` | Scores `evals/adjudication_sheet.csv` against the two outside raters. It refuses a sheet that is not committed |
| `score_adjudication_out.txt` | The score as printed, row by row, with the second reading |
| `rule_check.py`, `rule_check_out.txt` | Counts hand labels that the contract's fixed severity rule would change. Counts only for the golden file |

Freeze record:

| File | Commit | SHA-256 |
|---|---|---|
| `evals/adjudication_sheet.csv` | `634c05c` | `47ce41508e911455179a983f12f9e105c31129fae0450f790b6f46bf798e9274` |
| `evals/golden_50_labeled.csv` | `dcab9ff` | `b9d25cf271d921ec0a2545d2ca4a3ad8655e3b7056ac492b5a0458c5e4f2b79d` |

The blind sheet, 39 reviews labeled by Travis without seeing a rater's answer:

| Rows | Result |
|---|---|
| 15 where the raters agree | His label equals their shared answer on all three fields for 4 (topic 12, intent 12, severity 5) |
| 23 where the raters differ | His label equals Fable's on 3, Astra's on 3, neither on 17 |
| 38 real reviews, Fable against him | 7 on all three (topic 26, intent 31, severity 16) |
| 38 real reviews, Astra against him | 7 on all three (topic 23, intent 32, severity 13) |
| Planted case R1 | Expected `playback`, `complaint`, 3. His label: `billing`, `complaint`, 2 |

All 8 boycott reviews he called `unclear` carry severity 2, where the contract's severity 1 covers "neutral/unclear content". Four of the 11 agreed-check differences are this alone. The labels stay as frozen.

Ruling by Travis the same day: every score against hand labels is shown two ways, as written and with the contract's fixed severity rule applied to the hand labels by code (intent `unclear`, `praise` or `request` means severity 1).

| Measure | As written | With the rule |
|---|---|---|
| Labels the rule changes: blind sheet, development sheet, golden 50 | | 8 of 39, 0 of 29, 4 of 50 |
| Agreed checks, all three fields | 4 of 15 | 8 of 15 |
| Agreed checks, severity | 5 of 15 | 8 of 15 |
| Disputed rows: Fable's, Astra's, neither | 3, 3, 17 | 4, 5, 14 |
| Fable against him, all three and severity | 7 and 16 of 38 | 12 and 20 of 38 |
| Astra against him, all three and severity | 7 and 13 of 38 | 13 and 19 of 38 |

Tests of the two scripts ran on made-up labels in a scratch folder and are not saved here. What they showed is in the validation log.
