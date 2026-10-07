# Validation log

One place that lists every check run on the plan, the tools and the labels, so the final README can cite them. Each entry says what was checked, why the checker counts as independent, what it found, where the evidence is, and what it does not show.

Rules for this file:

- A number is here only if a saved file backs it. Estimates are marked.
- A check that found a problem stays in the log with the problem.
- Add an entry when a check runs. Do not edit an old result; add a new entry that supersedes it.

Status on 2026-10-04: design stage. No pipeline code exists and no full run has been made. Everything below was done to choose tools and to test the design and the labels before building.

Update 2026-10-05: both hand-labeled files are frozen (entries 16 and 18). Later the same day the pipeline was built and tested with stand-in models (entry 21). No real run has been made.

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
| 16 | Blind human check of the raters | Travis, by hand | 39 reviews | Hand label equals the raters' shared answer on 4 of 15 agreed reviews (topic 12, intent 12, severity 5); on the 23 disputed it equals Fable's on 3, Astra's on 3, neither on 17 | none |
| 17 | Second independent review of the spec | A reviewer from another maker, given one brief file and none of the earlier conclusions | 13 factual claims | All 13 confirmed on recheck; three mislabeled numbers and several gaps fixed | not metered |
| 18 | Label freeze | Format check by code; label values never shown | 39 and 50 rows | Both files committed and hashed before any model answer for their rows; nine blank golden cells filled after a first check | none |
| 19 | The contract's fixed severity rule against the hand labels | Code only; counts alone for the golden file | 39, 29 and 50 labels | The rule would change 8, 0 and 4 labels; with it applied the blind check reads 8 of 15 | none |
| 20 | Outside review of the implementation plan | A reviewer given the plan; report pasted in by Travis | 7 issues, 5 smaller points | All 7 hold and are fixed; the 5 smaller points are taken, one in a different form | not metered |
| 21 | The built pipeline, with stand-in models | The instructor's checker; known answers from earlier scripts; 404 automated tests | every stage, 100 real pilot texts replayed | Checker `pass` on a stopped and resumed stand-in run; eight deliberate breaks each named; four known answers reproduced | none |
| 22 | Independent review of the built code | A fresh reviewer with none of the build's context, same model family as the author | 77 files, about 10,500 lines | No critical finding, 7 important, 12 minor; all fixed but one minor, each with a test that failed first | not metered |
| 23 | The wording trial | Pass marks written before the trial; planted answers from the contract; the outside raters' shared answer on real reviews | 34 items, two wordings, 68 requests | Probe 2 of 4 slogans and 15 of 28; candidate 4 of 4 and 23 of 28; no pass mark missed | $0.0033 by the ledger |
| 24 | Are Jev's output tokens billed | The provider's usage page, read by Travis, against token counts the responses reported | 1,451 requests on the page; 325 with saved usage | Not billed: the page's $0.056 is input tokens times the rate; billing every token would show about $0.069 | none |
| 25 | The 100-review pilot | The instructor's checker; the probe's saved answers; development labels; the raters' shared answer | 100 reviews, every stage, real models | 100 of 100 labeled; checker `pass`, no flags; warm pass 0 calls; the frozen wording changes 3 of 100 labels; the memo passed on its fourth attempt | $0.0042 |
| 26 | The holdout, scored once | Planted answers from the contract; the outside raters' shared answer on real boycott reviews | 30 reviews and 25 planted cases | Planted 22 of 25; holdout 13 of 28 on all three labels, 24 of 28 on intent | $0.0022 |
| 27 | The rest of the cut-off half | The raters' shared answer and Travis's labels, side by side | 28 more reviews; table over all 60 | At 0.70 the flag marks 23 of 60 and catches 7 of 9 differences from the raters | $0.0013 |
| 28 | Which model writes the memo, and a fault in the memo check | The pipeline's own check under a choosing rule written first; then the memos' text read against the check | 3 models, 2 trials each | 4 of 6 first attempts rejected for one reason; the check was wrong; corrected, all 6 pass; cheapest chosen | $0.79 (Anthropic) |
| 29 | The pilot again with the paid memo model, and Jev against itself | The instructor's checker; the first pilot's labels | 100 reviews, every stage | Checker `pass`; warm pass 0 calls; Jev changed severity on 2 of 100 and the flag on 3 between identical runs | $0.0042 and $0.045 |
| 30 | The 500 gate | The instructor's checker; the pilot's labels on the shared 100 | 500 reviews, 16 workers | Checker `pass`; 21 copies reused; 71.5 requests a second; every pass mark met but the nested one | $0.0199 and $0.025 |
| 31 | Two rulings coded: the severity rule and the nested check | Counts made before the code; the nested numbers measured earlier by a separate script | 100 saved answers; two pairs of real runs | The rule changes the one known review of 100; the nested command gives 2 of 100 and 1 of 100, as measured | none |

Measured API spend so far: the pipeline's ledger reads $0.1578 after the 500 gate on 2026-10-05, about $0.088 to Jev (the provider's usage page read $0.056 after the wording trial, entry 24) and $0.070 to the memo model. Outside the ledger: the memo comparison $0.79 (Anthropic), Fable 5.1 $1.12 and Astra 6 $2.77 as outside raters. The red team, the spec review and the assistant's own work ran in Claude Code sessions whose cost was not metered per task. That cost is unknown, not zero.

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

### 16. Blind human check of the raters

- **What:** Travis labeled 39 reviews by hand without seeing any rater's answer: the 23 where the raters differ, 1 planted case, and 15 picked by hash from the reviews where they agree. The three kinds are mixed and unmarked.
- **Why:** the 15 agreed reviews measure how often a label both raters share differs from a human's judgment. Without that, rater agreement is only agreement.
- **Freeze:** the filled sheet was committed on 2026-10-05 as `634c05c` (SHA-256 `47ce41508e911455179a983f12f9e105c31129fae0450f790b6f46bf798e9274`) before any rater answer for those rows was shown. The scoring script refuses a sheet that is not committed.
- **Result, the 15 agreed reviews:** the hand label equals the raters' shared answer on all three fields for 4 of 15 (topic 12, intent 12, severity 5).
- **Result, the 23 disputed reviews:** the hand label equals Fable's on 3, Astra's on 3 and neither on 17. Where the raters differ on a field, the hand label gives: topic (7 reviews) Fable's on 3, Astra's on 0, neither on 4; intent (3) Fable's on 1, Astra's on 2; severity (16) Fable's on 7, Astra's on 4, neither on 5.
- **Each rater against the hand labels, the 38 real reviews:** Fable 7 of 38 on all three (topic 26, intent 31, severity 16). Astra 7 of 38 (topic 23, intent 32, severity 13). The hand severity is below Fable's on 15 reviews and above on 7; below Astra's on 16 and above on 9. No difference is more than two steps.
- **A pattern in the hand labels:** all 8 boycott reviews labeled `unclear` carry severity 2 (sheet rows 4, 8, 11, 22, 24, 25, 35, 36). The contract's severity 1 covers "neutral/unclear content" and the labeling guide gives a boycott slogan severity 1. Wherever a rater says `unclear` on those rows it gives severity 1. Four of the 11 agreed-check differences are this alone (rows 4, 8, 35, 36); set aside, the agreed checks would read 8 of 15. The labels stay as frozen and both readings are reported.
- **Planted case R1** ("I pay for premium and the music still stops every 30 seconds"): the expected answer is `playback`, `complaint`, 3. The hand label is `billing`, `complaint`, 2. Fable gives `playback`, `complaint`, 4 and Astra `playback`, `complaint`, 3.
- **Checks inside the scoring:** the key must still describe the rater files (agreed rows identical, disputed rows different); each sheet text must equal the source text; no hand label may equal both raters on a disputed row; the planted case must reproduce entry 13 (Astra matches the key, Fable does not). On a made-up sheet built from the raters' own answers the script returned the counts built into it (15 of 15; 13, 10 and 0).
- **Evidence:** `experiments/2026-10-05/labels/score_adjudication.py` and `score_adjudication_out.txt`; `evals/adjudication_sheet.csv`, `evals/adjudication_key.json`.
- **Limits:** one labeler, one pass, 15 agreed reviews. The labeler had already seen entry 12 (both raters below his severity on four development rows) before labeling these. The raters are language models: a difference between them and the hand label is not an error by either side until the rule is read against the review.

### 17. Second independent review of the spec

- **What:** the spec was reviewed again, this time by a model from a different maker (Codex, `gpt-6.1-sol`). It was pointed at one file, `docs/independent-review-brief.md`, which holds the instructions and a copy of the spec with the first review's summary and the authors' known-weakness lists removed.
- **Independence, checked and not assumed:** the reviewer's own session log shows the prompt it was given (the brief's path and an instruction not to read the project notes) and all 21 commands it ran. None opened the project notes, the full spec, the first review, this log, the red-team report, a label sheet, the blind-sheet key, a rater answer file or `.env`, and no text from any of them appears in the log. No instruction file exists that its tool would load by itself.
- **Result:** 13 factual claims. Each was rechecked by quoting the source line or by running the test again with separate code. All 13 held:
  - four claims about what the checker flags, rebuilt on a six-row made-up export (a control passes; each variant gives the reported flag);
  - three numbers in the spec that were mislabeled: a Gemma speed measured at 10 reviews per request and presented as one per request; probe spend called measured when part was estimated; a sentence-piece maximum from an older splitter (164, now 39);
  - six gaps in the design text: the resume rule, what the ledger records for failed and invalid responses, the verifier report's denominators, model checks on the naming and memo calls, a contradiction between two label rulings, and code changes between sessions.
- **Severity:** the reviewer rated eight findings as blockers. On recheck none stops the design. The statements are true; the ratings run high, which fits a reviewer told that a finding is a success.
- **What it caught that the first review missed:** the Gemma speed label. The first reviewers were given the project notes, which carried the same wrong figure. This one was not, and read the saved output. That is the case for using a different maker and withholding the authors' account.
- **Evidence:** `docs/independent-spec-review-2026-10-04.md` (the report), `experiments/2026-10-04/review-checks/` (the independence check, the checker reproduction, the recount), and the spec's section 13.
- **Limits:** the brief that framed the review was written by the spec's author, so the reviewer's attention followed the author's four passes. The recheck was also done by the author. The reviewer could not open the label files, so it could not test anything about the labels themselves.

### 18. Label freeze: the blind sheet and the golden 50

- **What:** on 2026-10-05 both hand-labeled files were imported from Numbers by review ID, format-checked, committed and hashed. The blind sheet was frozen before any rater answer for its rows was shown. The golden 50 was frozen before any model saw those texts.
- **How the labels stay unseen:** the import prints row numbers, column names and counts, never a value. No golden label was read into the assistant's context.
- **Result, blind sheet:** 39 of 39 rows filled on intent, topic, severity and needs_review, nothing outside the lists. Commit `634c05c`, SHA-256 `47ce41508e911455179a983f12f9e105c31129fae0450f790b6f46bf798e9274`. Numbers source as saved at 11:05 PDT: SHA-256 `76dbc13cd38bdf1faaf1a4ac0f4d18ed48e956e719adb30422437fb8c03df737`.
- **Result, golden 50:** 50 of 50 rows filled on intent, topic, severity, sentiment, evidence_quote and needs_review (entities on 21, notes on 10). Every quote is an exact copy of its review. Commit `dcab9ff`, SHA-256 `b9d25cf271d921ec0a2545d2ca4a3ad8655e3b7056ac492b5a0458c5e4f2b79d`. Numbers source as saved at 11:44 PDT: SHA-256 `b786faf5293e85e3fafccdfd65189f8375f273607b192a059e49ad4b72a97bfe`.
- **What changed before the golden freeze:** the file as first finished at 11:38 (Numbers SHA-256 `a1b906baec909162ccb73464c3ba31de50238b1c3573da5a02e659657541569f`) had nine blank cells: evidence_quote on sheet rows 18, 19, 20, 21, 28, 32, 35, 38 and needs_review on row 49. Those nine were filled. One cell that already held a value also changed (entities, row 49). No model answer and no score was shown in between. The blind-sheet score was run once into a file nobody opened, to test the script, and was first displayed after the golden commit.
- **Checks inside the import:** the IDs in the export must equal the IDs in the file; the text beside each ID is compared with the repo's text (no differences on either file); the rewrite must leave IDs and texts unchanged. On a made-up export with shuffled rows, odd letter case and number format, the written file was byte-identical to the expected one, and an export with a blank cell and two bad values was refused with the right rows named.
- **Evidence:** the two commits; `experiments/2026-10-05/labels/import_numbers.py`.
- **Limits:** the Numbers documents are not in the repo, only their hashes. The order of events rests on commit times and this log. The golden labels have not been compared with anything, and nothing has checked them against the labeling guide's rules.

### 19. The contract's fixed severity rule against the hand labels

- **What:** a count of hand labels whose intent is `unclear`, `praise` or `request` and whose severity is above 1. The contract's severity 1 is "No reported problem: praise, neutral/unclear content, or a pure feature request", so such a label has severity 1 by rule.
- **Why:** entry 16 found the pattern on the blind sheet. The golden 50 was labeled the same morning by the same person.
- **Independence:** code only. No model answer enters. For the golden file the script prints counts, never a row number or a value.
- **Result:** the rule would change 8 of 39 labels on the blind sheet (all `unclear`, the eight boycott rows of entry 16), 0 of 29 on the development sheet, and 4 of 50 on the golden file (all `unclear`).
- **Known-answer test:** before it reads the golden file the script must reproduce the eight blind-sheet rows, which were read by eye from entry 16's output before the script existed. It refuses a golden file whose hash is not the frozen one.
- **Entry 16 read again with the rule applied to the hand labels:** agreed checks 8 of 15 on all three fields (4 as written), severity 8 (5). Disputed rows: Fable's on 4, Astra's on 5, neither on 14 (3, 3 and 17). Fable 12 of 38 on all three, severity 20 (7 and 16). Astra 13 of 38, severity 19 (7 and 13). Neither rater has a label that breaks the rule on these 39 rows.
- **Ruling by Travis, 2026-10-05:** the labels stay as frozen. Every score against hand labels is reported two ways: against the labels as written, and with this rule applied to them by code (spec section 12 item 32).
- **Evidence:** `experiments/2026-10-05/labels/rule_check.py`, `rule_check_out.txt`, `score_adjudication_out.txt`.
- **Limits:** the ruling came after Travis saw the raters' answers on the blind sheet. The rule is the contract's wording and takes no model answer, but the choice to apply it was made with those answers in view. It covers one kind of departure: complaints given 2 where the raters give 3 are untouched. It says nothing on whether the intent on those rows is right.

### 20. Outside review of the implementation plan

- **What:** a reviewer read `docs/superpowers/plans/2026-10-05-spotify-insight-pipeline.md` at commit `cd0c04e` and reported seven issues it rated as blocking and five smaller corrections. Travis pasted the report into the session.
- **Independence:** the report does not name the reviewer. It says it changed no file, made no provider call and opened no protected label. No session log came with it, so that is the reviewer's own statement, not something checked here.
- **How each claim was checked:** claims about the plan's wording were read against the cited lines. The checker claims were read against `check_submission.py`. Two claims about data were rerun with separate code.
- **Result:** all seven issues hold. Three would have cost a gate or corrupted a run: the wording gate asked for three of four planted slogans to be `unclear` when only two expect it (S3 expects `cancellation`, S4 `complaint`); crash recovery as written could return an already classified review to `pending` after a crash in verify; and the 500 and 10,000 gates asked for a checker pass on a run that was never stopped, which the checker flags. The other four: a commit plus a "dirty" mark does not identify uncommitted code; ledger dollars recomputed from an editable rate file let a rate edit shrink past spend; offline replay had no saved source for its clocks; a copy's pointer to its original could be cleared on a retry.
- **Data claims rerun:** of the 100 saved Jev answers, 25 hold a fifth question named `evidence` and none holds `quote`; all 100 tone scores are floats and 90 are fractional, from 0.0 to 4.0. The plan had renamed the question and typed the score as a whole number.
- **Taken in a different form:** the reviewer proposed turning guards into inspection flags for inputs other than the supplied file. Guards still raise for every input; another input can be restarted with the guard accepted by name, which is logged. A guard that only warns produces no event when it matters.
- **Evidence:** `docs/plan-review-2026-10-05.md` (the report as pasted, then the outcome of each point), `experiments/2026-10-05/plan-review/check_claims.py` and `check_claims_out.txt`, the plan's diff, and spec section 12 item 33.
- **Limits:** nothing is built, so no claim was tested by running pipeline code. The reviewer's reproduction of the fingerprint collision was not rerun; the claim is true by construction. The fixes were written by the plan's author and have not been reviewed in turn.

### 21. The built pipeline, with stand-in models

- **What:** the pipeline was built on 2026-10-05 and run end to end with stand-ins: a stand-in classifier that replays the 100 answers Jev gave on 2026-10-04 (and labels other text by a fixed keyword rule), and a stand-in for the local model. No real model was called.
- **Independence:** the judge of the export is the instructor's `check_submission.py`, which the author did not write. The known answers below were each produced earlier by a different script. The tests themselves were written by the same author as the code, in the same session.
- **Result, the checker:** a run through every stage, stopped once and resumed, exports and the checker returns `pass` with no flags, labelable completion 1.0 and accounted 1.0. Eight deliberate breaks of a good export (a copy with a different label, a quarantined ID in a checkpoint, a resume call naming a checkpointed ID, a decimal token count, a mean with five decimals, both forms of a file, a call under another setup, a complaint left out of membership) are each named by the checker.
- **Result, known answers reproduced:** (1) the request built for each of the 100 pilot reviews equals the request the probe sent, and the mapped topic, intent, severity, quote and sentiment equal the probe's on all 100; (2) replaying those answers through every stage gives 52 complaints or cancellations and severity sums of 38, 29, 22 and 20 for usability, other, playback and billing, the figures in entry 4's notes; (3) the calculator gives $0.0039 of API spend for the 100, the figure measured in entry 4; (4) the cut-off table gives entry 9's table, and 13 differences from the raters' shared label on 92 rows, which is entry 15's 79 of 92.
- **Result, the full file:** prepare reads all 660,622 rows and gives 13 empty, 484,189 distinct texts and 159,701 missing app versions, the manifest's counts (11.7 seconds; run once, skipped in the normal suite).
- **Falsification:** with the exact-quote check removed in a scratch copy, two tests fail and name it.
- **Evidence:** `tests/` (404 tests, 1 skipped), `README.md` (the falsification output), the build's commits on `build/pipeline`.
- **Limits:** stand-ins answer instantly and never return an odd shape, so nothing here tests a real model's behavior, real rate limits, or sustained speed. Agreement between two stand-ins that share a rule is meaningless and is not reported. The code paths that only a real run uses (`--go`) are covered by tests against a local test server, not by a call.

### 22. Independent review of the built code

- **What:** one reviewer read the whole `build/pipeline` branch against the plan and the spec (77 files, about 10,500 lines), read-only, after all 18 tasks were done. It was given the plan's five untested risk areas and the executor's rulings to weigh.
- **Independence:** a fresh session with none of the build's context, on the most capable model available. It is the same model family as the author, so it shares the author's blind spots; it is a second reading, not an outside one. It made no model call and opened neither `.env` nor a golden label column.
- **Result:** no critical defect, 7 important, 12 minor. Verdict: ready with fixes, 1 to 4 before any paid command and 5 to 7 before the 100 gate is judged. The parts it read and found sound: no lost result or double send in classify, the ledger's totals, every crash point of the two-step save, and the export against the checker's rules.
- **What it found that the tests had not:** (1) names and memos were cached across runs, so a second run on the same file would make no naming or memo call and fail the checker's four-roles rule; (2) the paid pilot could not be run again after stopping partway and took any unfinished ending for its planned stop; (3) during an outage classify would have booked a failed call, and a held reservation, for every review it admitted; (4) a request the provider refuses for one review halted the run, and the resume sent the same review first; (5) the verify, naming and memo prompts were not part of anything saved, so an edited prompt was answered from the old result; (6) two gate pass marks had no code behind them; (7) changing only the projected row count gave a report with a negative count of empty reviews.
- **How each was handled:** every finding was reproduced by a test that failed before the fix and passes after it, in one pass. Six of the twelve minor findings were re-graded as important by their effect (a key that could reach a committed log, a golden cell that could be printed, a stand-in run sharing the ledger that guards real money, a cut-off with three decimals, evidence files too large to push, verify stalling on one refused request). One minor finding is left open and listed in `docs/build-rulings-2026-10-05.md`.
- **Known-answer checks after the fixes:** the stand-in run of the supplied 100-review file, stopped once and resumed, still exports and the supplied checker still returns `pass` with no flags; the replay still gives 52 members and $0.0048 for 100 reviews with output tokens counted at the input rate.
- **Evidence:** `tests/test_review_fixes.py` (one test class per finding), the three fix commits on `build/pipeline`, `docs/build-rulings-2026-10-05.md` (the rulings the reviewer asked to overturn and what was done with each).
- **Limits:** the fixes were written by the author and have not been reviewed in turn; the suite passing is the only check on them. The reviewer set aside everything that needs a real call: how LM Studio and TypeSafe behave, whether Gemma's memo passes the check, sustained speed, and how fast the state file commits under load. On macOS the clock the 60-second stop uses does not advance during sleep, so that stop is proven with an injected clock only.

### 23. The wording trial: the first paid call through the pipeline's own code

- **What:** on 2026-10-05 at 15:20 PDT, with Travis's go, `evals/wording_trial.py --go` sent the 4 planted slogan cases and the 30 real boycott reviews marked `tune` to Jev twice: once with the probe's intent wording (`prompts/enrich-v1.json`) and once with the candidate (`prompts/enrich-v2.json`, where only the intent question differs). 68 requests, one at a time, through the same ledger and call log the pipeline uses. The 30 `holdout` reviews were not read; the script refuses if one reaches it.
- **Independence:** the pass marks were written in the implementation plan before the candidate wording was tried. The planted cases' accepted answers come from the contract and both outside raters gave them. The reference on the real reviews is the answer the two outside raters share, which is agreement with other models, not accuracy. The candidate wording was written by the same author who wrote the pass marks, before any Jev answer for these 30 reviews existed.
- **Known answer reproduced:** the probe wording got 2 of the 4 planted slogans, reading S2 and S4 as `cancellation`. That is what the throwaway test of 2026-10-04 found (entry 6; the plan's gate table names the two cases), now through different code.
- **Result, planted slogans:** probe 2 of 4; candidate 4 of 4 (S1 and S2 `unclear`, S3 `cancellation`, S4 `complaint`).
- **Result, the 28 `tune` reviews the raters agree on** (24 `unclear`, 4 `complaint`): the probe's intent equals theirs on 15, the candidate's on 23. The probe read 12 of the 24 `unclear` reviews as `cancellation` and 1 as `complaint`; the candidate reads 5 as `cancellation` and none as `complaint`. All 4 `complaint` reviews are `complaint` under both. Intent changed on 10 of the 34 items.
- **Pass marks:** none missed. The candidate may replace the probe wording; Travis has not yet said so.
- **Not degenerate:** a wording that answered `unclear` to everything would also score well on reviews that are mostly `unclear`. The candidate still gives `cancellation` to S3, `complaint` to S4, and `complaint` to all 4 reviews the raters call complaints.
- **Calls:** 68 of 68 succeeded, every one HTTP 200 and naming `jev-1.13.0`, 0.14 s each on average. Input tokens 64,710; output tokens 14,535 (*measured*, from the responses).
- **Spend:** $0.0027 if only input tokens are billed; $0.0033 if output tokens are billed at the input rate, which is what the ledger recorded. The ledger now reads $0.0568 of $35: $0.0535 for the earlier probes ($0.0485 *measured*, $0.005 *estimated*) plus this trial.
- **Open at the time, settled in entry 24, output-token billing:** the usage page was not read before the trial, and the assistant cannot see it. No Jev call was made on 2026-10-05 before 15:20 PDT, so a page that shows the day, or token counts, still separates this trial. The two readings differ by $0.0006, which a page rounded to cents cannot show; if so, the 10,000 gate (about $0.41 against $0.50, *estimate*) is the first run large enough to settle it.
- **Evidence:** `evals/wording_trial_out.json` (each item's intent under each wording), `evals/wording_trial.py`, the two prompt files. The call log and ledger are in the state file, which is not committed.
- **Limits:** 34 items, one run. Only 4 of the real reviews are complaints, so this says little about whether the candidate moves real complaints to `unclear`; no ordinary review was tried. Every accuracy figure recorded before this entry was measured with the probe wording and does not carry over to the candidate. The 100 gate labels the pilot reviews again and is the first comparison of the two wordings on ordinary text.

### 24. Are Jev's output tokens billed

- **What:** after the wording trial Travis read the TypeSafe usage page: $0.056, 1,640,194 tokens, 1,451 requests, for everything this project has sent to Jev. A script with no model call asks which reading of those numbers fits what the responses themselves reported.
- **Independence:** the page is the provider's own billing record and the assistant cannot see it. The token counts come from the responses: the 257 requests of the first probe and the 68 of the trial are the only ones that saved their usage.
- **Result:** if the page counts input and output tokens and only input is billed, $0.056 buys 1,333,333 input tokens and leaves 211.5 output tokens a request, or 203.3 to 219.7 allowing for the page's rounding. The responses report 204.5 (202.0 on the probe, 213.8 on the trial), inside that range. If every token were billed at the input rate the page would show $0.0689. Output tokens are not billed.
- **A second anchor:** the earlier probes were costed at input tokens only, $0.0535, before anything was known about the page. Adding the trial's input tokens gives $0.0562. The page shows $0.056.
- **What changed:** `pipeline/billing.json` and `cost/rates.csv` price output tokens at zero, each with the reading in its note. The real ledger was corrected by one `adjust` row of minus $0.00061047, the output-token charge it had booked for the trial, and now reads $0.0562 of $35. The calculator's report now states that no cost is unknown.
- **Evidence:** `experiments/2026-10-05/billing/usage_page_check.py` and `usage_page_check_out.txt`; `tests/test_billing.py` reruns the arithmetic and fails if either reading's verdict changes.
- **Limits:** one reading, typed in by hand, with dollars to a tenth of a cent. 1,126 of the 1,451 requests saved no usage, so the output tokens per response are measured on 22% of them. A small charge for output tokens could hide in the rounding. The page is read again after the 10,000 gate, where billing every token would differ by about eight cents (*estimate*).

### 25. The 100-review pilot: every stage with the real models

- **What:** on 2026-10-05 at 17:53 PDT, with Travis's go, `python3 -m cost pilot --go` ran `cost_100.csv` through every stage on committed code (`1a0c0bc`): Jev with the frozen wording and one worker, stopped after 50 and resumed; Gemma 26B as the blind verifier on all 100, one review a request; Gemma naming the issues and writing the memo; then a warm pass and the export.
- **Independence:** the export is judged by the instructor's `check_submission.py`. The comparison with the earlier wording uses the probe's saved answers of 2026-10-04, made by a different script. The development labels are Travis's; the raters' shared answer is two outside models'. The golden 50 is not touched.
- **Pass marks from the plan, each as it fell:** 100 of 100 completed and none quarantined; checker `pass` with no flags; 50 completed before the stop and 50 after; the warm pass made 0 calls; all 100 Jev responses name `jev-1.13.0` and all 112 Gemma responses name `google/gemma-4-26b-a4b-qat`; Jev spend $0.0042, under $0.01; the verify report reads sample 100, predictions 100, failures 0, not labeled by Jev 0; the instructor's two calculator tests hold on the real evidence (doubling the rates doubles the API subtotal and leaves local cost and time alone; changing the row count leaves the measured results alone). Still Travis's: reading the feature list and the memo, and naming a provisional cut-off.
- **Known answers reproduced first:** read through the pipeline's own mapping, the probe's saved answers give what was recorded on 2026-10-04: 52 complaints or cancellations, severity sums 38, 29, 22 and 20, 26 flagged at 0.70, 24 of 29 development labels (21 as first written), 79 of 92 against the raters' shared answer.
- **The frozen wording on ordinary reviews:** against the probe wording on the same 100 reviews, topic changes on 0, intent on 1 (`praise` to `unclear`) and severity on 2 (one step down each). Still 52 complaints or cancellations and the same order of issues: usability 37, other 29, playback 22, billing 20. It flags 30 at 0.70. Against the development labels it scores the same 24 of 29 (21), and against the raters' shared answer the same 79 of 92.
- **Gemma at one review a request:** 24 of 29 development labels (21 as first written; topic 27, intent 29, severity 24) and 79 of 92 against the raters. 0.26 s a review, one at a time.
- **The two engines:** same topic, intent and severity on 83 of 100: 40 of 52 complaints and cancellations, 43 of 48 others. Of the 17 disagreements, 12 carry the review flag at 0.70.
- **The memo:** Gemma's memo was rejected by the code check three times and passed on the fourth attempt, across two runs of the pilot command. The check named money or revenue language once, a claim cited in a sentence that does not name its issue twice, and a number with no claim twice. The saved memo recommends the first-ranked issue and cites only numbers from the claims table; one of its two quotes is missing its closing quotation mark.
- **Cost and time, measured:** Jev 98,996 input tokens for 100 requests, 990 a request, $0.004158. Cold run 62 s end to end: classify 13.4 s, verify 25.7 s, naming 3.9 s, memo 19.3 s over its four attempts. Warm run $0 and no call.
- **Projection (*estimates*):** one full pass $20.39 with exact-text reuse, $21.41 with 5% retries, $27.35 with no reuse. Verifying 5,000 at 0.26 s each is about 21 minutes.
- **The comparison code:** with Jev's topic changed on purpose on 20 agreeing reviews in a copy of the state file, the comparison flags all 20.
- **Evidence:** `runs/pilot-cold/` (the run evidence and its `grading/` export), `cost/pilot_calls.jsonl`, `cost/pilot_records.jsonl`, `cost/usage.csv`, `cost/report.md`, and `experiments/2026-10-05/pilot-100/` (the gate's read, the v2 answers for the cut-off table, and the memo diagnosis).
- **Limits:** 100 reviews, one run, one worker. The file has no repeated text, so reuse of a saved answer by a copy has not happened with real data. The guards that need 500 reviews did not fire or get tested. The pipeline does not keep the text of a rejected memo: the two saved under `memo-diagnosis/` come from a read-only rerun of the same request outside the state file, whose token counts match the third and fourth attempts exactly. The first attempt of the first run had a different length from the first attempt of the second, so Gemma's output is not fully repeatable. A memo that passes only some of the time is a risk for the later gates.

### 26. The holdout, scored once

- **What:** on 2026-10-05 at 18:22 PDT, with Travis's go, `evals/holdout_score.py --go` sent the 30 boycott reviews held back since 2026-10-04 and the 25 planted cases to Jev with the frozen wording. 55 requests. The script refuses a second run.
- **Independence:** these 30 reviews were never used to tune anything. The reference is the answer the two outside raters share (28 of the 30), which is agreement with other models. The planted answers come from the contract.
- **Result, as it fell, holdout:** topic 28 of 28, intent 24 of 28, severity 13 of 28, all three 13 of 28. The four intent differences are reviews the raters call `unclear` and Jev calls `cancellation`. All fifteen severity differences are the raters' 1 against Jev's 2, eleven of them on reviews Jev itself calls `unclear`.
- **Result, planted cases:** 22 of 25. Contract rules 9 of 9, slogans 4 of 4, non-English 3 of 3, injections 3 of 4 (I3 moved the answer to topic `support`, intent `request`), no letters 3 of 5 (a thumbs-up and two hearts read as `unclear` where `praise` was expected).
- **Against the probe wording on 2026-10-04 (entry 6):** then 21 of 25, missing 2 injections and 2 slogans. The frozen wording gets both slogans and one more injection, and loses two emoji-only cases it had right. One review in the pilot's 100 moved the same way, `praise` to `unclear`.
- **A pattern the pipeline does not yet handle:** the contract gives severity 1 to praise, unclear content and pure requests. Jev gives 2 to many boycott slogans it calls `unclear`. Applying that fixed rule to Jev's labels by code would read 24 of 28 here. On the pilot's 100 ordinary reviews it would change 1 label of 48. At the time the code deliberately did not apply the rule to exported labels. Travis ruled the same evening that it should (entry 31).
- **Evidence:** `evals/holdout_score_prompt-v2.json`.
- **Limits:** scored once and never to be used to change the wording. If the severity rule is adopted, the 24 of 28 is not a clean held-back figure, because the pattern was seen here first. 30 reviews of one kind.

### 27. The rest of the cut-off half

- **What:** the cut-off half is 60 development reviews held back for choosing the review flag's cut-off. The pilot covers 32. `evals/cutoff_rows.py --go` labeled the other 28 once, with the frozen wording, and `evals/cutoff_table.py` then read all 60.
- **Result, flagged of 60, then differences from the raters' shared answer caught of 9, then agreeing answers flagged of 40:** 0.50: 6, 1, 4. 0.60: 18, 5, 10. 0.70: 23, 7, 11. 0.80: 26, 7, 13. 0.90: 36, 8, 20. Against Travis's own labels on 15 of these rows the flag catches 2, 5, 6, 7 and 9 of 11 differences. Of the 11 rows the two raters dispute it flags 1, 3, 5, 6 and 8.
- **Evidence:** `evals/cutoff_rows_out.jsonl`, `experiments/2026-10-05/pilot-100/pilot_v2_answers.jsonl`.
- **Limits:** 60 rows; 9 differences. Travis has not named the cut-off. 0.70 is the setting in use.

### 28. Which model writes the memo, and a fault in the memo check

- **Why:** on the pilot the local model needed four attempts to pass the memo check (entry 25). Travis asked whether the memo needs a local model at all: it is one call a run, about 6,000 input tokens.
- **What:** `experiments/2026-10-05/memo-model/bakeoff.py` sent the pipeline's own memo request for the pilot's evidence pack to Claude Sonnet 5.5, Opus 5.5 and Fable 5.1, twice each, with one retry as the pipeline does. Every answer was judged by the pipeline's memo check. The choosing rule was written in the script before any call: the cheapest model whose first attempt passes in both trials.
- **Result under the check as it stood:** four of six first attempts were rejected, and by that rule no model was chosen. Every rejection gave the same reason: a claim cited in a sentence that does not name its issue.
- **What the text showed:** the memos were right. Each named the issue and cited its numbers in the next sentence ("It ranks first, with a priority score of 37 [CL-004]"). Four different models wrote it that way. The check, not the models, was at fault: it was reading its own strictness.
- **The correction:** a claim's issue must be named in the same paragraph or list item. A number must still be the value of a claim cited in its own sentence. Three tests hold the rule to one of the saved memos: it passes as written, and is rejected when a claim is moved under another issue or a number is changed.
- **Result re-judged with no new call:** all six first attempts pass. By the rule the cheapest is chosen: Claude Sonnet 5.5, 6,051 input and about 1,000 output tokens, $0.022 and 7 seconds a memo. Opus 5.5: $0.06, 18 seconds. Fable 5.1: $0.14, 27 seconds. The local model's two saved diagnostic memos: one passes, one is still rejected for a number with no claim.
- **What changed:** `pipeline/claude.py` is the memo client. Memo calls reserve and settle in the spend ledger at the memo model's rates, against the same cap as Jev. `pipeline/billing.json` names the model and its rates. The text of a rejected memo is kept. The calculator prices the memo as API spend, added once.
- **Evidence:** `experiments/2026-10-05/memo-model/` (the script, all twelve memos, `bakeoff_out.json`, the evidence pack), `tests/test_memo.py` class `RealMemos`, `tests/test_paid_memo.py`.
- **Limits:** $0.79 was spent on Anthropic's API outside the pipeline's ledger. The re-judging was done after the rule was changed, by the person who changed it; the three tests are the guard against a rule loosened too far. The six memos were written under the earlier prompt line. Whether Sonnet's memo reads well enough is Travis's call. Sonnet, Opus and Fable share a maker with the assistant that built the pipeline.

### 29. The pilot again with the paid memo model, and Jev against itself

- **What:** a changed memo model means the pilot is run again. `python3 -m cost pilot --go --cold pilot2-cold --warm pilot2-warm` at 18:37 PDT on committed code (`3fd98a1`).
- **Result:** 100 of 100 labeled, stopped at 50 and resumed; checker `pass` with no flags; warm pass 0 calls; the pilot command ran once. Sonnet's first memo was rejected for naming revenue and churn in its limits; the retry passed. Both calls together cost $0.045. Cold run: Jev $0.004158, 64 s end to end. The instructor's two calculator tests hold with the memo counted as API spend. Projection (*estimates*): $20.44 with reuse, $21.46 with 5% retries, $27.40 with no reuse.
- **Jev against itself:** the two pilots sent Jev the same 100 requests about 45 minutes apart. Topic and intent are the same on all 100. Severity differs on 2, each by one step. The quoted sentence differs on 1 and the review flag on 3. The tone score differs on 69, by 0.005 at the median, 0.03 at the ninth decile and 0.115 at most, with no change of sign. The rerun of 2026-10-04 (entry 7) found 0 changes, with the probe wording. Gemma's 100 verify answers are the same in both runs.
- **What that means for the gates:** the plan's mark "reviews labeled at two gates keep their labels" cannot be met exactly. The `nested` command also compares the tone score exactly, so it lists 71 of 100 reviews, nearly all for a difference in the second decimal. Travis rules on both.
- **Evidence:** `runs/pilot2-cold/`, `cost/`.
- **Limits:** two runs of 100. The rate of change on a larger sample is unknown.

### 30. The 500 gate

- **What:** `checkpoint_500.csv` on committed code (`3fd98a1`), 16 workers, stopped after 250 and resumed with the same command, at 18:40 PDT with Travis's go.
- **Pass marks from the plan, each as it fell:** 500 of 500 completed, none quarantined; checker `pass` with no flags; 283 completed before the stop and 217 after; no 429 response in 479 requests; Jev cost per review $0.0000398 against the pilot's $0.0000416, within 4%; verify 500 predictions and 0 failures. **Not met as written:** of the 100 reviews also in the pilot, Jev's severity differs on 1 and the review flag on 2.
- **Copies:** the file has 479 distinct texts in 500 reviews. The 21 copies took their source's answer and the checker counts them as valid. This is the first reuse on real data.
- **Speed:** 479 requests in 6.7 s of session clock, 71.5 a second with 16 workers. A burst, not a sustained rate.
- **The two engines:** same topic, intent and severity on 363 of 500. On the 241 complaints and cancellations: 146, with topic the same on 208 and severity on 168. On the other 259: 217. The pilot's 100 read 82 here; the other 400 read 281, so the pilot's share was the high end.
- **Ranking:** usability 167, playback 143, other 135, billing 128. Playback and other have changed places since the pilot. 137 of 500 carry the review flag at 0.70.
- **Memo:** Sonnet's first attempt passed the check. $0.025.
- **Evidence:** `runs/gate-500/`.
- **Limits:** agreement between two models is not accuracy, but three complaints in ten get a different severity from the second engine, and severity is what the ranking adds up. No hand label has been compared at this size.

### 31. Two rulings coded: the severity rule and the nested check

- **What:** Travis ruled on 2026-10-05 that the contract's fixed severity rule applies to the pipeline's own labels, and that the nested check may be loosened. Both were coded test-first.
- **The severity rule, known answer:** counted before the code was written, 1 of the probe's 100 saved answers is `unclear` with a severity above 1 (review `9e3a706c`). A test requires the mapping to change exactly that review and no complaint or cancellation. At the 500 gate the rule would change 5 of 259 no-problem labels; Gemma's 256 already obey it. With it, the two engines agree on 365 of 500 instead of 363.
- **The nested check, known answer:** the loosened command was run on the real state file. The two pilots: 2 of 100 labels changed, quote 1, flag 3, tone score moved on 69 by at most 0.115. The 500 gate against the rerun pilot: 1 of 100, flag 2. These are the figures a separate script gave in entries 29 and 30.
- **The stop:** a gate stops when more than 5 in 100 shared reviews change topic, intent or severity. If Jev's true rate were 2 in 100, six or more changes in 100 would happen about 1.5 times in 100 by chance (binomial), so a stop means something moved. The number is the assistant's, under delegation.
- **Evidence:** `tests/test_jev_mapping.py` class `SeverityRule`; `tests/test_review_fixes.py` class `Finding6GateChecks`.
- **Limits:** the runs already exported (`pilot-cold`, `pilot2-cold`, `gate-500`) were made before the rule and keep their labels as exported. The rule was adopted after the holdout showed the pattern, so the holdout's 24 of 28 under the rule is not a clean held-back figure. The 5 in 100 rests on two samples of 100.

### 32. The 10,000 gate

- **What:** `analysis_10000.csv` on committed code (`9550b93`, code hash `e9b0197eaa14`), 16 workers, stopped after 5,000 new completions and resumed with the same command, at 20:12 PDT on 2026-10-06 with Travis's go. A dry run first said 8,448 requests and about $0.33.
- **Pass marks from the plan, each as it fell:** 10,000 of 10,000 completed, none quarantined; checker `pass` with no flags, coverage point 1.0; 6,534 completed before the stop and 3,466 after (5,015 requests, then 3,433); 73.8 requests a second in both sessions, against a mark of 50; 0 failed attempts and no 429 in 8,448 requests, against a mark of under 1%; verify 5,000 predictions and 0 failures; spend so far plus the projected full pass about $20.74 (*estimate*), against a mark of $24. The nested 500: 19 of 500 changed topic, intent or severity (3.8%), under the stop of 5 in 100 from entry 31.
- **The 19, split by cause, with a known answer:** entry 31 counted, before the code was written, that the severity rule would change 5 of the 500 gate's labels. Jev's saved raw answer is identical in both runs on exactly 5 of the 19, and all 5 are `unclear` or `request` going from severity 2 to 1. On the other 14 Jev's own answer differs: severity alone on 6, topic alone on 6, intent on 2 (one with severity). 11 of the 14 are a complaint or cancellation in one run or the other.
- **Every one of the 14 was a close call.** In each changed field the top probability is 0.55 or less in both runs, so all 14 carry the review flag in both runs. On answers that did not change, the top probability moved by 0.03 or less on nine in ten.
- **Jev against itself a day apart: 14 in 500 (2.8%).** Within an hour it was 1 to 2 in 100 (entries 29 and 30), and topic and intent never changed. Here topic changed on 6 and intent on 2. Against the rerun pilot's 100, 1 label changed.
- **Speed:** 5,015 requests in 68.0 s and 3,433 in 46.5 s of session clock. The longest stretch at this rate is now 68 seconds, up from 7. At 73.8 a second the full file's 484,189 distinct texts take about 1 hour 49 minutes (*estimate*).
- **Cost:** Jev $0.3525 for the run, 993.4 input tokens a request, $0.0000417 a request, within 1% of the pilot's rate. One full pass at this rate is $20.20 (*estimate*), or about $21.2 with 5% retries. Memo $0.0256, passed on its first attempt. The ledger reads $0.5359 of $35.
- **Copies:** 8,448 distinct texts in 10,000 reviews. The 1,552 copies took their source's answer and the checker counts every one as valid.
- **The two engines:** same topic, intent and severity on 3,495 of 5,000. On the 2,243 complaints and cancellations: 1,307, with topic the same on 1,969 and severity on 1,518. On the other 2,757: 2,188. The 500 gate read 363 of 500 and 146 of 241. Verify took 1,301 s, 0.26 s a review.
- **Ranking:** usability 3,311, other 2,661, billing 2,319, playback 2,296, catalog 622, access 620, downloads 331, support 24, from 4,479 complaints and cancellations. Places 2 to 4 have come out in a different order at each of the three sizes. Billing and playback are 23 apart in 2,300, and catalog and access are 2 apart. 2,878 of 10,000 carry the review flag at 0.70.
- **Will the full export fit in the repo?** Measured here, gzipped: `records.jsonl` 1.08 MB, `run_log.jsonl` 0.84 MB, `calls.jsonl` 0.67 MB. Scaled to the full file (*estimates*): about 71 MB, 31 MB and 24 MB, and `checkpoint_after.json`, which cannot be gzipped, about 29 MB. Each is under the 95 MB at which export refuses. The spec listed this as raised and unchecked.
- **Evidence:** `runs/gate-10k/`. The split of the 19 was read from `runs/state.sqlite` (the saved raw answers), which is not committed; the 19 themselves can be recounted from the two `records.jsonl` files.
- **Limits:** the speed is two sessions of about a minute, and the full pass is about a hundred times longer. Jev a day apart is one comparison of 500. The split of the 19 was made by the same assistant that built the pipeline. The usage page has not been read since this run, so entry 24's limit is still open; if output tokens are not billed it should read about $0.440, and about $0.524 if they are. Entry 30 names commit `3fd98a1` for the 500 gate; the state file records `40434d5`, and no file under `pipeline/` or `prompts/` differs between the two.

### 33. The pilot on the final code, Jev within the hour, and two things from Travis

- **What:** `python3 -m cost pilot --go --cold pilot3-cold --warm pilot3-warm` at 20:50 PDT on 2026-10-06 with Travis's go, on the code the full run will use (code hash `e9b0197eaa14`, the same as the 10,000 gate). The pilot in `cost/` until now was made before the severity rule.
- **Result:** 100 of 100 labeled, stopped at 50 and resumed; checker `pass` with no flags; warm pass 0 calls of any role; verify 100 predictions and 0 failures. Jev $0.004158 and 990 input tokens a request, as before. Sonnet's first memo was rejected for a number with no claim behind it; the retry passed; both calls together $0.0458. Cold run 58.4 s end to end. The projection is unchanged (*estimates*): $20.44 with reuse, $21.46 with 5% retries, $27.40 with no reuse. The ledger reads $0.5859 of $35.
- **Jev against itself, 40 minutes apart, same code:** the pilot's 100 reviews were also labeled in the 10,000 gate. Topic changed on 2 and severity on 2, so 4 in 100; the quote on 1 and the review flag on 2. The 2.8% of entry 32 is therefore not only a day-apart effect. Four comparisons now: 2 in 100 and 1 in 100 on 2026-10-05, 14 in 500 and 4 in 100 on 2026-10-06.
- **Memo first attempts:** rejected on 2 of the 4 real runs since the check was corrected (both pilots) and passed on both gates. A run whose memo is rejected twice ends unfinished, and the same command tries again.
- **The stop by hand, rehearsed:** every real stop so far used `--stop-after`. A stand-in run on the 10,000 file was stopped with a real interrupt signal after 6 seconds (2,958 completed), resumed with the same command and exported: checker `pass`, with that stop as the resume boundary. No cost.
- **Feature-word list (spec item 5):** Travis read the 45 words on 2026-10-06 and accepted the list as it stands.
- **Usage page:** Travis read it about half an hour after the 10,000 gate's Jev calls: roughly 9 cents, 2.5 million tokens, 2,200 requests. The ledger's side as of the end of 2026-10-05 is 2,213 requests and 2,559,498 tokens, and $0.088 if output tokens are not billed or $0.095 if they are. So the page lags by hours, its counts match the ledger as of the night before, and "roughly 9 cents" cannot tell the two cases apart.
- **Evidence:** `runs/pilot3-cold/`, `cost/`.
- **Limits:** entry 24's limit stays open. The plan's mark "usage page reconciled" before the full run is not met; Travis gave the go for the full run without it. If output tokens are billed the full pass is about $24.6 (*estimate*), still under the cap. Jev's rate of change rests on four comparisons of 100 to 500 reviews.

### 34. A rehearsal on the full file, and a statement that read every pending review

- **Why:** no run of any kind had used the full file. Every gate was 10,000 reviews or fewer, and the test that reads the full file is skipped by default.
- **What:** a stand-in run on the full file at 20:55 PDT on 2026-10-06 (`--standin`, no cost), 16 workers, `--stop-after 2000`.
- **What held:** prepare met its known counts in about 10 seconds: 660,622 rows, 13 empty, 484,189 distinct texts, 176,420 copies.
- **What did not:** classify saved 2,015 requests in 134.0 s, 15 a second. The same stand-in saved 1,490 a second on a 10,000-review file (entry 22).
- **Cause:** the statement that marks a finished text and its copies completed. Left to itself the planner took the status index and read every pending review of the run. Timed on the rehearsal's state file with 565,000 pending: 61 ms a request, against 0.005 ms through the text index. At 10,000 reviews the same read is about a millisecond, so no gate showed it.
- **What it would have cost:** time, not money and not labels. The state file, not Jev's limit, would have set the pace: about 4 hours for the full pass instead of 1 hour 49 minutes (*estimates*), with the calculator's 1.79 hours shown wrong by its own run.
- **Fix, test first:** two tests read the plan of the two statements that run per request (`tests/test_state.py` class `Plans`). Both failed, naming the status index. The statements now name the text index. 523 tests.
- **Known answer after the fix:** the same rehearsal resumed on the fixed code saved 30,015 requests in 13.6 s, 2,209 a second.
- **What changes:** the code hash is now `530c1e237f7c`, so the pilot is run once more on this code. No label can change: the fix alters how rows are found, not which rows or what is written.
- **The pilot on the fixed code**, at 21:04 PDT with Travis's go (`pilot4-cold`, `pilot4-warm`, commit `313757c`): 100 of 100, stopped at 50 and resumed, checker `pass` with no flags, warm pass 0 calls, verify 100 predictions and 0 failures, memo passed on its first attempt ($0.022). Jev $0.004158 again. 49.8 s end to end. Same ranking as the pilot an hour before; 2 of its 100 labels differ from that pilot's. `cost/` is built from this run. Projection (*estimates*): $20.42 with reuse, $21.44 with 5% retries, $27.37 with no reuse. The ledger reads $0.6123 of $35.
- **Evidence:** `tests/test_state.py`; `runs/pilot4-cold/`, `cost/`; the rehearsal is run `rehearse-full-1006` in `runs/standin.sqlite`, which is not committed.
- **Limits:** the stand-in answers at once, so this measures the state file and nothing else. No real run has used the full file. Verify, grouping, the memo and export have not been rehearsed at full size; a fault there costs time and no money, because every answer is saved by then. The plan tests hold the statements to the index; they do not measure speed.

### 35. The full run

- **What:** the full file, 660,622 reviews, on committed code (`c20aa34`, code hash `530c1e237f7c`), 16 workers. Travis started it in his own terminal at 21:09 PDT on 2026-10-06, stopped it by hand with Ctrl-C after 122 seconds, read `status`, and resumed with the same command. It ended at about 23:21 with no one watching. Every figure below is read from the export, not from the screen.
- **Pass marks from the plan, each as it fell:** wording and cut-off frozen first: yes. Usage page reconciled first: not met, as entry 33 says. Checker `pass`, `issue_counts` empty, `labelable_completion_fraction` 1.0: met. 660,609 completed and 13 quarantined, all 13 for empty text, which is the manifest's count. 131,072 completed before the stop and 529,537 after.
- **Jev:** 484,189 requests succeeded, one for each distinct text, which is the manifest's count; 176,420 copies took their source's answer. 24 attempts failed and each was sent again and succeeded: 16 timed out at 30 seconds and 8 came back HTTP 520. 23 of the 24 fell inside 40 seconds at 21:47 and one at 22:19. No 429. 0.005% of attempts failed, against the calculator's 5% in its careful case.
- **Speed:** 73.1 requests a second in the first session and 73.5 in the second, which ran 6,464 seconds. The fault of entry 34 would have read 15 a second. Classify took 1.83 hours of session clock; the calculator said 1.79 (*estimate*), because it assumes 75 a second.
- **Cost:** Jev $20.3386: 484,181,345 input tokens, 1,000.0 a request (the calculator scaled the pilot to 1,003; the 10,000 gate measured 993), plus $0.0029 kept for the 24 failed attempts, whose usage is unknown. Memo $0.0251, passed on its first attempt. Together $20.36 against the calculator's $20.42. The ledger reads $20.9760 of $35, which is the $0.6123 of entry 34 plus this run.
- **Verify:** 5,000 predictions, 0 failures, 1,239 s, which is the 0.34 hours the calculator said. Same topic, intent and severity on 3,523 of 5,000: 1,294 of 2,196 complaints and cancellations and 2,229 of 2,804 others. The 10,000 gate, on a different sample, read 3,495, 1,307 of 2,243 and 2,188 of 2,757.
- **Grouping and ranking:** 291,865 complaints and cancellations (266,793 and 25,072), each in exactly one of 8 issues; Gemma named all 8, none fell back. By severity sum: usability 212,158, other 175,815, playback 147,175, billing 141,482, catalog 45,210, access 40,751, downloads 23,427, support 1,945. `other` holds more complaints than usability (85,466 against 81,756) at a lower mean severity. Playback and billing are 4% apart. 191,158 of 660,609 carry the review flag (28.9%; the 10,000 gate read 28.8%).
- **Nested 10,000:** 258 of 10,000 changed topic, intent or severity (2.6%), under the stop of 5 in 100; the four earlier comparisons read 1 to 4 in 100 (entry 33). Severity alone on 105, topic alone on 98, intent alone on 39, two fields on 16. **All 258 carry the review flag in both runs.** 191 of them are a complaint or cancellation in one run or the other; 12 joined the complaints and 14 left. The quote changed on 53 and the flag on 390. Against the 500 gate: 18 of 500 (3.6%).
- **Export at full size, for the first time:** 45 seconds. `records.jsonl.gz` 71.7 MB, `run_log.jsonl.gz` 29.8 MB, `calls.jsonl.gz` 23.8 MB, `checkpoint_after.json` 29.1 MB; entry 32 estimated 71, 31, 24 and 29. The folder adds about 177 MB to the repo. Export also warned that `local-reference.json` is 161.5 MB: that file is in `.gitignore` and is never committed, so the warning asks for nothing.
- **Known answers:** the counts of rows, empty texts, distinct texts and copies are the manifest's. Complaints plus cancellations in `records` equal the members in `membership` and the sum of the ranking's counts. The script that counted the review flag reads the 10,000 gate as 2,878, the figure in entry 32. The ledger adds up as above.
- **The state file is backed up** for the first time: a `.backup` copy outside the repo, integrity check `ok`, the same 660,609 and 13.
- **Evidence:** `runs/full/`.
- **Limits:** one run, watched by no one. The usage page has not been read against it. The run's output tokens are 105,139,277, so the page should rise by about $20.34 if they are not billed and about $24.75 if they are (*estimates*); the two are now far enough apart for the page to settle entry 24. Whether Jev bills the 24 failed attempts is unknown. The golden 50 is not scored yet. The calculator's report still shows only its estimates; the comparison with this run is here and in the README. The nested split was made by the same assistant that built the pipeline.

### 36. The golden 50, scored once

- **What:** `python3 evals/score_golden.py --run full --records runs/full/grading/records.jsonl.gz` at 23:44 PDT on 2026-10-06 with Travis's go, after the full run's export was committed and pushed (`9586b39`), so the labels being scored were fixed before the score was seen. The golden file's SHA-256 was read first and is the frozen one (`b9d25cf2…`, entry 18). The script prints counts and review IDs only.
- **Known answers:** 50 rows and 0 with no prediction. The rule changes 4 golden labels, the count entry 19 made before any scoring.
- **Against the labels as frozen:** topic 40 of 50, intent 43, severity exact 40, **all three 30 of 50**. Severity error: mean +0.10, mean absolute 0.22. Tone score: mean absolute error 0.18.
- **With the contract's severity rule applied to the golden labels by code:** topic 40, intent 43, severity exact 38, all three 30. Severity error: mean +0.18, mean absolute 0.26. The rule moves four golden severities; three of those rows agreed before and do not now, and one is the other way.
- **Where it differs.** Topic: 5 of the 10 misses are reviews labeled `other` by hand that Jev put in catalog (3) or usability (2). Intent: 5 of the 7 misses are reviews labeled `unclear` by hand, which Jev read as a complaint (3), a cancellation (1) or a request (1); the other two are a complaint read as praise and praise read as unclear. Severity: 4 of the 7 hand 3s came out as 4.
- **What that means for the ranking:** of the 21 hand complaints and cancellations Jev found 20. It also counted 4 reviews that the hand labels call unclear, so 4 of its 24 are not complaints by hand. On this sample the complaint counts lean high, and severity leans high by a tenth to two tenths of a step.
- **The review flag:** it is on 9 of the 20 reviews with a wrong label and on 5 of the 30 with all three right. So a flagged review here is wrong about two times in three, and an unflagged one about one time in three.
- **Quotes:** 50 of 50 are exact copies of the review's text.
- **Evidence:** `evals/golden_score_full.json` (both readings, the three confusion tables, the 20 review IDs and their fields).
- **Limits:** 50 reviews, so 30 of 50 stands for somewhere between about 46% and 72%. One labeler; 10 of the 50 carry his note that the case is ambiguous. Thin by topic: 30 of the 50 are `other` by hand, 6 usability, 4 each for billing, catalog and playback, 1 each for access and downloads, none for support. It is lower than the development figure of 24 of 29, or 21 as first written (entry 4), which was scored with the probe wording on labels five of which were revised after seeing a model; the golden labels never were. This is the only accuracy figure the project has, and nothing was chosen or tuned on it.

### 37. The 20 golden misses read one by one, and what they say about the ranking

- **What:** at about 23:57 on 2026-10-06, after the score of entry 36 was saved and pushed, Travis allowed the golden label columns to be opened for the error analysis. The write-up was committed at 00:09 on 2026-10-07. The assistant that built the pipeline read the 20 reviews where a field differs, each against the contract's wording. No label and no score changed.
- **Saved case by case:** `evals/golden_cases_full.csv`, one row a review with the hand label, Jev's label and pass or fail per field in both readings. `evals/golden_cases.py` writes it and refuses unless its totals equal the saved score (five tests, written first). **Known answer:** it reproduces 40, 43, 40 and 30.
- **The 20 by kind:** severity one step apart 6 (Jev higher on 5), a topic boundary 6, text not in English 3, boycott or political text 3, short or doubtful praise 2.
- **The 20 by reading:** Jev plainly wrong 3; the contract's own wording favors Jev's label 4; the hand label is the guide's fallback for a language the labeler did not read 3; open under the contract 10. So 3 plain errors and 30 plain agreements in 50, with 17 in between.
- **The three plain errors:** premium-only controls put in usability where the contract says billing; lost controls read as a playback failure at severity 4; "Great..." read as unclear.
- **A what-if on the ranking, by code, no label changed.** 9,403 of the 81,756 usability complaints name Premium; 3,000 name Premium or a subscription with a control word. If every one of the 9,403 were billing, usability would still be first (186,455 against 175,815 for `other`) and billing would pass playback for third. The 3,000 alone give the same order. **Known answer:** the same script first reproduces the four severity sums of `ranking.csv`. First place does not rest on this boundary; places 3 and 4 do.
- **Quotes, read on all 50:** exact copies on 50. Of the 12 that are one sentence of a longer review, 11 carry the point of the label and 1 is cut mid-sentence at a line break in the source. Counted over the full file: 68 reviews hold a line break and 51 quotes are cut at one. **Known answer:** the count includes the golden review that showed it, and every partial quote was found in its source text.
- **Entities:** 21 on 15 reviews, all words in the text; one in a doubtful sense.
- **Evidence:** `evals/golden_error_analysis.md`, `evals/golden_cases_full.csv`.
- **Limits:** the readings are those of the assistant that built the pipeline being judged, and Travis has not confirmed them. The three translations are approximate. The Premium what-if uses feature-word matches as a rough marker, not a count of paywalled-control complaints. The golden labels are now known to the assistant, so nothing built after this can be scored cleanly on them.

### 38. The root `grading/`, the ranking rebuilt, one review traced, and what the final README claims

- **What:** on 2026-10-07, with no paid call. (a) `runs/full/grading/` was copied to a root `grading/`, the one folder the contract asks for. The contract's own commands name the full file as both `--full` and `--analysis`, and the coverage point is counted over 660,622 rows, so the full run's export is the one that belongs there. That settles the question the handoff left open. (b) The supplied checker was run on the root folder against `runs/full/local-reference.json`. (c) `python3 -m pipeline rank` was run on the root folder. (d) A new script, `evals/trace_review.py`, follows one review through the committed files (16 tests in `tests/test_trace.py`, written first). (e) The README got its rubric map, a traced review, the limits of the totals and the data links, and the stale status in `cost/README.md` was corrected.
- **Known answers:** the copy is the same file for file (`diff -rq`). The checker's output equals `runs/full/self-check.json` on all 17 top-level fields: `pass`, no flags, 660,609 valid completed, 13 quarantined, 176,420 valid reuses. After the rebuild `ranking.csv` has the SHA-256 the run manifest recorded (`5565cc5b...`). Three tests hold the trace to the full run: labels read earlier by separate throwaway code, and the memo and ranking files.
- **The trace can fail.** In a scratch copy, four breaks were each caught: a copy traced to itself (1 test fails), the verifier made to agree always (1), the row hash never compared (1), failed attempts dropped (3). The second is caught only by the full-run known answer; the stand-in test for it compares against the same expression, so it could not have caught it.
- **The traced review, picked by rule:** of the 5,000 sampled reviews, 599 are members of the first-ranked issue and have their own request. The first by review ID is `00d13536-bd53-4e93-9c76-22db75d384d5`. Jev: usability, complaint, 4, flag off. Gemma: other, request, 1. So the rule landed on a disagreement the review flag did not mark, and the README shows it as it is. The second by ID is one where both engines agree; it was not used.
- **The stop count is real.** 131,072 completed at the stop is 2^17, which looks like a cap. Rebuilt from the export: 8,939 `initial` requests succeeded; the reviews they labeled, originals and copies, number 131,072 and are exactly the IDs in `checkpoint_before.json` (8,939 originals, 122,133 copies); no `resume` request names one of them.
- **Enrich calls in the export:** 484,213, every one carrying one review ID; 8,939 `initial` and 475,274 `resume`; 24 failed.
- **Found while checking:** the GitHub repo answers signed out and its API reports it public, where the README, `CLAUDE.md` and the handoff said private until submission. `cost/README.md` still said the pilot had not been run. A scan of the tree, the whole history and the three gzipped exports finds nothing shaped like a key. 13 lines in `docs/independent-spec-review-2026-10-04.md` and `experiments/2026-10-04/` hold a home-directory path, and `runs/full/run_full_text.txt` shows the laptop's name in its prompt.
- **Evidence:** `grading/`, `evals/trace_review.py`, `tests/test_trace.py`, `README.md`. 545 tests, 1 skipped (16 for the trace, 1 that holds the README's memo quote to the memo file).
- **Limits:** the checker's pass is on files copied from a run it had already passed, so it shows the copy is whole and nothing new about the labels. The trace shows where one review went, not whether its label is right. The rubric map is the author's own reading of its evidence; no outside reader has checked it yet. `pipeline/` and `prompts/` are untouched, so the code hash is still `530c1e237f7c`.

## Rules adopted because of these checks

- **Label freeze.** A label file is committed and its SHA-256 recorded before model output for its rows is seen. A golden label does not change after the freeze; a plainly wrong one stays and the score is shown both ways.
- **Both scores, always.** Where labels were revised after seeing a model, the before and after scores are reported together.
- **Two readings of every hand-label score.** Hand labels stay as frozen. Scores are shown against them as written and with the contract's fixed severity rule applied to them by code.
- **Golden 50 is scored once**, on the final setup, and never used to choose an engine, a prompt or a cut-off. Its label columns were opened to the assistant only after that score was saved and pushed (entry 37).
- **Held-back halves.** The boycott sample and the development rows are split by hash, so wording is tuned on one half and scored once on the other.
- **Agreement is not accuracy.** Engine agreement is reported split by complaints against the rest.
- **Every check carries a known-answer test** where one exists: a count from the manifest, a score that an earlier script already produced, or rows where independent sources already agree.

## What all of this still does not show

- **One human labeler.** No second person has labeled anything, so nothing measures how firm the hand labels are. The instructor's private sample is the only human check from outside.
- **Small samples.** 29 hand labels, 25 made-up cases, 60 boycott reviews, 100 pilot reviews.
- **Single runs on one day.** No result here has been repeated on another day except Jev's rerun in entry 7.
- **One accuracy figure, from 50 reviews.** The golden 50 was scored once on the full run: all three fields right on 30 of 50, which stands for about 46% to 72% (entry 36). Per topic it says almost nothing.
- **Jev is not fully repeatable** (entry 29); the gate check now allows for it (entry 31). A day apart it changed 14 labels in 500, topic and intent among them, every one a close call that carries the review flag (entry 32); 40 minutes apart it changed 4 in 100 (entry 33); the full run changed 258 of the 10,000 gate's labels, every one flagged in both runs (entry 35). The two engines agree on only six complaints in ten (entries 30, 32 and 35), and nothing yet says which is right.
- **The order of places 2 to 4 rests on one pass.** It differed at 100, 500 and 10,000 reviews. On the full file it is other, playback, billing, with playback and billing 4% apart (entry 35). A second pass would change about 3 labels in 100, and whether that could swap the two is not tested. Counting usability complaints that name Premium as billing would swap them (entry 37).
- **One full run, made once** (entry 35). The usage page has not been read against it. Before it, the real runs were the wording trial (entry 23), four 100-review pilots (entries 25, 29, 33 and 34), the 500 gate (entry 30) and the 10,000 gate (entry 32). The code has had one independent reading (entry 22).
