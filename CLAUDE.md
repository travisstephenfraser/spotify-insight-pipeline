# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Travis's individual capstone, "Multi Agent Large Data Processing Pipeline", due 2026-10-13 23:59 PT. The pipeline turns 660,622 Spotify app reviews into a ranked list of product issues and a short decision memo, with every number traceable to saved evidence. The deliverable is one public GitHub repo whose README maps each rubric point to an evidence link.

**Both hand-labeled files are frozen as of 2026-10-05** (`evals/adjudication_sheet.csv` and `evals/golden_50_labeled.csv`; hashes and results under "Label freeze and blind human check" below). No golden label changes from here. **The spec is approved as of 2026-10-05** (section 12 has no open row; see "Spec approved" below). **The implementation plan is written** (`docs/superpowers/plans/2026-10-05-spotify-insight-pipeline.md`: 18 tasks in six phases, with proposed pass marks for each gate). **The pipeline is built (2026-10-05) on branch `build/pipeline`, tested with stand-in models only.** All 18 plan tasks are done, one independent reviewer has read the whole branch, and its findings are fixed (validation log entry 22); 521 tests pass (1 skipped: the full-file read). No real model call, pilot, gate or full run has been made with it. **The Jev cap is $35 as of 2026-10-05** (raised from $25 by Travis; spec item 34). The build landed on `main` by pull request 1 (merge `3ab3584`). **The wording trial ran on 2026-10-05 with his go, the candidate passed every pass mark, and Travis froze `prompts/enrich-v2.json` as the wording** (validation log entry 23). **Jev's output tokens are not billed** (entry 24, from his reading of the usage page). See "Wording trial" below. **The 100-review pilot ran on 2026-10-05 with his go: 100 of 100 labeled, the supplied checker passes, the warm pass made 0 calls** (validation log entry 25; see "100-review pilot" below). **Later the same day, on his go: the holdout was scored, the memo moved to Claude Sonnet 5.5, the pilot was rerun and the 500 gate ran; both exports pass the checker** (validation log entries 26 to 30; see "Evening of 2026-10-05" below). He has since ruled on all three open items listed there, and named the cut-off: 0.70. **The 10,000 gate ran on 2026-10-06 with his go and met every pass mark** (validation log entry 32; see "10,000 gate" below). **Later that evening the pilot ran once more on the final code, he accepted the feature-word list, and he gave the go for the full run** (validation log entry 33; see "Before the full run" below). **The full run finished on 2026-10-06 at about 23:21: 660,609 labeled, 13 empty quarantined, checker `pass` with no flags, $20.36, nested check 2.6%** (validation log entry 35; see "The full run" below). **The golden 50 was scored once on the full run, with his go: all three fields right on 30 of 50** (validation log entry 36; `evals/golden_score_full.json`). **On 2026-10-07 the root `grading/` was added (a copy of the full run's export; the checker passes on it) and the README got its rubric map, a traced review and the limits of the totals** (validation log entry 38; see "Final documents" below). **The GitHub repo was found already public that day.** Next: his reading of the usage page, his read of the memo and of the error-analysis readings, a license, an outside review of the whole repo, then the portal.

**State as of 2026-10-04:** no pipeline code exists. The repo's remote is `git@github.com:travisstephenfraser/spotify-insight-pipeline.git`, private until Travis flips it public for submission. The design is being agreed one decision at a time. Update this section as stages land, and add the pipeline's own run and test commands under Commands when they exist. The decisions below are in the order they were made; later entries supersede earlier ones.

**The repo was found public on 2026-10-07** (it answers signed out; when it was flipped is not recorded here). The reread is still owed: this file, `docs/` and `experiments/` for anything personal, and whether the course brief in `feed/` should be published. Handoff notes (`feed/HANDOFF-*.md`) are gitignored and stay on the laptop.

Decisions Travis has confirmed so far:

- Stage 2 (classify) is decided by a race on the 100-review pilot: Jev against local Gemma 26B-A4B 4-bit. A small cloud model joins only if both disappoint.
- Runs are time-boxed sessions (for example `--max-hours 8`) that save after every request and resume with the same command. Reviews are processed in a fixed shuffled order so each finished session is a fair sample of the file. State lives in one SQLite file.
- Jev side: one request per review with topic, intent and severity as choices and sentiment as a 5-step score. Option order is shuffled in a repeatable way derived from the review text. Code supplies entities (fixed feature-word list) and `needs_review` (low top probability or disagreement between two option orders). The quote is the whole text for single-sentence reviews; for multi-sentence reviews code splits sentences and Jev picks one in the same request.
- Golden labels: Travis fills `evals/golden_50_labeled.csv` using `evals/golden_labeling_guide.md`. Never read that file's label columns into context, and never open `.env`; scripts read both and report shapes, counts and row numbers only.

- Gemma side: 10 reviews per request.
- Hold: this is spec stage. Build nothing and run no local model or Jev call until Travis has ruled on the red-team findings. `.env` holds `CF_ACCOUNT_ID` and a token created for this project.

Red team, 2026-10-04: six independent checkers, 65 claims, verdict **Reshape**. Full report in `docs/red-team-plan-2026-10-04.html`. Findings that bind the design:

- The cost pilot must run all six stages, so the Jev-versus-Gemma race is a separate, budgeted experiment with its own result cache, not the pilot.
- 50 golden labels cannot both choose the winner and grade it (a 10-point gap needs 132 to 313 labels; choosing and grading on the same set inflates the score 2 to 3 points). Choose on a separate labeled development set, or disclose a direction-only choice.
- Jev through Cloudflare is capped at 200 requests per 60 seconds per gateway, about 40 hours per pass over the unique texts. TypeSafe's direct API documents 80 requests per second.
- Jev's docs say multi-step rules cost accuracy and advise narrow sub-questions with precedence in code. Identical requests can return different answers, and the version cannot be pinned through Cloudflare; log the `model` field from every response.
- Data traps: review-bombing bursts in July and October 2023, thousands of bare boycott slogans (contract says `unclear`), 12,268 nonempty reviews with no letter or digit that must still be labeled, and 13 reviews whose text is the literal `None`.
- Sorting all rows by SHA-256 of `seed:review_id` (seed in `manifest.json`) puts the golden 50, cost 100, 500 and 10,000 at the front in exact order. That is the run order.

Reshaped plan, approved by Travis on 2026-10-04 after he obtained a direct TypeSafe key (this supersedes the earlier Jev-through-Cloudflare decisions above):

- All Jev calls go to TypeSafe directly: `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer`, with a pinned `model` such as `jev-1.13.0`. Documented limits are 80 requests and 100K tokens per second, changeable without notice. The response carries `model`, `answers` and `usage`; log `model` on every call. The key is in `.env` (currently named `TYPESAFE_API`; the brief's name is `TYPESAFE_API_KEY`).
- Both engines get built. A race on hand-labeled development reviews picks the labeler (Jev or Gemma 26B); the other becomes the blind second opinion. Tie rule: if the gap is inside the noise, the faster engine labels.
- Jev's questions are narrow and literal, judged per sentence for multi-sentence reviews; code picks the most severe sentence (first on ties) so topic, severity and quote come from the same sentence.
- A Jev pass over everything runs early whichever engine wins (after the 100, 500 and 10,000 gates). It gives a draft ranking for building the later stages, and it is the second opinion on every review if Gemma labels.
- No fallback model. Hard cases are flagged where the two engines disagree, never re-labeled.
- Development labels: `evals/dev_150_labeled.csv` holds the 100 pilot reviews then 50 keyword-picked for rare topics (groups in `evals/dev_sets.json`). The golden 50 is scored once, on the winner only.

Measured in a throwaway Jev probe on 2026-10-04 (the 100 pilot reviews, direct route, `jev-1.13.0`, one request at a time): 257 requests, none failed, median 0.12 s each, about 8 requests per second. One broad-question request per review averaged 926 input tokens; the per-sentence style took 157 requests at 871 tokens each. Total spend $0.0097.

First head-to-head, 2026-10-04, on Travis's 29 development labels (sheet rows 2 to 30), throwaway code, matched definitions, Gemma at 10 per request:

| Engine | Topic | Intent | Severity | All three |
|---|---|---|---|---|
| Jev, one broad question per label | 28/29 | 28/29 | 26/29 | 24/29 |
| Jev, per sentence | 27/29 | 28/29 | 25/29 | 23/29 |
| Gemma 26B | 25/29 | 29/29 | 26/29 | 23/29 |

Too few labels to call a winner. Five labels were revised toward the contract after Travis saw Jev's answers (logged in the sheet's notes column), which tilts this toward Jev. Jev and Gemma gave identical topic, intent and severity on 77 of 100 reviews; on the labeled rows where they agreed (22), the shared answer matched Travis on 21. Gemma labeled 100 reviews in 54 s with one non-exact quote.

Three foundation tests, 2026-10-04 (throwaway code, about 4 cents of Jev calls):

- Tricky made-up reviews (25, expected labels written from the contract): Jev 21 right, Gemma 23. Jev was moved by instruction-like text in 2 of 4 injection cases and read boycott hashtags as `cancellation` in 2 of 4 slogan cases. Gemma got all 8 of those right, missed one premium-versus-playback topic and one emoji severity.
- Repeatability on the 100 pilot reviews: Jev changed 0 answers on a rerun. Gemma changed 1 with the same request grouping and 15 when the same reviews were regrouped into different requests, so a Gemma label at 10 per request depends on its neighbours. This reopens the 10-per-request decision; one review per request ran at about the same speed in the first probe.
- Jev parallel speed on 500 reviews: 60 requests per second with 8 workers, 78 with 16 workers capped at 80, no errors or rate-limit responses. A 6-second burst only; sustained speed is unmeasured.

**Ruling by Travis, 2026-10-04: Jev is the primary classifier**, chosen for cost and speed on the evidence above, and testing is stopped. This replaces the race: Gemma 26B becomes the blind second opinion. The ruling matches the tie rule (gap inside the noise, so the faster engine labels). Known Jev weak spots the design must guard and test: boycott hashtags read as `cancellation`, and instruction-like text moving the answer. No full run yet; the spec is still being agreed.

**Design part 2 approved by Travis, 2026-10-04**, one setting at a time, all five as presented:

1. Labeler: Jev `jev-1.13.0`, simple style, one request per review, with Jev picking the evidence sentence on multi-sentence reviews (25 of the 100 pilot reviews). Known limit, accepted: the quote and the topic come from separate questions and can point at different sentences; how often is unmeasured. This supersedes the per-sentence bullet in the reshaped plan above.
2. Speed: one request at a time for the cost pilot, then up to 16 at once capped near 75 per second. That is about 69K tokens per second (estimate; 72K was measured at 78 per second) against a documented 100K. Sustained speed is unmeasured until the 10,000 gate. What the run does on a rate-limit response is still to be written in the spec.
3. Second opinion: Gemma 26B, blind, on a random sample of 5,000, one review per request. Gemma's accuracy at one per request is unmeasured and gets scored on the development labels at the 100 gate. Only these 5,000 reviews can be flagged by disagreement.
4. Review flag: `needs_review` is true when the lowest of Jev's three top probabilities (topic, intent, severity) is below a cut-off. Travis picks the number later, on development labels only, once more of the 150 rows are labeled. This drops the earlier two-option-orders idea.
5. Weak spots: tightened intent wording for slogans, plus planted slogan and injection tests kept in `evals/`. Injections get a test only, no guard; the README reports the measured miss rate as a known limit. The new wording is unwritten and untested, and trying it is a paid call that needs a go.

Read of the saved pilot answers for setting 4 (no new calls, `flag_probe.py`), using the lowest of the three top probabilities per review:

| Cut-off | Flagged, of 100 | Jev mistakes caught, of 5 | Right answers flagged, of 24 | Jev-Gemma disagreements caught, of 23 |
|---|---|---|---|---|
| 0.6 | 17 | 2 | 1 | 8 |
| 0.7 | 26 | 4 | 4 | 13 |
| 0.8 | 38 | 4 | 8 | 18 |
| 0.9 | 54 | 5 | 11 | 21 |

Too thin to fix a number (29 labels, 5 mistakes, five labels revised toward Jev).

Design part 3, walked through one decision at a time on 2026-10-04:

- **Grouping, decided by Travis:** one issue per topic is the baseline (eight issues at most). Code assigns each `complaint` or `cancellation` review from its saved topic; the group model only names and describes each issue from a bounded sample of quotes. Sub-issues inside a topic (a proposed list Travis signs off, then one extra Jev question per complaint, about 250,000 requests and roughly $10 by estimate) are an optional later step, decided after the early Jev pass and before the final export, because they change issue IDs. On the 100 pilot reviews Jev called 52 complaints or cancellations, and `other` ranked second by severity sum (usability 38, other 29, playback 22, billing 20), so the baseline carries one issue with nothing specific to fix.
- **Writing model, decided by Travis:** Gemma 26B writes both the issue names (group role, at most 8 small calls) and the memo (one call), each with its own instructions. No model has written either yet, so quality is unmeasured. Review point: Travis reads the memo from the 100-review pilot and rules then on keeping Gemma 26B or switching the memo model; a switch means the pilot reruns. LM Studio also lists Gemma 31B (speed and memory on this laptop unknown); no cloud key is in use.
- **Budget cap, decided by Travis: $25 of total Jev spend for the project** (raised to $35 on 2026-10-05, see the build section below), held in the spend ledger (reserve worst case before each request; stop admitting work when spent plus reserved plus the next reservation would pass the cap; save and resume). Projected from the measured $0.0039 per 100 reviews: gates about $0.41 together, one full pass over 484,189 distinct texts about $19, leaving about $5. The cap does not cover a second full pass (about $19) or sub-issues (up to about $10); either needs Travis to raise it. So the intent wording must be settled before the full pass, because any prompt change is a new `label_config` and new work. Retries are unmeasured.

All three parts of the design are now decided. The written spec is `docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md`, **drafted 2026-10-04 and awaiting Travis's review**. It marks every line as Decided or Proposed, and its section 12 lists the proposed items that still need his ruling. After his approval comes the implementation plan.

**Every check run so far is listed in `docs/validation-log.md`** (what was checked, why the checker counts as independent, the result, the evidence file, the limit). Add an entry there whenever a check runs; the final README cites it for the testing and evaluation points. `docs/spec-review-2026-10-04.md` holds the spec reviewers' briefs and reports as written and the outcome of every finding.

`docs/independent-review-brief.md` is a single file to point a fresh reviewer at: instructions, a list of files it must not open, and a copy of the spec with the earlier reviews' summaries and the known-weakness lists removed. Its header records the hash of the spec it was copied from; rebuild the copy when the spec changes. It is meant for a reviewer from another maker, run where this file is not loaded automatically. If you are that reviewer and this file was loaded, set it aside as the brief says.

Independent review of the spec, 2026-10-04 (three readers: measurement validity, contract and checker, state and spending; all the same model family as the author). Fixes the sources dictate are folded into the spec and listed in its section 13. Thirteen real choices were added to section 12 as items 17 to 29, so it now holds 29. What the review established, each checked against the files:

- The first draft's resume rule would have been flagged: the full pass (about 1.8 hours, estimate) fits in one session, so `before` would equal `after`. The full run must be stopped once on purpose.
- The development labels lean toward Jev. Rows were revised only where a model disagreed (21 of 29 on all three fields before, 24 after). Sheet row 29 still carries severity 4 where the labeling guide says 3, and it scores as a Jev hit because Jev made the same call.
- Jev and Gemma agree on 43 of 48 non-complaints but only 34 of 52 complaints and cancellations on the pilot 100. Billing severity sum is 20 from Jev and 9 from Gemma; usability 38 against 55. The top four topics keep their order.
- A request body is 2.46 to 2.93 bytes per input token, and Jev reports about 215 output tokens per response whose billing is unknown.
- The golden labeling guide's last line allowed changing a label after scoring, which conflicted with "scored once" (spec item 19).

Rulings by Travis on the review items, 2026-10-04:

- **Item 19, label freeze: yes.** A label file is committed and its SHA-256 recorded before model output for its rows is seen. After the freeze no golden label changes; a plainly wrong one stays and the score is shown both ways. The guide's last lines were rewritten to say this. The development sheet as it stands is commit `bb5f440`, SHA-256 `febbfaeea4ed9a0034ce8ee9e6cf9fb0f283515d2469a41520dbd93a00cd6dd6` (29 rows labeled, five revised after seeing Jev). The golden sheet was frozen on 2026-10-05: commit `dcab9ff`, SHA-256 `b9d25cf271d921ec0a2545d2ca4a3ad8655e3b7056ac492b5a0458c5e4f2b79d`.
- **Item 27, output-token billing: settle it with a test batch** (send a small known batch, compare the TypeSafe usage page with input tokens times the rate). Unknown until then.
- **Outside raters (spec item 30): approved.** Fable 5.1 (Anthropic) and Astra 6 (OpenAI's top model) label reviews blind as third-party raters. Budget: **$10 per provider, a hard cap**, separate from the Jev cap ($25 then, $35 from 2026-10-05). Travis adds `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` to `.env`. Conditions: the raters see only the review text and the contract's label section word for word, nothing from Jev, Gemma, Travis or the assistant's paraphrases; their labels are for tuning and for marking disputed rows, never for accuracy claims; the golden 50 stays Travis's by hand and is frozen before any rater sees those texts; the write-up discloses that Fable 5.1 shares a maker with the assistant that wrote the spec. Each paid run still needs its own go.
- **Item 20, the 29 development labels already seen: keep them as they are.** Always report both scores (21 of 29 against the originals, 24 against the revised). They are no longer used to pick the cut-off. The outside raters label them blind to show whether the five revisions were fixes or drift.
- **Item 24, cut-off evidence: agreed.** The raters label all 150 development rows blind. Travis hand-labels only the rows where the two raters disagree, plus about 15 random rows where they agree (to measure how often an agreed label is wrong), without seeing the raters' answers. The rows are then split by hash into a wording half and a cut-off half.
- **Item 23, slogan cases: agreed.** 60 real reviews containing "boycott" are picked by hash and go through the same process; wording is tuned on 30 and the other 30 are scored once. The planted injection cases stay, with the raters confirming the expected answers.
- Items 17, 18, 21, 22, 25, 26, 28 and 29 are unruled.

**Outside-rater pass finished, 2026-10-04, medium effort, each step with Travis's go.** Evidence and full tables: `experiments/2026-10-04/README.md` and `outside-raters/compare_raters_out.txt`.

- Both raters labeled 235 of 235 with no refusals. Spent: Fable 5.1 $1.12, Astra 6 $2.77, of $10 each. Room is left for the 50 golden texts.
- They give identical topic, intent and severity on 210 of 235 (development 131 of 150, boycott 56 of 60, planted 23 of 25). Every severity difference is one step.
- Against the 29 hand labels each matches 25 as the labels stand and 21 as first written. Both give the revised value on all five revised rows, so the revisions were fixes by this measure. The four remaining differences are all severity (sheet rows 5, 19, 24, 29), with both raters below the hand label.
- Planted cases: Fable 24 of 25, Astra 25 of 25, including every injection and slogan case.
- Real boycott reviews: 52 or 53 of 60 are `unclear` to the raters, 6 or 7 `complaint`, 1 `cancellation`.
- Saved Jev and Gemma answers on the pilot 100, against the answer the two raters share (92 reviews): Jev 79, Gemma 77 on all three fields. Agreement with other models, not accuracy.
- **Done 2026-10-05:** Travis labeled `evals/adjudication_sheet.csv` blind (39 reviews: 23 where the raters differ, 1 planted case, 15 agreed checks, mixed). It was committed and hashed before he saw any rater answer for those rows. Results are under "Label freeze and blind human check" below.

Earlier steps of the same pass: 10-review test batch run at low effort with Travis's go, then the same 10 at medium. Measured: Fable 5.1 labeled 10 of 10 at $0.0041 each (projected $1.16 for 285); Astra labeled 10 of 10 at $0.0097 each (projected $2.78). No refusals. They matched on topic, intent and severity on 7 of 10. At low effort neither spent more than a few tokens thinking (31 and 43 output tokens per answer). A second test of the same 10 at medium effort, also with his go: Fable $0.0051 each (projected $1.50), Astra $0.0119 each (projected $3.49); the raters again matched on 7 of 10; Fable's answers were identical at both settings, Astra changed 1 of 10. Spent so far: $0.09 and $0.22 of the $10 caps. Both keys are now in `.env`. Answers are saved per effort setting, and all settings count toward the cap.

- Models and rates, checked against the makers' pages on 2026-10-04: `claude-fable-5-1` and `gpt-6-astra`, both $10 input and $50 output per million tokens. Thinking is billed as output on both, so cost depends on the effort setting and is unmeasured.
- `evals/boycott_60.csv`: 60 real reviews containing "boycott", picked by hash among 1,873 distinct eligible texts (3,484 rows contain the word, matching the red team's count), 30 marked `tune` and 30 `holdout`. No golden or development review is in it.
- `experiments/2026-10-04/outside-raters/raters.py`: one review per request, the contract's label section copied word for word (2,522 characters, SHA-256 starting `21b37d5f43750bc9`), standard library only, dry run by default. It rates 235 reviews now (150 development, 60 boycott, 25 planted) and leaves room in the budget for the 50 golden texts later. It stops at the $10 cap and stops after ten rows if the projection would pass it. No fallback model: a refusal is saved as a refusal so each file is one rater's work.
- Dry-run estimate for 285 rows per provider: about $3.70 if answers average 100 output tokens, $6.55 at 300, $12.25 at 700 (estimates; the last would trip the cap).
- `.env` now holds three key names: `TYPESAFE_API_KEY` (renamed, so spec item 15 is done), `ANTHROPIC_API_KEY`, and `OPEN_API_KEY`. The brief's name for the last is `OPENAI_API_KEY`; the script reads either. Nothing is built and no model is called until he approves those and gives a go for each gate.

**Second independent review of the spec, 2026-10-04, from another maker** (Codex, model `gpt-6.1-sol`, given only `docs/independent-review-brief.md`). Report: `docs/independent-spec-review-2026-10-04.md`. Its own session log shows it opened no excluded file, and Travis's prompt named the brief and nothing else. It made 13 factual claims; all 13 were confirmed by quoting the line or rerunning the test (evidence in `experiments/2026-10-04/review-checks/`). It rated eight as blockers; none stops the design. The fixes are folded into the spec (section 13, second review). Travis ruled on both items it left open the same day. **Item 13:** a failed call with no usage is exported with zero token counts plus `usage_known: false`, and the README counts such calls and calls the usage totals incomplete (zeros pass the checker; missing counts are flagged). **Item 31:** a resume under a different code commit is refused unless it is allowed by name and logged; whether to compare the whole package or only the labeling code is left for the implementation plan. `docs/build_review_brief.py` rebuilds the brief's copy of the spec.

**Corrections to numbers recorded earlier in this file.** The saved outputs were right; the wording here was not.

- **Gemma 26B speed.** One review per request with one worker: 0.64 s per review (20 reviews). The 0.57 s figure was 50 reviews per request, and 0.27 s was 10 per request with four workers (40 reviews). Four workers at one review per request was never timed. Wherever this file says "0.57 s per review with one request at a time and 0.27 s with four", read it this way. Verifying 5,000 one at a time is about 53 minutes (estimate), not 48, and the 23-minute figure has nothing measured behind it. Travis approved the second-opinion setting on the earlier wording. The setting does not depend on the difference, and he was told on 2026-10-04.
- **Jev probe spend.** $0.0485 measured plus about $0.005 estimated, not "$0.053 measured".
- **Sentence pieces.** At most 39 per review with the probe's splitter. The 164 came from an older splitter.
- **Checker facts measured on made-up exports.** Stopping with only copies pending, or with a pending original that later fails, raises `resume_call_evidence`. A failed call without token counts raises two `invalid_usage` flags; zeros pass and are summed with no mark. An input with no complaints can never pass (`missing_claims`).

**Label freeze and blind human check, 2026-10-05.** Validation log entries 16 and 18. Evidence: `experiments/2026-10-05/`.

- **Blind sheet frozen:** commit `634c05c`, SHA-256 `47ce41508e911455179a983f12f9e105c31129fae0450f790b6f46bf798e9274`, 39 of 39 rows filled. Committed before any rater answer for those rows was shown.
- **Golden 50 frozen:** commit `dcab9ff`, SHA-256 `b9d25cf271d921ec0a2545d2ca4a3ad8655e3b7056ac492b5a0458c5e4f2b79d`, 50 of 50 rows filled, every quote an exact copy. Frozen before any model saw the texts. Nine cells were blank at the first check and were filled before the freeze (quotes on eight short reviews, one needs_review); one entities cell also changed. No score was shown in between.
- **Import:** `experiments/2026-10-05/labels/import_numbers.py` exports a copy of the Numbers document, fills the CSV by review ID and prints row numbers, column names and counts only. It opens a window in Numbers for about a second, so never run it while Travis is typing there.
- **The 15 agreed checks:** Travis's label equals the raters' shared answer on all three fields for 4 of 15 (topic 12, intent 12, severity 5). A label both raters share does not stand in for his label, least of all on severity.
- **The 23 disputed rows:** his label equals Fable's on 3, Astra's on 3 and neither on 17.
- **Each rater against him, 38 real reviews:** Fable 7 on all three (topic 26, intent 31, severity 16); Astra 7 (topic 23, intent 32, severity 13). His severity is below Fable's on 15 and above on 7; below Astra's on 16 and above on 9.
- **A pattern in his labels:** all 8 boycott reviews he called `unclear` carry severity 2. The contract's severity 1 covers "neutral/unclear content" and the labeling guide gives a boycott slogan severity 1. Four of the 11 agreed-check differences are this alone; set aside, the agreed checks would read 8 of 15. The labels stay as frozen.
- **Planted case R1** (paying user, music stops): expected `playback`, `complaint`, 3; his label is `billing`, `complaint`, 2.
- **Ruling by Travis, 2026-10-05 (spec item 32): labels stay frozen, scores shown two ways.** Every score against hand labels is reported against the labels as written, and again with the contract's fixed severity rule applied to the hand labels by code (intent `unclear`, `praise` or `request` means severity 1). No model answer enters the second reading. He raised tuning the sheets after seeing the result; that was set aside because he had by then seen the raters' answers.
- **Count-only check, run with his go** (`rule_check.py`, validation log entry 19): the rule would change 8 of 39 blind-sheet labels, 0 of 29 development labels and 4 of 50 golden labels, all `unclear`. With it applied the agreed checks read 8 of 15 and the disputed rows Fable 4, Astra 5, neither 14.
- **Not covered by any rule:** his habit of giving severity 2 where the raters give 3 on complaints. It is disclosed as it stands. He said on 2026-10-05 that on review he agrees with the raters' severity.
- **Which labels the cut-off is tuned against:** a label both raters share equals his on 4 of 15 (8 by rule), and item 24 was decided before this was known. Ruled under delegation at item 4 (below): he picks the number from a table that shows every reference side by side.

**Spec approved, 2026-10-05.** Travis approved item 17 himself, then said: "Approve and run. No need to check in with me. We can speed this process up. I just want to get an executive summary report with anything high-level I should know about the steps once they're all completed." The assistant then ruled on every row still open in the spec's section 12. Those rows are marked Delegated, so they can be told apart from his own rulings. No row is open.

- **Accepted as written:** items 1, 2, 3, 8, 9, 10, 11, 12, 14, 21, 22, 26, and the two parts of 27 that were still proposed.
- **Accepted with something added:** item 4 (he still names the cut-off; the table he picks from shows every reference side by side, and rows the raters dispute are a group on their own); item 6 (the assistant drafts the slogan wording alone; the trial still needs his go); item 7 (reviews whose requests keep failing are listed, and a named command, run only on his call, quarantines them so the export is not blocked); item 25 (if the nested 100 differ between gates the run stops and he rules); item 28 (the implementation plan lists each gate's pass marks).
- **Item 5, feature-word list:** the process is accepted and the contents are still open. The assistant drafts the list from word counts; he reads it when he gives the go for the 100 gate.
- **Item 18, the deliberate stop:** both. `--stop-after N` is built for the tests, the run also stops cleanly on Ctrl-C, and the recorded full run is stopped by hand.
- **Human-only, still to do:** item 16 (send the two instructor questions) and item 29 (look for a spending limit in the TypeSafe console before the first paid pipeline call).
- **What the delegation does not cover, on the assistant's reading:** money, model calls and the build. Every paid call and every gate still needs his explicit go, and so does starting the build. He did not re-rule on those, and the summary report tells him so. The report is `feed/exec-summary-2026-10-05.html` (not committed).

**Implementation plan, 2026-10-05.** `docs/superpowers/plans/2026-10-05-spotify-insight-pipeline.md`. It gives exact files, interfaces, the schema, the export rules read from the checker, and named tests for 18 tasks. It does not carry finished code for every step, which the plan-writing skill asks for: Travis asked for speed and the build needs his go, so code is written test-first when each task is executed. The gate pass marks in it are proposed under the delegation; he confirms or changes them when each go is asked for. One fact checked while writing it: sorting by SHA-256 of `seed:review_id` with the seed in `manifest.json` under `samples.seed` reproduces the file order of `cost_100.csv`, `checkpoint_500.csv` and `analysis_10000.csv`, and puts every golden ID first.

**Outside review of the plan, 2026-10-05** (validation log entry 20; `docs/plan-review-2026-10-05.md`). Travis pasted in a review with seven blocking issues and five smaller points. Each was checked against the plan, the fixtures and the checker before anything changed; all seven held and are fixed in the plan. Four also changed the spec (item 33): the code is identified by a hash of `pipeline/*.py` and a real run needs a clean tree; each ledger row keeps the rates in force when it was written; `usage.csv` carries the pilot's clock seconds; a guard still raises for every input but another input can be restarted with the guard accepted by name. Facts worth keeping: the four planted slogan cases expect `unclear`, `unclear`, `cancellation`, `complaint`; Jev's sentence question is named `evidence` in the saved answers; Jev's tone score is a real number from 0 to 4; every gate run must be stopped once and resumed or the checker flags it.

Raw evidence for every number above is in `experiments/2026-10-04/` and `experiments/2026-10-05/` (throwaway scripts and saved responses, not code to reuse).

Label workflow: Travis labels in Numbers (iCloud document `dev_150_labeled.numbers`); labels are exported with AppleScript and merged into the CSV by review ID, with review text always taken from the source. The CSV is now ahead of Numbers for the revised rows, so future imports must only fill rows that are still blank in the CSV.

Still pending from Travis: which questions go to the instructor (reuse of early-run calls, one issue per topic, where side experiments are reported); how to log failed calls with unknown token counts. Also open: group and memo details, budget, and the test plan.

Measured in a throwaway probe on 2026-10-04 (50 reviews, single runs): Gemma 26B-A4B 4-bit took about 0.57 s per review with one request at a time and 0.27 s with four, with no failed requests. Batch size (1, 10 or 50 per request) did not change speed, but labels drifted as batches grew.

## What the build established (2026-10-05)

Every decision the executor made on Travis's behalf during the build is in `docs/build-rulings-2026-10-05.md` (94 rulings, each with what it costs if wrong, plus the review's findings and the one left open). The summary written for Travis is `feed/exec-summary-build-2026-10-05.html` (not committed). The facts worth keeping:

- A stand-in run through every stage, stopped once and resumed, exports and the supplied checker returns `pass` with no flags. Eight deliberate breaks of a good export are each named by the checker.
- Replaying Jev's 100 saved pilot answers through the pipeline reproduces the recorded ranking (52 members; usability 38, other 29, playback 22, billing 20) and the measured cost ($0.0039 per 100).
- The calculator's full-pass estimates: $19.11 with exact-text reuse, $25.57 without, $24.65 in the conservative case (5% retries and output tokens billed at the input rate). Under the first cap of $25 the no-reuse case was over and the conservative case left almost no room.
- `pipeline/billing.json` counts Jev output tokens at the input rate until the usage page settles it, so the ledger errs high; `cost/rates.csv` leaves that rate blank and reports it as unknown.
- The token limit (100,000 a second) alone allows about 97 requests a second at pilot request sizes, so the 75-a-second request limit is the one that binds.
- Two stand-ins that label by the same rule agree on every pair, so a stand-in run with 50 or more sampled reviews trips the `verifier_agreement_100` guard; pass `--accept-guard verifier_agreement_100` or a smaller `--verify-size`.
- Saved Jev answers cover 32 of the 60 cut-off-half rows. The other 28 are keyword-picked development rows Jev has not labeled: a small paid run is needed before the cut-off table is complete.
- `prompts/enrich-v2.json` is the candidate slogan wording (only the intent question changes). Unmeasured.
- `prompts/features-v1.txt` is a draft of 45 feature words from counts over the full file, for Travis to read at the 100 gate.

**Independent code review and fix pass, 2026-10-05** (validation log entry 22). No critical finding, 7 important, 12 minor; all fixed but one minor, each with a test that failed first. What changed in how the pipeline behaves:

- Names and memos are cached per run. A second run on the same file makes its own naming and memo calls; only a warm pass reads another run's.
- Classify stops sending new reviews after 8 failures in a row (or twice the workers) and the session ends as `outage`. A request that never left the machine costs nothing in the ledger. A 4xx other than 401, 402, 403 and 429 sets that one review aside; it no longer halts the run.
- The verify, naming and memo prompts are hashed into their stage's setup string. An edited naming or memo prompt is new work for that stage only. An edited verify prompt is refused once verify has started on a run.
- New commands: `nested` (reviews labeled at two gates must keep their labels), `memo` (checks a hand-edited memo), `adjust` (corrects the ledger from the usage page), `cost evidence`. `cost pilot` reads the state file and picks up where it stopped.
- A `--standin` run defaults to `runs/standin.sqlite`; a real eval refuses a state file that holds stand-in runs.
- Measured with the stand-in: the state file saves about 1,490 requests a second with a disk sync on every save (10,000-review file, 16 workers), against a limit of 75. On macOS that sync does not force the drive's cache to flush.
- Still open: Ctrl-C during naming or the memo call does not stop the call in flight.
- Unknown until a real call, by the reviewer's own list: how LM Studio and TypeSafe behave at the edges, whether Gemma's memo passes the check, and sustained speed.

**Ruling by Travis, 2026-10-05: the Jev cap is $35** (spec item 34; he added $10 to the API budget). The number lives once in `pipeline/ledger.py` (`CAP_USD`) and every command's default reads it. The calculator runs without the pipeline package, so it keeps its own copy in `cost/assumptions.csv`; `tests/test_cap.py` holds them equal. What $35 covers, by estimate: the gates (about $0.41) and one full pass in any of the three cases, with about $10 to $15 left. It does not cover a second full pass (about $19 more). Sub-issues (up to about $10) fit only if the full pass comes in near its base estimate. Either still needs his word. The cap is a local guard: it does not know what is in the TypeSafe account.

**Wording trial, 2026-10-05, with Travis's go** (validation log entry 23; `evals/wording_trial_out.json`). The first paid call through the pipeline's own code: 68 requests, all succeeded, $0.0033 by the ledger.

- Planted slogans: the probe wording (`enrich-v1.json`) got 2 of 4, reading S2 and S4 as `cancellation`, as it did on 2026-10-04. The candidate (`enrich-v2.json`) got 4 of 4.
- The 28 `tune` boycott reviews the raters agree on (24 `unclear`, 4 `complaint`): probe 15, candidate 23. The candidate still reads 5 `unclear` reviews as `cancellation`. All 4 complaints stay complaints under both.
- No pass mark missed. **Travis froze v2 on 2026-10-05.** The frozen name lives once in `pipeline/jev.py` (`PROMPT_FILE`); the pipeline command and the eval scripts default to it. `PROBE_PROMPT_FILE` names v1, which stays for the trial's comparison and for the tests that replay the saved pilot answers. Changing the wording after the full run starts means a second full pass.
- Every accuracy figure above this point was measured with the probe wording. The 100 gate is the first look at the candidate on ordinary reviews.
- **Output tokens are not billed** (validation log entry 24). Travis read the usage page after the trial: $0.056, 1,640,194 tokens, 1,451 requests. That is input tokens times the rate; billing every token would show about $0.069. `pipeline/billing.json` and `cost/rates.csv` price output tokens at zero. One reading, rounded to a tenth of a cent; read the page again after the 10,000 gate.
- v2's requests are longer: 64 more input tokens a request on the 34 trial items (7%). That adds about $1.30 to a full pass (*estimate*): roughly $20.4 with reuse, $21.4 with 5% retries, $27.4 with no reuse. The pilot measures the real figure.
- **The holdout score is held until after the 100-review pilot** (the assistant's recommendation when Travis asked on 2026-10-05; this departs from the plan's order). The holdout is scored once and can never change the wording, so it has no use before the pilot, and the pilot is the first look at v2 on ordinary reviews. If the pilot forced another wording change, a holdout already scored would be spent.
- The real state file now exists: `runs/state.sqlite` (gitignored, laptop only). Its ledger reads $0.0562 of $35 after one correction to the usage page; that includes $0.0535 for the earlier probes. It is the only copy of the money ledger; do not delete it.
- Two gaps were fixed before the call: the eval scripts now handle a request the provider refuses, and a real eval opens the ledger with the earlier probe spend.

**100-review pilot, 2026-10-05, with Travis's go** (validation log entry 25). Evidence: `runs/pilot-cold/` (run evidence and its `grading/` export), `cost/` (pilot files and `report.md`), `experiments/2026-10-05/pilot-100/`.

- Every pass mark the code can judge was met: 100 of 100 completed, none quarantined; checker `pass` with no flags; stopped at 50 and resumed; warm pass 0 calls; every response names its pinned model; the instructor's two calculator tests hold on the real evidence.
- **Still Travis's at this gate:** read `prompts/features-v1.txt` (45 words), read `runs/pilot-cold/memo.md` and rule on the memo model, name a provisional cut-off.
- The frozen wording against the probe wording on the same 100 reviews: topic changes on 0, intent on 1, severity on 2. Still 52 complaints or cancellations; usability 37, other 29, playback 22, billing 20. Same scores as v1: 24 of 29 development labels (21 as first written), 79 of 92 against the raters' shared answer.
- Gemma at one review a request: 24 of 29 (21) and 79 of 92; 0.26 s a review, so 5,000 is about 21 minutes (*estimate*), not 53.
- Jev and Gemma give the same three labels on 83 of 100: 40 of 52 complaints and cancellations, 43 of 48 others. 12 of the 17 disagreements carry the review flag at 0.70.
- Measured: 990 input tokens a request with v2, $0.0042 for the 100, 62 s end to end. Projected full pass (*estimates*): $20.39 with reuse, $21.41 with 5% retries, $27.35 with no reuse.
- **The memo is the weak stage.** Gemma's memo was rejected by the code check three times and passed on the fourth attempt; the pilot command had to be run twice. The saved memo is thin and one quote is missing its closing quotation mark. The pipeline does not keep the text of a rejected memo. Proposed and not yet done: keep rejected memo text as evidence, allow three attempts, and let a claim's issue be named earlier in the same paragraph instead of only in the same sentence. These change `pipeline/memo.py`, so they wait for Travis's word.
- Cut-off table from the v2 answers, all 100 pilot reviews (flagged; differences from the raters' shared answer caught, of 13; agreeing answers flagged, of 79): 0.60: 18, 5, 10. 0.70: 30, 11, 15. 0.80: 37, 12, 21. 0.90: 55, 13, 36. Only 32 of the 60 cut-off-half rows are in the pilot; the other 28 need a small paid run (28 requests) that has not been approved.
- The ledger reads $0.0604 of $35 after the pilot.

**Evening of 2026-10-05, on Travis's go** (validation log entries 26 to 30). All of it is on the local branch `gate/pilot-100`, not pushed.

- **Memo model: Claude Sonnet 5.5** (spec item 35). Travis asked whether the memo needs a local model: it is one call a run of about 6,000 input tokens. Sonnet 5.5, Opus 5.5 and Fable 5.1 each wrote the pilot's memo twice under a choosing rule fixed first (cheapest whose first attempt passes the check in both trials). Cost a memo: Sonnet $0.022, Opus $0.06, Fable $0.14. Switching model is one entry in `pipeline/billing.json` (model and rates together) plus the two memo rows of `cost/rates.csv`.
- **The memo check was wrong, and that is why Gemma kept failing.** It asked for a claim's issue in the same *sentence*; four different models wrote "issue-x ranks first. It has 37 [CL-004]." and were rejected. It now asks for the same paragraph or list item. A number still answers to its own sentence. `tests/test_memo.py::RealMemos` holds the rule to a real saved memo, which must pass as written and fail with a claim moved or a number changed.
- Memo calls go through the spend ledger at the memo model's rates and count against the same $35 cap. `Ledger(..., provider="memo")`. A rejected memo's text is now kept (artifact role `memo-rejected`). A real run needs `ANTHROPIC_API_KEY` as well as the TypeSafe key and LM Studio; a missing key stops the run before any spend.
- **Pilot rerun** (`runs/pilot2-cold/`, `cost/`): checker `pass`, warm pass 0 calls, memo passed on its retry ($0.045 for both calls). Projection (*estimates*): $20.44 with reuse, $21.46 with 5% retries, $27.40 with no reuse.
- **500 gate** (`runs/gate-500/`): 500 of 500, checker `pass`, 21 real copies reused, 479 requests at 71.5 a second with 16 workers and no 429, $0.0199 of Jev, memo passed first time. Ranking: usability 167, playback 143, other 135, billing 128.
- **Holdout, scored once** (`evals/holdout_score_prompt-v2.json`): planted 22 of 25 (slogans 4 of 4, injections 3 of 4, emoji-only 3 of 5); real boycott reviews 13 of 28 on all three labels, 24 of 28 on intent. Never to be used to change the wording.
- **Cut-off table on all 60 held-back rows** (flagged; differences from the raters caught, of 9): 0.60: 18, 5. 0.70: 23, 7. 0.80: 26, 7. 0.90: 36, 8. Travis has not named a number; 0.70 is the setting in use.
- **Jev is not fully repeatable.** The same 100 requests 45 minutes apart: topic and intent the same on all, severity changed on 2, quote on 1, review flag on 3, tone score by 0.03 or less on nine in ten. On the 500 gate's nested 100: severity 1, flag 2.
- **The two engines agree on 363 of 500**, but only 146 of 241 complaints and cancellations (severity the same on 168 of those). Severity is what the ranking adds up.
- The ledger reads $0.1578 of $35: about $0.088 to Jev, $0.070 to the memo model. The memo comparison cost $0.79 on the Anthropic key, outside the ledger.

**Travis's rulings on those, 2026-10-05** (validation log entry 31):

1. **The contract's fixed severity rule applies to the pipeline's own labels: yes** (spec item 36). `jev.to_record` gives severity 1 to praise, unclear content and a pure request; Jev's own answer stays in the saved raw answer. It never changes a complaint or cancellation, so the ranking is untouched. The runs exported before it (`pilot-cold`, `pilot2-cold`, `gate-500`) keep their labels as exported.
2. **The nested check is loosened** (spec item 37). `pipeline nested` compares topic, intent and severity and stops a gate when more than 5 in 100 shared reviews changed (`--max-rate`, default 0.05). The quote, the review flag and the tone score are counted and reported. He said "loosen ok" and named no rate; the 5 in 100 is the assistant's, against a measured 1 to 2.
3. **The cut-off is 0.70, named by Travis** after he asked for it to be explained (spec item 4). It is one constant, `jev.CUTOFF`; the pipeline command and the eval scripts default to it. It is part of `label_config`, so it cannot change once the full run starts.

The cost pilot in `cost/` was made before the severity rule. Rerun it once more when everything is frozen, just before the full run, so the submitted pilot is the final code.

**10,000 gate, 2026-10-06, with Travis's go** (validation log entry 32). Evidence: `runs/gate-10k/`. Pull request 3 put `gate/pilot-100` on `main` first (merge `f74c33f`, merged by Travis); the gate's records are on branch `gate/10k`.

- Every pass mark met: 10,000 of 10,000, none quarantined; checker `pass` with no flags; stopped at 6,534 and resumed; 8,448 requests at 73.8 a second with 16 workers, none failed, no 429; verify 5,000 predictions and 0 failures in 1,301 s; memo passed first time.
- **The nested check read 19 of 500 (3.8%), under the stop of 5 in 100.** Five of the 19 are the severity rule, which was coded after the 500 gate (the count entry 31 predicted). On the other 14 Jev's own saved answer differs: severity 7, topic 6, intent 2. All 14 were close calls (top probability 0.55 or less) and carry the review flag in both runs.
- **Jev a day apart changed 2.8% of labels, topic and intent among them.** Within an hour it was 1 to 2 in 100 and never topic or intent. The 5 in 100 stop has less room than it looked.
- Cost: Jev $0.3525 for the run, 993.4 input tokens a request. One full pass at this rate is $20.20 (*estimate*), about $21.2 with 5% retries. At 73.8 a second the full pass is about 1 hour 49 minutes (*estimate*); the longest measured stretch is 68 seconds.
- Ranking: usability 3,311, other 2,661, billing 2,319, playback 2,296, catalog 622, access 620, downloads 331, support 24. **Places 2 to 4 have come out in a different order at 100, 500 and 10,000.** Billing and playback are 1% apart.
- The two engines agree on 3,495 of 5,000: 1,307 of 2,243 complaints and cancellations, 2,188 of 2,757 others.
- The full export should fit in the repo: the largest file, `records.jsonl.gz`, scales to about 71 MB (*estimate*) against the 95 MB at which export refuses.
- The ledger reads $0.5359 of $35. The usage page should read about $0.440 if output tokens are not billed and about $0.524 if they are (it read $0.056 before the pilots). When he read it half an hour later it still showed the night before; see below.
- `pipeline status` refuses while a run holds the state file, so nothing can be checked mid-run. The run prints nothing until it ends when its output goes to a file.

**Before the full run, 2026-10-06** (validation log entry 33). Evidence: `runs/pilot3-cold/`, `cost/`.

- **Pilot on the code as it then stood:** `pilot3-cold` and `pilot3-warm`. 100 of 100, checker `pass`, warm pass 0 calls, memo passed on its retry. Superseded an hour later by `pilot4-cold` (below), after the state-file fix.
- **Jev changed 4 labels in 100 within 40 minutes** (pilot against the 10,000 gate, same code): topic 2, severity 2. Expect the full run's nested check against `gate-10k` to read near 3 in 100. It stops above 5.
- **Feature-word list accepted by Travis** (spec item 5, now decided). Do not edit `prompts/features-v1.txt`, its header comment included: the file is hashed into every run.
- **The usage page lags by hours.** Half an hour after the 10,000 gate it read about 9 cents, 2.5 million tokens and 2,200 requests, which is the ledger as of the night before (2,213 requests, 2,559,498 tokens). Entry 24's limit is still open. To close it: read the page a day after a run and compare with $0.056 plus input tokens since at $0.042 a million.
- **Travis gave the go for the full run without the usage page**, knowing it had not landed. Worst case if output tokens are billed: about $24.6 for the pass (*estimate*), under the cap.
- **The stop by hand works:** a stand-in run stopped by a real interrupt signal, resumed and exported passes the checker. A stand-in run named `rehearse-ctrlc-1006` is in `runs/standin.sqlite`.
- **The memo's first attempt was rejected on 2 of 4 real runs.** If the full run ends with "memo: not written", run the same command again.
- The dry run's cost line still uses the probe wording's rate ($0.0039 per 100) and says $18.88 for the full pass. The ledger and the calculator are right.

**A full-file rehearsal found a slow statement, 2026-10-06** (validation log entry 34). A stand-in run on the full file saved 15 requests a second where 1,490 was measured at 10,000 reviews. The statement that marks a finished text completed was reading every pending review (61 ms at 565,000 pending; 0.005 ms by the text index). Fixed test-first in `pipeline/state.py` (`MARK_TEXT_COMPLETED`, `MARK_TEXT_QUARANTINED`, both `INDEXED BY reviews_by_text`); the same rehearsal then saved 2,209 a second. 523 tests. The code hash is now `530c1e237f7c`. Unfixed, the full pass would have taken about 4 hours (*estimate*) at the same cost. **Rule from this: rehearse any new size with the stand-in before paying for it.** Verify, grouping, the memo and export are still unrehearsed at full size.

**The pilot on the fixed code, 2026-10-06 21:04, with Travis's go:** `pilot4-cold` and `pilot4-warm` on commit `313757c`. 100 of 100, checker `pass`, warm pass 0 calls, memo passed first time. `cost/` is built from this pilot. Projection (*estimates*): $20.42 with reuse, $21.44 with 5% retries, $27.37 with no reuse. The ledger reads $0.6123 of $35. **Then the full run: run name `full`, started by Travis in his own terminal, stopped once with Ctrl-C on camera and resumed.** If this note is the last thing here, check `python3 -m pipeline status --run full` before anything else; it refuses while the run still holds the state file.

**The full run, 2026-10-06 21:09 to about 23:21** (validation log entry 35). Evidence: `runs/full/`.

- Commit `c20aa34`, code hash `530c1e237f7c`. Stopped by Ctrl-C after 122 s at 131,072 completed, resumed with the same command, finished unattended.
- 660,609 completed, 13 quarantined (empty text). Checker `pass`, no flags, `labelable_completion_fraction` 1.0.
- Jev: 484,189 requests, 73.5 a second for 1.8 hours, 24 failed attempts (16 timeouts, 8 HTTP 520) that passed when sent again, no 429. $20.3386 at 1,000.0 input tokens a request. Memo $0.0251, first attempt. Ledger $20.9760 of $35.
- Calculator against the run: $20.42 estimated, $20.36 measured; classify 1.79 h estimated, 1.83 h measured; verify 0.34 h both.
- Verify 5,000 of 5,000, 0 failures; the engines agree on 3,523 (1,294 of 2,196 complaints and cancellations).
- Ranking by severity sum: usability 212,158, other 175,815, playback 147,175, billing 141,482, catalog 45,210, access 40,751, downloads 23,427, support 1,945. 291,865 complaints and cancellations. 191,158 reviews flagged (28.9%).
- Nested against `gate-10k`: 258 of 10,000 (2.6%), all 258 flagged in both runs. Against `gate-500`: 18 of 500.
- Export took 45 s; the folder is about 177 MB, largest file 71.7 MB. `local-reference.json` (161.5 MB) is gitignored, so export's size warning about it asks for nothing.
- The state file is backed up outside the repo at `~/Backups/assign5-multiagent/state-2026-10-06-full-finished.sqlite` (1.4 GB, integrity `ok`).
- **Golden 50, scored once at 23:44 with his go, after the export was pushed (`9586b39`):** topic 40 of 50, intent 43, severity exact 40 (38 with the rule applied to the golden labels), all three 30 in both readings. Jev found 20 of the 21 hand complaints and cancellations and counted 4 hand-`unclear` reviews as complaints. The flag is on 9 of 20 wrong and 5 of 30 right. 50 of 50 quotes exact. Do not score it again; `score_golden.py` refuses without `--again`.
- **Ruling by Travis, at about 23:57 on 2026-10-06, after the score was saved and pushed: the golden label columns may be read for the error analysis.** (The write-up was committed at 00:09 on 2026-10-07, which is why earlier copies of this line said the 7th.) This lifts the reading ban only. The labels stay frozen, the score stays 30 of 50, and the labels still never reach a prompt, an example, a cut-off or grouping. The 20 misses are read one by one in `evals/golden_error_analysis.md` (validation log entry 37): 3 plain Jev errors, 4 where the contract's wording favors Jev, 3 fallback labels for unread languages, 10 open. A what-if by code: counting usability complaints that name Premium (9,403) as billing leaves usability first and swaps places 3 and 4.
- **The stop-and-resume record** is Travis's screenshot and terminal text of the real full run: `runs/full/run_full_screenshot.png`, `runs/full/run_full_text.txt`. The contract asks for "a short recording"; the README says plainly it is a screenshot, not a video.
- **Still open:** the usage page (should rise by about $20.34, or about $24.75 if output tokens are billed, *estimates*); the calculator's report does not print the full run beside its estimates; the dry run's stale cost line. `pipeline/` and `prompts/` have not been touched since the full run, so the code hash is still `530c1e237f7c`; a change to either gives a new hash and must be said in the log.

**Final documents, 2026-10-07** (validation log entry 38). No paid call.

- **Root `grading/`** is a copy of `runs/full/grading/`, file for file. The contract's commands name the full file as the analysis file and the coverage point is counted over all 660,622 rows, so the full run's export is the one that goes there. The checker on it: `pass`, no flags. `python3 -m pipeline rank` rebuilds its `ranking.csv` to the same bytes. Keep the two folders identical; if the full run is ever exported again, copy it again.
- **`evals/trace_review.py REVIEW_ID`** follows one review through the committed files (16 tests in `tests/test_trace.py`). The README's trace is the first review by ID among the 599 sampled members of the first-ranked issue; it happens to be one where the engines disagree with the flag off, and the README says so.
- **The README now has a rubric map** (ten points, each with evidence links and where it is thin), the limits of the totals (review bias, missing data, the two burst months) and the data links. `cost/README.md` no longer says the pilot has not run.
- **131,072 at the stop is real, not a cap:** 8,939 finished requests plus the 122,133 copies of their texts, rebuilt from the export.
- **`docs/final-review-brief.md`** is the one file to hand an outside reviewer of the whole repo (another maker's model, a fresh clone, no paid call). It quotes no result on purpose and holds this file, the rest of `docs/` and the error analysis back until its last pass. If you are that reviewer and this file was loaded, set it aside as the brief says. When the report comes back, compare it with the validation log and add an entry.
- **For Travis before submitting:** 13 lines under `docs/` and `experiments/2026-10-04/` hold a home-directory path and `runs/full/run_full_text.txt` shows the laptop's name. No key is in the tree, the history or the gzipped exports.

## How to work with Travis here

- This is a guided walk-through, not an autonomous build. Explain each step, confirm he understands it, and get his decision before acting. Do not choose a tool, model, threshold, budget or schema on his behalf.
- **Changed by Travis on 2026-10-05 for design decisions:** he asked for speed. Rule on open design items without checking in on each, mark the ruling as delegated, and give him an executive summary of anything high-level he should know. This does not loosen the rules on money, model calls, gates or the golden labels.
- Short messages, plain words. Add detail only when he asks.
- Prefer local models wherever they measure well enough. Tool choices are justified by measured quality, cost and runtime, never by default.
- The 50 golden labels are his to write by hand. Never draft them, and never let his answer columns reach a prompt, a few-shot example, a routing threshold or issue discovery. The golden review *texts* are still classified in the full run.
- Never present an invented or simulated execution, token count, cost, timing, revenue or churn figure as measured. Unmeasured values are labeled "estimate" or "unknown", never silently zero.
- Scale in gates: 100 reviews, then 500, then 10,000, then the full file. Each gate, and any paid call, needs an explicit go.

## Source of truth

Everything lives in `feed/Final Assignment - Spotify Reviews Dataset/` (the path has spaces; quote it). Treat `feed/` as read-only input.

- `GRADING_CONTRACT.md`: label definitions, tie-break rules, and the `grading/` export schema.
- `COST_CALCULATOR.md`: the `cost/` deliverable.
- `check_submission.py`: read `audit()`. It is the real specification of what passes.
- `manifest.json`: checksums and counts for every supplied file.
- `feed/Final Assignment - Multi Agent Large Data Processing Pipeline.md`: the full brief and rubric. Its last lines hold about 150 KB of base64 images; read lines 1 to 225 only.

Fixed numbers: 660,622 rows; 660,609 nonempty texts to classify; 13 empty texts to quarantine; 484,189 distinct nonempty texts; 159,701 missing app versions; no repeated IDs. `cost_100.csv` is the first 100 rows of `checkpoint_500.csv`, which sits inside `analysis_10000.csv`. `golden_50_to_label.csv` is disjoint from all three.

Do not commit the 97.4 MB CSV. The README links the source and records its SHA-256.

## Commands

Only the supplied scripts exist so far. From the repo root:

```sh
D="feed/Final Assignment - Spotify Reviews Dataset"
python3 "$D/check_submission.py" profile   --full "$D/spotify_reviews_18months.csv" --out grading/ingestion.json
python3 "$D/check_submission.py" reference --full "$D/spotify_reviews_18months.csv" --analysis "$D/spotify_reviews_18months.csv" --out local-reference.json
python3 "$D/check_submission.py" check     --reference local-reference.json --submission grading --out self-check.json
```

The pipeline's own commands (see `README.md` for the full list):

```sh
python3 -m unittest discover -s tests -t .                      # 545 tests, no outside network, no key
python3 -m pipeline run --run NAME --new --input PATH.csv --standin   # every stage with the stand-ins; no cost
python3 -m pipeline run --run NAME --standin                    # resume: the same command without --new
python3 -m pipeline run --run NAME --new --input PATH.csv --go  # REAL: needs Travis's go, a clean tree, the TypeSafe and Anthropic keys, LM Studio
python3 -m pipeline status --run NAME
python3 -m pipeline export --run NAME --evidence runs/NAME     # grading/, run evidence, then the supplied checker
python3 -m pipeline rank                                        # ranking from committed files; no model, no state file
python3 evals/trace_review.py REVIEW_ID                         # one review through the committed files of the full run
python3 -m cost                                                 # offline replay of the calculator
python3 -m cost pilot --go                                      # REAL: the paid 100-review pilot; run again to pick up where it stopped
python3 -m cost evidence                                        # write the pilot files again from finished runs
python3 -m pipeline nested --run NAME --against EARLIER         # gate check: reviews labeled in both runs kept their labels
python3 -m pipeline memo --run NAME --file memo.md --save       # check a hand-edited memo and make it the run's memo
python3 -m pipeline adjust --usd 0.25 --note "why"              # correct the spend ledger from the provider's usage page
```

Stand-in runs and real runs never share a state file: a `--standin` run defaults to `runs/standin.sqlite`, so `status`, `export` and `nested` on a stand-in run need `--state runs/standin.sqlite`. A real run without `--go` only prints what it would spend. The eval scripts in `evals/` follow the same rule (`--standin` or `--go`).

The checker is standard library only and makes no network or model calls. Keep `local-reference.json` and `self-check.json` outside `grading/`. Python is `/opt/homebrew/bin/python3` (3.14).

## Pipeline shape the brief requires

Six stages under code control, each with a saved input and output: prepare, classify (enrich), verify, group, rank, recommend. Code owns record accounting, validation, budgets and arithmetic. Models only read language, in four distinct roles with separate instructions and saved evidence: `enrich`, `verify`, `group`, `memo`.

- The classifier sees `review_text` only. Stars and other metadata are kept for analysis and never substitute for reading the text.
- The verifier re-labels a declared random sample without seeing the first prediction; code compares.
- The memo model receives the ranked table and a bounded evidence pack, never the raw CSV. Code checks every cited ID and number.
- The program must accept an arbitrary input CSV path, and ranking must regenerate from saved outputs with no model call.
- `label_config` names model, effort, prompt and schema version. It is also the result-cache key together with the exact text, so any change to those means new work, not reuse.

## Checker rules that are easy to miss

Found by reading `audit()`:

- "Empty" means `review_text.strip()` is empty. The quarantine reason must be exactly `empty_review_text`.
- Hash rows only with the checker's `row_sha`. No trimming or Unicode normalization anywhere.
- `evidence_quote` must be a non-blank exact substring of the original text on every completed record.
- Types are strict: `severity` a real int 1 to 5, `needs_review` a real bool, `sentiment` a finite number in [-1, 1], `entities` a list of non-blank strings (may be empty).
- Cache reuse (`cache_source_id`): the source must be a valid completed record with no `cache_source_id` of its own, byte-identical text, and identical values in all eight label fields. A bad reuse removes that record from the completed count.
- Every completed record that is not a cache reuse needs a `succeeded` `enrich` call listing its ID with the same `label_config`.
- In `calls.jsonl`, `request_id` is unique across the file, `input_tokens` and `output_tokens` are non-negative ints on every line, and every ID in `review_ids` must be a real source ID. Synthetic injection and planted-error cases therefore live in `evals/`, never in `grading/calls.jsonl` and never in business aggregates.
- Enrich calls carry 1 to 50 unique IDs and a `phase` of `initial` or `resume`. A `resume` call must not contain any ID from `checkpoint_before.json`. This holds even for failed calls and for a different model, so a review is saved as finished only when every call for it is done, and it is never sent again.
- A succeeded enrich call whose `label_config` differs from the review's final record is flagged once per ID. A fallback model must share one `label_config` with the main model, and calls from superseded prompt versions stay out of `grading/calls.jsonl`.
- Every logged call, failed ones included, needs a unique `request_id`, a phase (if enrich) and whole-number token counts; missing, null or decimal counts are flagged.
- Checkpoints list completed reviews only. Including quarantined IDs fails the resume check.
- One invalid record cascades into membership, ranking and claim mismatches, so run the checker before memo numbers are final.
- Checkpoints: `before` is non-empty and a strict subset of `after`; `after` sits inside the valid completed set. Every non-cached `before` ID needs an `initial` call, and at least one new non-cached ID needs a `resume` call.
- All four roles need at least one `succeeded` call.
- Every completed `complaint` or `cancellation` record appears in `membership.csv`, in exactly one issue unless `run.json` sets `allow_multi_issue: true`. No other intent may appear.
- `ranking.csv` and `claims.csv` are compared as strings: plain integer strings, and `mean_severity` to six decimals with half-up rounding (use `Decimal`). Order is `priority_score` descending, then `issue_id` ascending.
- `grading/` holds a JSONL file plain or gzipped, not both.
- Coverage point = 0.2 × exact profile match + 0.2 × accounted rows + 0.6 × validly classified nonempty rows. Any flag sets status to `review_required`.

## Cost calculator rules

- Offline replay from saved usage is the default. Importing or opening the calculator must never start a call; the paid pilot is a separate explicit command.
- The pilot runs `cost_100.csv` unchanged, cold (empty result cache, one worker) then warm (zero new enrichment calls), through all stages.
- Instructor tests: doubling API rates doubles the API subtotal and leaves local-compute cost and measured time unchanged; changing the projected row count leaves the measured 100-review results unchanged.
- API spend, local-compute estimates and unknown costs are reported separately. Local inference is not "free"; it has time, memory and power.
- Project each stage from its own work count. Fixed overhead (one memo, one grouping pass) is added once.
- Workers share one rate limiter and one spend ledger. Reserve worst-case spend before dispatch and stop admitting work when spent plus reserved plus the next reservation exceeds the cap.

## Environment notes

These come from Travis's wiki (pages `[[lm-studio]]` and `[[jev]]`), not from measurements in this project. Verify before relying on them.

- Local text models run in LM Studio (MLX), OpenAI-compatible at `localhost:1234/v1`: Gemma 4 E2B, E4B, 26B-A4B and 31B. Ollama on this machine holds only vision and coder models.
- Gemma 4 traps: send `reasoning_effort: "none"` or reasoning tokens consume `max_tokens`; `response_format` must be `json_schema` (`json_object` returns 400); schema-valid strings can still carry leaked template tokens, so validate string contents.
- Jev (TypeSafe) is reached through Cloudflare AI Gateway. It takes one review per request, returns choices and probabilities only (no generated text, so quotes and entities need code or another model), favors the first `choice` option, and can be moved by text that argues for its own label. Send `cf-aig-collect-log: false` on every call, because the gateway logs full bodies by default.
