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

Design part 2 (settings that follow from the Jev ruling) was presented on 2026-10-04 and is **awaiting Travis's yes**: Jev `jev-1.13.0` in the simple style, one request per review, with Jev picking the evidence sentence; one request at a time for the pilot, then up to 16 at once capped near 75 per second; Gemma 26B as blind second opinion on a random sample of 5,000 at one review per request; a review flag from Jev's top probability with the cut-off set on development labels only; tightened intent wording for slogans plus planted slogan and injection tests. Part 3 (grouping, memo, budget cap) has not been presented. Then the spec gets written.

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
