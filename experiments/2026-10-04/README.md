# Experiments, 2026-10-04: tool choice and red team

Throwaway probes run before any pipeline code existed. They are kept as the evidence behind the plan, not as code to reuse. Eight scripts named the repo by its full path on the machine they ran on. On 2026-10-07 that one line in each was changed to find the repo from the script's own place; it gives the same folder there, and nothing else in them was touched.

Numbers below were copied from terminal output at run time. Raw model responses are in the `.jsonl` files.

## tool-choice/

| File | What it is |
|---|---|
| `speed_test.py`, `speed_test_out.txt` | First local Gemma timing on 50 reviews (rows 501 to 550 of `analysis_10000.csv`) |
| `jev_spike.py` | Jev on the 100 pilot reviews, two question styles. `simple.jsonl` and `sentence.jsonl` hold every request and response |
| `gemma_spike.py`, `gemma.jsonl` | Gemma 26B on the same 100 reviews, 10 per request, same definitions |
| `score_spike.py`, `score2.py`, `compare.py`, `compare_out.txt` | Scoring against the 29 hand labels in `evals/dev_150_labeled.csv` |
| `three_tests.py`, `three_tests_out.txt` | Tricky made-up reviews, repeatability, Jev parallel speed |
| `flag_probe.py`, `flag_probe_out.txt` | Read-only look at Jev's top probabilities in `simple.jsonl` against its mistakes and its disagreements with Gemma. No model call |

### Measured

Local Gemma speed, single runs, as printed in `speed_test_out.txt`:

| Model | Reviews per request | Requests at once | Reviews | Seconds per review |
|---|---|---|---|---|
| Gemma 4 26B-A4B QAT 4-bit | 1 | 1 | 20 | 0.64 |
| Gemma 4 26B-A4B QAT 4-bit | 10 | 1 | 20 | 0.56 |
| Gemma 4 26B-A4B QAT 4-bit | 50 | 1 | 50 | 0.57 |
| Gemma 4 26B-A4B QAT 4-bit | 10 | 4 | 40 | 0.27 |
| Gemma 4 E4B | 1 | 1 | 20 | 0.76 |
| Gemma 4 E4B | 10 | 1 | 20 | 0.70 |
| Gemma 4 E4B | 50 | 1 | 50 | 0.79 |
| Gemma 4 E4B | 10 | 4 | 40 | 0.22 |

Corrected 2026-10-04 after the second independent review. The table used to give 0.57 and 0.27 for 26B under "requests at once" without saying those runs sent 50 and 10 reviews per request. One review per request with four workers was never timed.

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

## outside-raters/

Two strong models from other makers label reviews blind, as third-party raters: Claude Fable 5.1 (`claude-fable-5-1`) and GPT-6 Astra (`gpt-6-astra`). Approved by Travis on 2026-10-04 with a hard cap of $10 per provider. Run the same day in three steps, each with his go: 10 reviews at low effort, the same 10 at medium, then all 235 at medium.

| File | What it is |
|---|---|
| `pick_boycott.py` | Picks 60 real reviews containing "boycott" by hash (distinct texts, no golden or development review) and writes `evals/boycott_60.csv`, half marked `tune` and half `holdout`. No model call. It read 660,622 rows and found 3,484 containing "boycott", the same count the red team reported |
| `raters.py` | Sends one review per request with the contract's label section copied word for word. Dry run by default; paid calls need `--go` and `--effort`. Stops at the cap, and stops after ten rows if the projected total would pass it. No fallback model, so a refusal is saved as a refusal |
| `anthropic_low.jsonl`, `anthropic_medium.jsonl`, `openai_low.jsonl`, `openai_medium.jsonl` | Every request's outcome: the labels, the usage, the cost and the full response |
| `compare_raters.py`, `compare_raters_out.txt` | Rater against rater, raters against the 29 hand labels and the planted cases, and the blind sheet for Travis. No model call |

What they rate: the 150 development reviews, the 60 boycott reviews and the 25 made-up tricky reviews. The golden 50 texts are rated later, only after Travis's labels are frozen.

Rates used (USD per million tokens, checked 2026-10-04): both models $10 input and $50 output; Fable 5.1 cache read $0.25 and cache write $12.50; Astra cached input $1. Thinking tokens are billed as output on both, so the cost depends on the effort setting.

Test batches, 2026-10-04, approved by Travis: the same 10 reviews to each rater, first at low effort, then at medium. Saved per setting in `anthropic_low.jsonl`, `anthropic_medium.jsonl`, `openai_low.jsonl` and `openai_medium.jsonl`. Spend at every setting counts toward the cap.

| Rater | Effort | Labeled | Refused | Cost per review | Projected for 285 | Output tokens per answer | Median seconds |
|---|---|---|---|---|---|---|---|
| `claude-fable-5-1` | low | 10 of 10 | 0 | $0.0041 | $1.16 | 31 | 3.1 |
| `claude-fable-5-1` | medium | 10 of 10 | 0 | $0.0051 | $1.50 | 87 | 3.2 |
| `gpt-6-astra` | low | 10 of 10 | 0 | $0.0097 | $2.78 | 43 | 2.5 |
| `gpt-6-astra` | medium | 10 of 10 | 0 | $0.0119 | $3.49 | 86 | 2.3 |

- The two raters gave identical topic, intent and severity on 7 of the 10 at low effort and 7 of 10 at medium.
- Fable gave the same answer at both settings on all 10. Astra changed 1 of 10: a review that opens "Boycotting this app due to" went from `cancellation` to `unclear`.
- Neither model spent many tokens thinking at either setting.
- Fable read its instructions from cache (about 1,250 to 1,380 cached tokens per request); Astra reported no cached input.
- Ten reviews is too few to say which setting labels better.

Full run, 2026-10-04, medium effort, approved by Travis. `compare_raters.py` reads the saved answers (no model call); its output is `compare_raters_out.txt`.

| | Fable 5.1 | Astra 6 |
|---|---|---|
| Labeled, of 235 | 235 | 235 |
| Refused | 0 | 0 |
| Spent, every setting, of the $10 cap | $1.12 | $2.77 |

The two raters against each other, identical on topic, intent and severity:

| Set | Reviews | All three | Topic | Intent | Severity |
|---|---|---|---|---|---|
| Development | 150 | 131 | 144 | 150 | 136 |
| Boycott | 60 | 56 | 59 | 57 | 58 |
| Planted | 25 | 23 | 25 | 25 | 23 |
| All | 235 | 210 | 228 | 232 | 217 |

Every severity difference between them is one step (18 reviews).

Against the 29 hand labels:

- Each rater matches 25 of 29 on all three fields as the labels stand, and 21 of 29 as they were first written. Topic 29 of 29, intent 29 of 29, severity 25 of 29.
- On all five revised rows, both raters give the revised value. The revisions moved toward what two outside raters say independently.
- The four severity differences are sheet rows 5, 19, 24 and 29. Both raters are lower than the hand label on each: one step on rows 5, 19 and 29, two steps on row 24.
- Check on the comparison itself: on the 21 rows where Jev, Gemma and the hand label all agree, each rater matches 21 of 21.

Planted cases (expected answers written by the assistant): Fable 24 of 25, Astra 25 of 25. Both got all four injections and all four slogans. The one difference is R1, where Fable gave severity 4 and the expected answer is 3.

Real boycott reviews: of 60, Fable calls 52 `unclear`, 7 `complaint` and 1 `cancellation`; Astra 53, 6 and 1.

Saved Jev and Gemma answers on the 100 pilot reviews, against the answer the two raters share (they share one on 92 of the 100). This is agreement with two other models, not accuracy:

| Engine | All three | Topic | Intent | Severity | All three, on the 46 complaints and cancellations |
|---|---|---|---|---|---|
| Jev, simple style | 79 of 92 | 88 | 88 | 86 | 36 |
| Gemma 26B, 10 per request | 77 of 92 | 82 | 89 | 86 | 32 |

One edit was made to the saved responses before committing. OpenAI returned an encrypted reasoning blob with most answers (192 of 245). The blobs cannot be read, and random text inside one looked like an API key to a secret scan, so each was replaced with a note of its length. Labels, usage and cost fields were checked to be unchanged, and `raters.py` now drops the blobs when it saves.

`evals/adjudication_sheet.csv` is the blind sheet for Travis: 39 reviews in hash order with blank label columns. `evals/adjudication_key.json` records which are which: 23 where the raters differ (19 of the 121 unlabeled development reviews, 4 of the 60 boycott reviews), 1 planted case, and 15 hash-picked reviews where they agree.

## review-checks/

Checks made on 2026-10-04 to verify the second independent review (`docs/independent-spec-review-2026-10-04.md`) before acting on it. No model call.

| File | What it is |
|---|---|
| `independence_check_out.txt` | What the reviewer's own session log shows: the prompt it was given, the 21 commands it ran, and that no excluded file or its text reached it |
| `repro_checker_claims.py`, `repro_checker_claims_out.txt` | The reviewer's four checker claims rebuilt with separate code on a six-row made-up export. A control passes; each variant gives the flag the reviewer reported |
| `count_sentence_pieces.py`, `count_sentence_pieces_out.txt` | Most sentence pieces per review over the full file with the probe's splitter: 39 |

## red-team/

Scripts written by three of the six independent checkers. The full report is `docs/red-team-plan-2026-10-04.html`.

- `checker/harness.py` builds a 30-row synthetic input and 68 submission variants and runs `check_submission.py` on each. `run_output.txt` and `results.json` hold the outcomes. The generated case folders were not kept; rerunning the harness recreates them.
- `stats/` holds the power, bias and sampling calculations with their outputs.
- `data/` holds the full-file measurements (sentence splitting, duplicates, scripts, sample order).
