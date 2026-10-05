# Validation log

One place that lists every check run on the plan, the tools and the labels, so the final README can cite them. Each entry says what was checked, why the checker counts as independent, what it found, where the evidence is, and what it does not show.

Rules for this file:

- A number is here only if a saved file backs it. Estimates are marked.
- A check that found a problem stays in the log with the problem.
- Add an entry when a check runs. Do not edit an old result; add a new entry that supersedes it.

Status on 2026-10-04: design stage. No pipeline code exists and no full run has been made. Everything below was done to choose tools and to test the design and the labels before building.

## Summary

| # | Check | Who checked | Size | Result | API cost |
|---|---|---|---|---|---|
| 1 | Red team of the plan | Six separate checkers given plain claims, never the plan | 65 claims | Verdict Reshape: 22 confirmed, 17 partial, 23 contradicted, 3 unverifiable | none |
| 2 | Checker behavior | The instructor's `check_submission.py`, run on made-up submissions | 68 submissions | Found which designs get flagged; three plan assumptions were wrong | none |
| 3 | Full-file data facts | Code over all 660,622 rows | whole file | Row, duplicate and trap counts confirmed; one count contradicted | none |
| 4 | Jev against hand labels, two question styles | One human labeler | 29 labels | Simple style 24 of 29 on all three fields; per-sentence 23 | $0.0097 |
| 5 | Gemma 26B against the same labels | Same labels | 29 labels | 23 of 29 on all three fields | local |
| 6 | Tricky made-up reviews | Expected answers written from the contract | 25 reviews | Jev 21, Gemma 23; Jev missed 2 of 4 injections and 2 of 4 slogans | about $0.005 (estimate) |
| 7 | Repeatability | Same reviews sent again | 100 reviews | Jev 0 changed; Gemma 1 changed, 15 when regrouped | included in 6 |
| 8 | Jev speed in parallel | Wall clock | 1,000 requests | 60 and 78 requests per second, no errors | $0.0388 |
| 9 | Review-flag signal | Saved Jev probabilities against its mistakes | 100 reviews, 29 labeled | Low probability lines up with mistakes; too thin to set a number | none |
| 10 | Independent review of the spec | Three reviewers with no access to the author's reasoning | about 32 findings | 4 serious holes; fixes folded in; 13 choices raised | not metered |
| 11 | Outside raters | Two models from other makers, blind | 235 reviews each | Identical on 210 of 235; no refusals | $1.12 and $2.77 |
| 12 | Were the five label revisions fixes or drift | The two outside raters, blind | 5 rows | Both give the revised value on 5 of 5 | in 11 |
| 13 | Answer key for the planted cases | The two outside raters | 25 cases | 24 and 25 of 25 match the key | in 11 |
| 14 | Real boycott reviews | Hash-picked sample, two raters | 60 reviews | 52 or 53 `unclear`, 6 or 7 `complaint`, 1 `cancellation` | in 11 |
| 15 | Jev and Gemma against the raters' shared answer | Two outside raters | 92 reviews | Jev 79, Gemma 77 on all three fields | in 11 |
| 16 | Blind human check of the raters | Travis, by hand | 39 reviews | **Pending** | none |

Measured API spend on validation so far: Jev about $0.053, Fable 5.1 $1.12, Astra 6 $2.77. The red team, the spec review and the assistant's own work ran in Claude Code sessions whose cost was not metered per task. That cost is unknown, not zero.

## The entries

### 1. Red team of the plan

- **What:** before any model was run, 65 factual claims the plan depended on were tested against the assignment's own files, the full data and vendor documentation.
- **Independence:** six checkers, each given plain claims and pointers to primary sources, never the plan or its reasoning. A "contradicted" verdict needed a quoted line, a measured count or a reproducible test, the same standard as "confirmed". Eight claims with known wrong answers were planted to test the checkers; all eight were caught.
- **Result:** verdict Reshape. Six findings changed the plan: the cost pilot must run all six stages; 50 labels cannot both pick an engine and grade it; Jev through Cloudflare is capped at 200 requests a minute; Jev's documented weak spot is multi-step rules; the checker punishes mixed configurations and re-sent reviews; the data has slogan, emoji and burst traps.
- **Evidence:** `docs/red-team-plan-2026-10-04.html`, `experiments/2026-10-04/red-team/`.
- **Limit:** document and data checks only. Label quality was not tested.

### 2. Checker behavior

- **What:** `check_submission.py` run on a 30-row synthetic input with 68 submission variants, to learn exactly what it flags.
- **Independence:** the checker is the instructor's code, not ours.
- **Result:** a second model under its own `label_config` is flagged on every review; any resume call that lists an already-finished review is flagged, even a failed one; missing, null or decimal token counts are flagged; checkpoints must not list quarantined IDs.
- **Evidence:** `experiments/2026-10-04/red-team/checker/` (`harness.py`, `results.json`, `run_output.txt`).

### 3. Full-file data facts

- **What:** counts over the whole 97 MB file.
- **Result:** 660,622 rows, 13 empty texts, 484,189 distinct nonempty texts, 12,268 nonempty reviews with no letter or digit, 3,484 containing "boycott", two review-bombing bursts (July and October 2023). The file's SHA-256 matches `manifest.json`.
- **Known-answer checks:** the row count and checksum come from the manifest, which the instructor wrote. The boycott count was reproduced by a second script on a later day (entry 14).
- **Evidence:** `experiments/2026-10-04/red-team/data/`, `outside-raters/pick_boycott.py`.

### 4 and 5. Jev and Gemma against hand labels

- **What:** both engines labeled the 100 pilot reviews; 29 of those have hand labels by Travis.

| Engine | Topic | Intent | Severity | All three |
|---|---|---|---|---|
| Jev, one broad question per label | 28 | 28 | 26 | 24 |
| Jev, per sentence | 27 | 28 | 25 | 23 |
| Gemma 26B, 10 reviews per request | 25 | 29 | 26 | 23 |

- **Known weakness, found by the spec review:** five of the 29 labels were revised after the labeler saw Jev's answers. Against the labels as first written, Jev simple scores 21 of 29, not 24. Both numbers are reported wherever this table is used. Entry 12 tests whether those revisions were fixes.
- **Evidence:** `experiments/2026-10-04/tool-choice/` (`simple.jsonl`, `sentence.jsonl`, `gemma.jsonl`, `compare.py`, `compare_out.txt`).
- **Limit:** 29 labels from one person. Too few to separate the engines.

### 6. Tricky made-up reviews

- **What:** 25 synthetic reviews built to hit contract rules, emoji-only text, non-English text, boycott slogans and injected instructions.
- **Result:** Jev 21 right, Gemma 23. Jev was moved by instruction-like text in 2 of 4 injection cases and read boycott hashtags as `cancellation` in 2 of 4 slogan cases. Gemma got all 8 of those right.
- **Weakness, then a check:** the expected answers were written by the assistant, not a second person. Entry 13 had two outside raters label the same 25 blind.
- **Evidence:** `tool-choice/three_tests.py`, `three_tests_out.txt`.

### 7. Repeatability

- **Result:** Jev changed 0 answers on a rerun of 100 reviews. Gemma changed 1 with the same request grouping and 15 when the same reviews were grouped into different requests. This is why Gemma runs at one review per request.
- **Evidence:** `tool-choice/three_tests_out.txt`.

### 8. Jev speed

- **Result:** 60 requests per second with 8 workers; 78 with 16 workers capped at 80; all 1,000 requests returned 200.
- **Limit:** each run lasted under 9 seconds. Sustained speed is unmeasured.
- **Evidence:** `tool-choice/three_tests_out.txt`.

### 9. Review-flag signal

- **What:** for each pilot review, the lowest of Jev's three top probabilities, compared with Jev's mistakes on the labeled rows and with its disagreements with Gemma. No new calls.
- **Result:** at a cut-off of 0.7 the flag marks 26 of 100 reviews and catches 4 of Jev's 5 mistakes. Catching all 5 means flagging 54 of 100.
- **Checks inside the script:** it must reproduce the 24 of 29 score and the 23 engine disagreements before it prints anything.
- **Limit:** 5 mistakes. No number was chosen from this.
- **Evidence:** `tool-choice/flag_probe.py`, `flag_probe_out.txt`.

### 10. Independent review of the spec

- **What:** the written design was read against the source files by three reviewers with different lenses: measurement validity, contract and checker compliance, state and spending controls.
- **Independence:** none saw the author's reasoning. Each had to quote a source line for every finding. The most serious findings were then rechecked against those lines.
- **Result:** about 32 findings. Four were serious: the resume evidence would have been flagged; the development labels lean toward Jev; engine agreement is much lower on complaints (34 of 52) than on other reviews (43 of 48); a crash could lose paid calls. Two claims in the draft were simply wrong and were removed.
- **Evidence:** `docs/spec-review-2026-10-04.md` holds the briefs, the reports as written, and what happened to every finding. The spec's section 13 lists the changes.
- **Limit:** the reviewers are the same model family as the spec's author. Nothing was executed.

### 11. Outside raters

- **What:** Claude Fable 5.1 (`claude-fable-5-1`, Anthropic) and GPT-6 Astra (`gpt-6-astra`, OpenAI) each labeled 235 reviews: the 150 development reviews, 60 real boycott reviews and the 25 made-up reviews.
- **Independence:** different makers from Jev (TypeSafe) and Gemma (Google). One review per request. Each saw only the review and the contract's label section, copied word for word from `GRADING_CONTRACT.md` at run time (2,522 characters, SHA-256 starting `21b37d5f43750bc9`). Nothing from Jev, Gemma or the hand labels was in any prompt. No fallback model was used, so each file is one rater's work.
- **Result:** both labeled 235 of 235 with no refusals. They gave identical topic, intent and severity on 210 of 235 (topic 228, intent 232, severity 217). Every severity difference is one step.
- **Checks inside the comparison:** on the 21 rows where Jev, Gemma and the hand label already agree, each rater matches 21 of 21. The script stops if either rater uses almost one topic or if agreement is 100% or under 30%.
- **Setting:** medium effort, chosen after testing the same 10 reviews at low and at medium. Fable gave the same answers at both; Astra changed 1 of 10.
- **Cost:** $1.12 and $2.77, under a cap of $10 each that the script enforces.
- **Evidence:** `experiments/2026-10-04/outside-raters/` (`raters.py`, the four `.jsonl` files with every response, `compare_raters.py`, `compare_raters_out.txt`).
- **Limits:** both raters are language models, like the engines they check, and can share a blind spot such as reading anger as severity. Fable 5.1 is from the same maker as the assistant that wrote the spec. Their labels are used to tune and to find disputed reviews, never to claim accuracy.

### 12. Were the five label revisions fixes or drift

- **Question:** entry 4's labels were revised after the labeler saw Jev. Did they move toward the contract or toward Jev?
- **Result:** on all five revised rows, both outside raters independently give the revised value. Each rater matches 25 of 29 hand labels as they stand and 21 of 29 as first written.
- **What remains:** four severity differences (sheet rows 5, 19, 24, 29). Both raters are below the hand label on each. The labels stay as they are, by the freeze rule, and both scores are reported.
- **Evidence:** `outside-raters/compare_raters_out.txt`.

### 13. Answer key for the planted cases

- **Result:** Astra matches the assistant's expected answer on 25 of 25 and Fable on 24 of 25, including every injection and slogan case. The one difference is case R1, where Fable gives severity 4 and the key says 3.
- **Evidence:** `outside-raters/compare_raters_out.txt`.

### 14. Real boycott reviews

- **What:** 60 real reviews containing "boycott", picked by hash among 1,873 distinct eligible texts, with every golden and development review excluded. Half are marked for tuning and half are held back to be scored once.
- **Result:** the raters call 52 or 53 of the 60 `unclear`, 6 or 7 `complaint`, and 1 `cancellation`. They differ on 4.
- **Why it matters:** Jev read boycott hashtags as `cancellation` in entry 6. Cancellations enter the issue ranking, and 3,484 reviews contain the word.
- **Evidence:** `evals/boycott_60.csv`, `outside-raters/pick_boycott.py`.

### 15. Jev and Gemma against the raters' shared answer

- **Result:** on the 92 pilot reviews where the two raters agree with each other, Jev matches their answer on 79 and Gemma on 77 (all three fields). On the 46 complaints and cancellations among them: Jev 36, Gemma 32.
- **Limit:** this is agreement with two other models, not accuracy. Gemma's answers here are from the 10-per-request probe, a setup since dropped.
- **Evidence:** `outside-raters/compare_raters_out.txt`.

### 16. Blind human check of the raters (pending)

- **What:** Travis labels 39 reviews by hand without seeing any rater's answer: the 23 where the raters differ, 1 planted case, and 15 picked by hash from the reviews where they agree. The three kinds are mixed and unmarked.
- **Why:** the 15 agreed reviews measure how often a label both raters share is wrong in a human's judgment. Without that, rater agreement is only agreement.
- **Freeze:** the filled sheet is committed and hashed before any rater answer for those rows is shown.
- **Files:** `evals/adjudication_sheet.csv`, `evals/adjudication_key.json`.

## Rules adopted because of these checks

- **Label freeze.** A label file is committed and its SHA-256 recorded before model output for its rows is seen. A golden label does not change after the freeze; a plainly wrong one stays and the score is shown both ways.
- **Both scores, always.** Where labels were revised after seeing a model, the before and after scores are reported together.
- **Golden 50 is scored once**, on the final setup, and never used to choose an engine, a prompt or a cut-off.
- **Held-back halves.** The boycott sample and the development rows are split by hash, so wording is tuned on one half and scored once on the other.
- **Agreement is not accuracy.** Engine agreement is reported split by complaints against the rest.
- **Every check carries a known-answer test** where one exists: a count from the manifest, a score that an earlier script already produced, or rows where independent sources already agree.

## What all of this still does not show

- **One human labeler.** No second person has labeled anything, so nothing measures how firm the hand labels are. The instructor's private sample is the only human check from outside.
- **Small samples.** 29 hand labels, 25 made-up cases, 60 boycott reviews, 100 pilot reviews.
- **Single runs on one day.** No result here has been repeated on another day except Jev's rerun in entry 7.
- **The golden 50 is not labeled yet**, so there is no accuracy figure of any kind.
- **Nothing is built.** These checks cover tool choice, the design and the labels. The pipeline's own tests come later and will be added here.
