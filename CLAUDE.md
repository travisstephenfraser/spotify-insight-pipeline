# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Travis's individual capstone, "Multi Agent Large Data Processing Pipeline", due 2026-10-13 23:59 PT. The pipeline turns 660,622 Spotify app reviews into a ranked list of product issues and a short decision memo, with every number traceable to saved evidence. The deliverable is one public GitHub repo whose README maps each rubric point to an evidence link.

**State as of 2026-10-04:** no pipeline code exists. The repo's remote is `git@github.com:travisstephenfraser/spotify-insight-pipeline.git`, private until Travis flips it public for submission. The design is being agreed one decision at a time. Update this section as stages land, and add the pipeline's own run and test commands under Commands when they exist. The decisions below are in the order they were made; later entries supersede earlier ones.

Before the repo goes public: reread this file, `docs/` and `experiments/` for anything personal, and decide whether the course brief in `feed/` should be published. Handoff notes (`feed/HANDOFF-*.md`) are gitignored and stay on the laptop.

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
- **Budget cap, decided by Travis: $25 of total Jev spend for the project**, held in the spend ledger (reserve worst case before each request; stop admitting work when spent plus reserved plus the next reservation would pass the cap; save and resume). Projected from the measured $0.0039 per 100 reviews: gates about $0.41 together, one full pass over 484,189 distinct texts about $19, leaving about $5. The cap does not cover a second full pass (about $19) or sub-issues (up to about $10); either needs Travis to raise it. So the intent wording must be settled before the full pass, because any prompt change is a new `label_config` and new work. Retries are unmeasured.

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

- **Item 19, label freeze: yes.** A label file is committed and its SHA-256 recorded before model output for its rows is seen. After the freeze no golden label changes; a plainly wrong one stays and the score is shown both ways. The guide's last lines were rewritten to say this. The development sheet as it stands is commit `bb5f440`, SHA-256 `febbfaeea4ed9a0034ce8ee9e6cf9fb0f283515d2469a41520dbd93a00cd6dd6` (29 rows labeled, five revised after seeing Jev). The golden sheet is still blank; its freeze hash is recorded when Travis finishes labeling.
- **Item 27, output-token billing: settle it with a test batch** (send a small known batch, compare the TypeSafe usage page with input tokens times the rate). Unknown until then.
- **Outside raters (spec item 30): approved.** Fable 5.1 (Anthropic) and Astra 6 (OpenAI's top model) label reviews blind as third-party raters. Budget: **$10 per provider, a hard cap**, separate from the $25 Jev cap. Travis adds `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` to `.env`. Conditions: the raters see only the review text and the contract's label section word for word, nothing from Jev, Gemma, Travis or the assistant's paraphrases; their labels are for tuning and for marking disputed rows, never for accuracy claims; the golden 50 stays Travis's by hand and is frozen before any rater sees those texts; the write-up discloses that Fable 5.1 shares a maker with the assistant that wrote the spec. Each paid run still needs its own go.
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
- **Waiting on Travis:** `evals/adjudication_sheet.csv`, 39 reviews to label blind (23 where the raters differ, 1 planted case, 15 agreed checks, mixed). He must not open `evals/adjudication_key.json` or the rater answer files first. When he is done the sheet is committed and hashed before he sees any rater answer for those rows.

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

Raw evidence for every number above is in `experiments/2026-10-04/` (throwaway scripts and saved responses, not code to reuse).

Label workflow: Travis labels in Numbers (iCloud document `dev_150_labeled.numbers`); labels are exported with AppleScript and merged into the CSV by review ID, with review text always taken from the source. The CSV is now ahead of Numbers for the revised rows, so future imports must only fill rows that are still blank in the CSV.

Still pending from Travis: which questions go to the instructor (reuse of early-run calls, one issue per topic, where side experiments are reported); how to log failed calls with unknown token counts. Also open: group and memo details, budget, and the test plan.

Measured in a throwaway probe on 2026-10-04 (50 reviews, single runs): Gemma 26B-A4B 4-bit took about 0.57 s per review with one request at a time and 0.27 s with four, with no failed requests. Batch size (1, 10 or 50 per request) did not change speed, but labels drifted as batches grew.

## How to work with Travis here

- This is a guided walk-through, not an autonomous build. Explain each step, confirm he understands it, and get his decision before acting. Do not choose a tool, model, threshold, budget or schema on his behalf.
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
