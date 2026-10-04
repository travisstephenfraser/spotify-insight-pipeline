# Experiments, 2026-10-04: tool choice and red team

Throwaway probes run before any pipeline code existed. They are kept as the evidence behind the plan, not as code to reuse. Paths inside the scripts point at the machine and session they ran on.

Numbers below were copied from terminal output at run time. Raw model responses are in the `.jsonl` files.

## tool-choice/

| File | What it is |
|---|---|
| `speed_test.py`, `speed_test_out.txt` | First local Gemma timing on 50 reviews (rows 501 to 550 of `analysis_10000.csv`) |
| `jev_spike.py` | Jev on the 100 pilot reviews, two question styles. `simple.jsonl` and `sentence.jsonl` hold every request and response |
| `gemma_spike.py`, `gemma.jsonl` | Gemma 26B on the same 100 reviews, 10 per request, same definitions |
| `score_spike.py`, `score2.py`, `compare.py`, `compare_out.txt` | Scoring against the 29 hand labels in `evals/dev_150_labeled.csv` |
| `three_tests.py`, `three_tests_out.txt` | Tricky made-up reviews, repeatability, Jev parallel speed |

### Measured

Local Gemma speed, single runs, 50 reviews:

| Model | Requests at once | Seconds per review |
|---|---|---|
| Gemma 4 26B-A4B QAT 4-bit | 1 | 0.57 |
| Gemma 4 26B-A4B QAT 4-bit | 4 | 0.27 |
| Gemma 4 E4B | 1 | 0.75 |
| Gemma 4 E4B | 4 | 0.22 |

Jev (`jev-1.13.0`, direct API, one request at a time) on the 100 pilot reviews:

| Style | Requests | Failed | Median seconds | Input tokens per request | Cost |
|---|---|---|---|---|---|
| Simple, one request per review | 100 | 0 | 0.12 | 926 | $0.00389 |
| Per sentence | 157 | 0 | 0.12 | 871 | $0.00575 |

Gemma 26B on the same 100: 10 requests, 54.4 s, 100 of 100 labeled, one quote not an exact copy, 8,125 input and 5,783 output tokens.

Agreement with the 29 hand labels (after five labels were revised toward the contract, logged in the sheet's notes column):

| Engine | Topic | Intent | Severity | All three |
|---|---|---|---|---|
| Jev simple | 28/29 | 28/29 | 26/29 | 24/29 |
| Jev per sentence | 27/29 | 28/29 | 25/29 | 23/29 |
| Gemma 26B | 25/29 | 29/29 | 26/29 | 23/29 |

Before the revision, against the labels as first written: Jev simple 25, 27, 25 and 21 of 29; Jev per sentence 25, 27, 24 and 20 of 29. Gemma was not scored against the unrevised labels.

Three foundation tests:

- Tricky made-up reviews (25, expected answers written from the contract): Jev 21 right, Gemma 23. Jev missed 2 of 4 injection cases and 2 of 4 slogan cases; Gemma missed one contract-rule topic and one emoji severity.
- Repeatability on the 100 pilot reviews: Jev 0 answers changed. Gemma 1 changed with the same request grouping, 15 changed when regrouped into different requests.
- Jev parallel speed on 500 reviews: 60 requests per second with 8 workers; 78 with 16 workers capped at 80; all 1,000 requests returned 200. Each run lasted under 9 seconds.

Jev spend for the day: about $0.053 (measured $0.0097 and $0.0388 for the first probe and the speed test; the tricky and repeat tests were not logged separately and are about $0.005 by token average).

### Limits

- 29 labels from one person, 11 of them complaints or cancellations. Too few to separate the engines.
- The five revised labels moved toward Jev's answers, which tilts the comparison toward Jev.
- Gemma's prompt was a first draft. One review per request was timed but never scored.
- Expected answers for the made-up reviews were written by the assistant from the contract, not by a second person.

## red-team/

Scripts written by three of the six independent checkers. The full report is `docs/red-team-plan-2026-10-04.html`.

- `checker/harness.py` builds a 30-row synthetic input and 68 submission variants and runs `check_submission.py` on each. `run_output.txt` and `results.json` hold the outcomes. The generated case folders were not kept; rerunning the harness recreates them.
- `stats/` holds the power, bias and sampling calculations with their outputs.
- `data/` holds the full-file measurements (sentence splitting, duplicates, scripts, sample order).
