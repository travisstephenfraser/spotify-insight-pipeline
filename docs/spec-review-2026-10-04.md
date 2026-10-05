# Independent review of the design spec, 2026-10-04

This is the record of the review that the spec's section 13 summarizes. It holds what each reviewer was told, what each reported, and what was done with every finding.

Spec reviewed: the first draft of `docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md` (312 lines, before the revision the same day).

## Why it was run this way

The assistant that wrote the spec cannot check its own work independently. So three separate reviewers were started, each with:

- the spec and the primary source files (the checker's code, the grading contract, the cost calculator spec, the brief, the saved experiment outputs);
- one narrow lens, so the three would not produce three overlapping summaries;
- none of the author's reasoning, suspicions or expected findings;
- a rule that every finding must quote a source line with its path and line number, and that a concern without a quote goes in a separate "unverified" list;
- read-only access, no network and no model calls, and no access to `.env` or either label sheet.

The three lenses: measurement validity, contract and checker compliance, and state and spending controls.

After the reports came back, the author rechecked the most serious findings against the quoted sources before acting on any of them. Those are marked "rechecked" below.

## Limits of this review

- All three reviewers are the same model family as the spec's author (Claude). They can share its blind spots. A reviewer from another maker was not used for the spec.
- The reviewers read documents and saved outputs. Nothing was executed against the checker, so findings about the checker rest on reading its code.
- The recheck was done by the spec's author, who has a stake in the spec. It was limited to comparing each finding with the quoted line or recomputing a number from a saved file.
- Findings marked "not rechecked" were accepted on the reviewer's quoted evidence alone.

## What the review found, in short

About 32 findings. Four would have produced a flagged export or a misleading score:

1. **Resume evidence would have been flagged** (two reviewers, independently). The first draft took the "before" checkpoint at the end of the first session. The full pass, about 1.8 hours by estimate, fits in one session, so "before" would equal "after", and the checker requires a strict subset (`check_submission.py` line 322).
2. **The development labels lean toward Jev.** Labels were revised only on rows where a model disagreed with the labeler. One row kept a severity the labeling guide itself calls a slip, and it counted as a Jev hit because Jev made the same call.
3. **Engine agreement hides where the engines differ.** Jev and Gemma agree on 43 of 48 non-complaints but 34 of 52 complaints and cancellations, the only rows that feed the ranking.
4. **A crash could lose paid calls** (two reviewers). The first draft claimed it could not.

Two claims in the first draft were wrong and were corrected: that the checker forces verifier disagreement to stay out of `needs_review`, and that request bytes could serve as the token estimate in the rate limiter at 75 requests per second.

## Every finding and what happened to it

M = measurement reviewer, C = compliance reviewer, S = systems reviewer. Numbers follow each report below. Item numbers refer to the spec's section 12.

| Finding | Severity given | Rechecked | Outcome |
|---|---|---|---|
| M1 labels revised only where a model disagreed | Blocker | Yes: guide lines 10 and 81, saved comparison output | Label freeze adopted (item 19). The 29 rows kept with both scores reported (item 20). Later tested by the outside raters, see `docs/validation-log.md` entry 9 |
| M2 agreement read as accuracy; ranking rows disagree more | Blocker | Yes: recomputed 34 of 52 and 43 of 48, and both engines' severity sums | Stated in spec 6.2. Report depth and verifier wording still open (items 21, 22) |
| M3 planted cases written and tuned on by one author | Should fix | No | Real boycott sample of 60 built, half held back (item 23). Outside raters checked the planted answers |
| M4 cut-off rests on 5 errors and is never evaluated | Should fix | Partly: recomputed the 14 reviews near a 0.70 cut-off | Golden report now scores `needs_review` as a prediction (spec 10). More labels and a split agreed (item 24) |
| M5 planted-error test passes by construction | Should fix | No | Renamed a test of the comparison code (spec 6.2) |
| M6 guards miss the realistic failure and are untested | Should fix | No | Thresholds marked as placeholders. Bands and guard tests open (item 25) |
| M7 memo check verifies copying, not truth | Should fix | No | Stated in spec 6.6. Stronger checks open (item 26) |
| M8 measures the brief requires are missing | Should fix | Yes: brief lines 101 and 102 | Added to the golden report (spec 10) |
| M9 golden set is disjoint by ID, not by text | Note | No | Naming and evidence samples no longer use run order (spec 6.3, 6.6) |
| M10 stand-in models confirm format only | Note | No | End-to-end test replays the 100 recorded Jev responses (spec 10) |
| M11 verify sample drawn among completed reviews | Note | No | Sample fixed at prepare time (spec 6.2) |
| M12 gates name no blocking number | Note | No | Open (item 28) |
| C1 phase and checkpoint tied to the first session | Blocker | Yes: checker lines 322 and 369 | Fixed (spec 6.1). How the stop is triggered is open (item 18) |
| C2 run evidence exists only in the uncommitted state file | Blocker | Yes: brief lines 143 to 148 and 197 | Run evidence listed; ranking and replay read committed files (spec 6.5, 8, 9) |
| C3 no path when a nonempty review ends quarantined | Should fix | Yes: checker lines 245 and 255 | Fixed (spec 6.1, 9) |
| C4 `run.json` fields unspecified | Should fix | Yes: checker lines 180 to 183 | Fixed (spec 9) |
| C5 gzip rule too wide | Should fix | Yes: the checker's `lines`, `table` and `obj` readers | Fixed (spec 9) |
| C6 requests in flight at an interruption never logged | Should fix | No | Fixed with an intent row saved before each request (spec 4) |
| C7 nothing freezes `label_config` inside a run | Should fix | No | Content hashes saved at run creation (spec 4). Run naming open (item 17) |
| C8 golden report omissions, no label examples | Should fix | Yes: same lines as M8 | Fixed (spec 6.1, 10) |
| C9 calculator display gaps | Should fix | No | Fixed (spec 8) |
| C10 "forced by the checker" is unsupported | Note | Yes: checker lines 245 to 248 | Wrong claim removed (spec 6.2) |
| C11 stage definitions incomplete | Note | No | Stop and failure rules added (spec 6.2, 6.3, 6.5, 6.6) |
| S1 same as C1 | Blocker | Yes | Same fix. Two reviewers found it independently |
| S2 paid results held in memory until the writer commits | Blocker | Arithmetic only | Fixed with the intent row, a bounded queue and write-ahead logging (spec 4) |
| S3 no run identity and no process lock | Blocker | No | Proposed in spec 4 and 11; open (item 17) |
| S4 no end state after temporary failures; fatal errors treated as invalid answers | Blocker | No | Fixed (spec 6.1) |
| S5 stop and rate-limit rules break under 16 workers | Should fix | No | Rewritten as time windows (spec 6.1, 7); open (item 7) |
| S6 token limiter has no estimator | Should fix | Yes: recomputed 2,463 body bytes against 926 input tokens | Limiter uses bytes divided by 2.4 (spec 7). Output-token billing to be settled by a test batch (item 27) |
| S7 verify has no rule for a dead local server | Should fix | No | Server check added (spec 6.2) |
| S8 tables cannot feed the calculator | Should fix | No | Sessions table, ledger in billed units (spec 4, 8) |
| S9 cache keys omit model and settings | Should fix | No | Fixed (spec 6.3, 6.6) |
| S notes: cap not seeded with probe spend; stale plain file beside a gzipped one; keys in error text; no provider-side limit | Note | No | First three fixed (spec 4, 9). Provider limit open (item 29) |

The reviewers' "unverified concerns" are listed at the end of each report. None was acted on as fact. Those worth testing are carried in the spec's section 13.

## Appendix: the reviewers' briefs and reports, as written

Each brief is the complete instruction the reviewer received. Each report is the reviewer's complete final message. The only edit is that the repository's absolute path prefix was shortened to `<repo>/`.

### Measurement validity: brief

You are a measurement-design reviewer. Your one job: find holes in how a design spec proposes to MEASURE and VALIDATE its own results. You are not reviewing code style, architecture or cost. You have no stake in this spec being good; a finding of "this measurement is a rubber stamp" is a successful review.

#### What to review

Spec (not yet built): `<repo>/docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md`

It describes a pipeline that labels 660,622 Spotify app reviews (topic, intent, severity, sentiment, quote) with a classifier called Jev, re-labels a sample with a local model (Gemma 26B) as a blind second opinion, groups complaints into issues, ranks them, and has a model write a memo.

#### Files you need (read them; do not rely on the spec's own summary of them)

All under `<repo>/`:
- `CLAUDE.md`: the decision trail and every number measured so far. Treat its numbers as claims to check against the evidence files, not as truth.
- `experiments/2026-10-04/README.md` and the files in `experiments/2026-10-04/tool-choice/` (`compare_out.txt`, `three_tests_out.txt`, `flag_probe_out.txt`, `flag_probe.py`, `three_tests.py`, `jev_spike.py`, `gemma_spike.py`): the evidence behind those numbers.
- `evals/golden_labeling_guide.md` and `evals/dev_sets.json`: how the human labels are produced and how the development set was picked.
- `feed/Final Assignment - Spotify Reviews Dataset/GRADING_CONTRACT.md`: label definitions.
- `feed/Final Assignment - Multi Agent Large Data Processing Pipeline.md`: the assignment brief. READ LINES 1 TO 225 ONLY (the rest is base64 image data). Lines 98 to 103 state the evaluation requirements.
- `docs/red-team-plan-2026-10-04.html`: an earlier adversarial review; its statistics findings bind the design.

#### Hard rules

- Read-only. Do not create, edit or delete any file.
- No network and no model calls. Do not contact `localhost:1234` or `api.typesafe.ai`. Do not run any script that does.
- Never open `.env`. Never open `evals/golden_50_labeled.csv` or `evals/dev_150_labeled.csv` (you do not need them: both have columns review_id, review_text, intent, topic, severity, sentiment, evidence_quote, entities, needs_review, notes; 29 of 150 development rows are labeled, 0 of 50 golden rows are labeled yet).

#### The test to apply

For EVERY measurer the spec relies on, run three probes. All three must hold or the measurement is a rubber stamp:
1. Architectural independence: does the measurer share the model, the prompt or definitions lineage, the preprocessing, or the author with the thing it measures?
2. Incentive independence: does whoever produced the measurer (or the expected answers) have a stake in the result passing, or prior exposure to the answer being graded?
3. Evidence parity: does the measurer see what the primary saw, no more and no less?

The measurers to cover, at minimum: (a) the Gemma verifier and its disagreement report; (b) the `needs_review` flag and how its cut-off is chosen and later evaluated; (c) scoring on the development labels; (d) the golden-50 evaluation; (e) the planted slogan and injection cases; (f) the planted-error test; (g) the "guards that raise" in sections 5 and 10 and their thresholds; (h) the code check on the memo and the human read of the memo; (i) the end-to-end test with stand-in models.

Specific things to hunt for:
- A human labeler whose labels were shaped by seeing model output, and what that does to any score computed from those labels.
- A finite labeled set reused for several tuning decisions (prompt wording, a cut-off, engine comparison) with no fresh holdout, and whether the spec has any guard for that.
- Expected answers written by the same party that tunes the system against them.
- Agreement between two models being read as accuracy.
- A baseline number carried over from a different configuration and used as an anchor.
- Thresholds that are invented rather than derived, and guards that would not fire on the realistic version of the failure they exist to catch (for each guard, ask: what does the real failure look like, and does this guard see it?).
- Which direction of failure would look like success, for each measurement.
- Sampling: what population each sample is drawn from, what it silently excludes, and whether duplicates distort it.
- Sample sizes against the claims they are meant to support.
- Anything the brief's evaluation section requires that the spec does not measure at all.
- Measurements nobody will read (intermediate values feeding a prompt or a report footer) and guards whose absence would produce no signal.

Ask what the spec MISSES ENTIRELY, not only what it gets wrong.

#### Evidence standard

Every finding needs evidence: a quoted line with `path:line` from the spec or a source file, or a count you computed from an evidence file. A concern you cannot back with a quote goes in a separate list headed "Unverified concerns". Do not refute or confirm from general priors. If the spec already handles something correctly, do not list it.

#### Output (cap about 700 words)

A list of findings, most severe first. For each: a one-line claim; severity (BLOCKER = the result would be wrong or misleading and nobody would know; SHOULD-FIX; NOTE); which probe fails; the evidence quote with path:line; and the smallest change that would close the hole. Then the "Unverified concerns" list. No preamble and no summary of the spec.

### Measurement validity: report

Root: `<repo>/`. SPEC = `docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md`. TC = `experiments/2026-10-04/tool-choice`. "Computed" = counted by me from TC/simple.jsonl, gemma.jsonl, sentence.jsonl and the feed CSVs. No model call, no label file opened, nothing written.

**1. BLOCKER. Reference labels are revised only where the model disagreed, so scores drift toward Jev unseen.** Probe 2.
- `experiments/2026-10-04/README.md:46`: "Before the revision... Jev simple 25, 27, 25 and 21 of 29... Gemma was not scored against the unrevised labels." It is 24 of 29 after.
- A slip Jev shared stayed in. `evals/golden_labeling_guide.md:10`: "(wifi fails but mobile data works), it is 3, not 4". `TC/compare_out.txt:13`: "row 29: you playback/complaint/4 gemma playback/complaint/3", scored a Gemma miss and a Jev hit.
- Golden inherits it. Guide:81: "After the classifier is scored, a label changes only to fix a clear slip", against SPEC:24 "scored once".
- Fix: record each label file's SHA-256 before model output for those rows is seen. Headline the frozen score. Any re-check covers an equal hash-picked sample of agreements, with both scores shown.

**2. BLOCKER. Jev-Gemma agreement is one headline rate read as accuracy, while ranking rows disagree more and the rank inputs move.** Probe 1.
- Computed: identical labels on 34 of 52 Jev complaint/cancellation rows against 43 of 48 others; 30 of 32 on texts of 20 characters or fewer against 47 of 68 longer. 38.1% of file rows are that short; 29.1% carry a repeated text.
- Same 100 reviews, billing severity sum: Jev 20, Gemma 9. Usability: 38 against 55.
- Shared lineage: `TC/gemma_spike.py:13` "from jev_spike import INTENTS, SEVERITY, SRC, TOPICS". `TC/jev_spike.py:56` says "nothing stops working" where `GRADING_CONTRACT.md:44` says "no supported functional loss". Both engines gave severity 2 on row 19 (compare_out.txt:9,19).
- SPEC:198 forwards only "the verifier's disagreement rate"; brief:110 says "investigate disagreements".
- Fix: split agreement by complaint/cancellation against the rest, and per topic. Re-rank the verify sample on Gemma's labels and state whether the order holds. Give the verifier the contract's wording verbatim.

**3. SHOULD-FIX. Slogan and injection cases: one author writes the answers, the wording is tuned on them, then reported on them.** Probes 1, 2.
- README:61: "written by the assistant... not by a second person". SPEC:116: "tried on the planted cases". SPEC:256: "against the final wording". Four cases per group (`TC/three_tests_out.txt:29`).
- Computed: "boycott" texts number 1 in the pilot (sheet row 87, unlabeled), 1 in golden, 0 in targeted cancellation rows, 3,484 in the file.
- Flattering direction: tightening pushes real complaints to `unclear`, which drops them from the ranking. That pilot row ("Useless aap boycott sweden") is already `unclear`, severity 2, from both engines.
- Fix: hash-pick about 60 real boycott reviews, label blind, tune on half, score the other half once.

**4. SHOULD-FIX. The `needs_review` cut-off rests on 5 errors and is never evaluated.** Probe 2.
- `TC/flag_probe_out.txt:12`: "cut 0.7: flags 4 of 5 wrong, 4 of 24 right". 4 of 5 spans 38% to 96% (computed). Row 29 sits among the "right" at severity probability 0.59.
- SPEC:258 omits the flag; brief:102 says "Evaluate needs_review as a prediction".
- The same rows tune wording (SPEC:116) and score both engines (SPEC:152, 257). CLAUDE.md:43 "sheet rows 2 to 30": all 50 targeted rows are unlabeled.
- Fix: label the rest blind, split by hash into a wording half and a cut-off half, add flag hit and false-alarm counts to the golden report.

**5. SHOULD-FIX. The planted-error test passes by construction.** Probe 1.
- SPEC:166 "The comparison must flag each one" tests `!=` against Gemma's fixed answer.
- Fix: call it a code test. Add verifier detection on labeled rows: today 4 of Jev's 5 errors, and 4 of 7 disagreements were Jev errors (compare_out.txt:23).

**6. SHOULD-FIX. Guards miss the realistic failure and nothing tests that they fire.**
- SPEC:263 "one topic above 95%... over 500 or more reviews": baseline `other` is 55 of 100 (compare_out.txt:24), so 80% is silent and the 100 gate is exempt. The probe was stricter (`TC/score_spike.py:130-134`).
- No severity guard, though priority is the severity sum. SPEC:124 "kept inside -1 to 1" clamps a wrong scale into a valid value.
- SPEC:164 "exactly 100%": a leak at 98% or a mis-join at 40% passes. Its 77 anchor is "at 10 per request", where regrouping changed 15 of 100 (three_tests_out.txt:37).
- SPEC:249 lists no guard tests.
- Fix: bands around the previous gate's values; a test that verify request bodies are byte-identical with Jev results present, scrambled or absent; one planted failure per guard; the nested 100 must get identical labels at every gate.

**7. SHOULD-FIX. The memo check verifies copying, not truth.**
- SPEC:202 "Any other number must be one of the run facts" matches by value against numbers nothing recomputes. A claim ID is not tied to the issue its sentence names. A recommendation without digits is unchecked.
- SPEC:197 "sorted by severity (highest first)" presents extremes as representative.
- SPEC:208: the owner reads one pilot memo, with no checklist.
- Fix: claim ID and issue ID in the same sentence; assert the recommendation is rank 1 or the deviation is stated; recompute run facts from exported files; add hash-picked quotes.

**8. SHOULD-FIX. Brief-required measures are missing from SPEC:258.**
- Missing: ambiguous count and per-topic counts (brief:101); entities and "inspect whether the quote supports the label" (brief:102).
- SPEC:47 calls quote/topic mismatch "unmeasured"; saved data gives 3 of 25 multi-sentence reviews (computed).
- No signed severity error: Jev's three severity misses are all low (compare_out.txt:17,19,20).

**9. NOTE.** Golden is disjoint by ID, not text: 2 of 50 texts equal pilot texts, 13 are 20 characters or fewer, keyword matches for access and support are 0 (computed).

**10. NOTE.** Stand-ins (SPEC:250) confirm format only. Replay the 100 recorded responses in TC/simple.jsonl.

**11. NOTE.** The verify sample is drawn "among completed reviews" (SPEC:152), which conditions on Jev success. Draw it from all nonempty IDs first.

**12. NOTE.** Gates: SPEC:45 "Each needs an explicit go" names no blocking number.

**Unverified concerns**
- Which five rows were revised. Rows 5 and 26 (billing against usability, both Gemma misses) fit guide:9.
- Notes-column "alt" labels count as hits (`TC/compare.py:57`); when they were written is unknown.
- Whether verify loads Jev's definitions file (SPEC:275 implies it).
- Whether "mean error" (SPEC:258) is absolute or signed.
- Translated golden rows (guide:77) give the labeler evidence Jev lacks.
- The usage-page check (SPEC:216) may not resolve a $0.004 pilot.
- 14 of 100 pilot reviews sit within 0.08 of a 0.70 cut-off; a rerun moved one probability by 0.08 (three_tests_out.txt:35).

### Contract and checker compliance: brief

You are a compliance reviewer. Your one job: find every place where a design spec would fail, contradict, or simply omit a requirement of the assignment it is written for. You are not reviewing prose quality or whether the design is elegant. You have no stake in this spec being good.

#### What to review

Spec (not yet built): `<repo>/docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md`

It describes a pipeline that labels 660,622 Spotify app reviews, verifies a sample with a second model, groups complaints into issues, ranks them, writes a memo, and exports a `grading/` folder and a `cost/` folder that an instructor checks.

#### The primary sources (the spec must satisfy these; read them yourself, in full)

All under `<repo>/feed/`:
- `Final Assignment - Spotify Reviews Dataset/check_submission.py`: read the whole `audit()` function. It is the real specification of what passes. Every `flag(...)` call is a way to fail.
- `Final Assignment - Spotify Reviews Dataset/GRADING_CONTRACT.md`
- `Final Assignment - Spotify Reviews Dataset/COST_CALCULATOR.md`
- `Final Assignment - Spotify Reviews Dataset/manifest.json` and `README.md` in the same folder
- `Final Assignment - Multi Agent Large Data Processing Pipeline.md`: the brief and rubric. READ LINES 1 TO 225 ONLY (the rest is base64 image data).

Also available for context: `<repo>/CLAUDE.md` (decision trail) and `docs/red-team-plan-2026-10-04.html` (an earlier review that already tested the checker with synthetic submissions; do not repeat what it settled, but do check the spec honours it).

#### Hard rules

- Read-only. Do not create, edit or delete any file.
- No network and no model calls. Do not contact `localhost:1234` or `api.typesafe.ai`.
- Never open `.env`. Never open `evals/golden_50_labeled.csv` or `evals/dev_150_labeled.csv`.
- You may run `check_submission.py` only if you build throwaway inputs in a temp directory outside the repo; that is optional and not expected.

#### How to work

Go through the primary sources requirement by requirement and ask of each: does the spec satisfy it, contradict it, or never mention it? Then go through the spec's design choices and ask of each: which `flag()` in `audit()` could this trigger?

Specific things to hunt for:
- Every `flag()` code in `audit()`: trace whether the spec's design can trip it. Pay special attention to cache reuse (`invalid_cache_reuse` and the eight `label_fields`), `call_config_mismatch`, `unlogged_completed_records`, `reprocessed_checkpoint`, `resume_snapshot_mismatch`, `resume_call_evidence`, `invalid_usage`, `invalid_call_ids`, `unbounded_batch`, `invalid_run_phase`, `ungrouped_complaints`, `ranking_mismatch`, `claim_mismatch`, `missing_claims`, `run_manifest_mismatch`, `ingestion_mismatch`.
- The spec's rule for assigning `phase` (initial or resume) and for which IDs go in `checkpoint_before`: can any sequence of sessions, retries, failures or duplicate texts produce a flagged export?
- Records for reviews that end up quarantined for a model failure, and what that does to checkpoints, membership and the coverage score.
- String formats the checker compares exactly (`ranking.csv`, `claims.csv`, `mean_severity`).
- `run.json` fields.
- The requirement that the program accept an arbitrary input CSV: does anything in the spec only work for the supplied file?
- Every item in COST_CALCULATOR.md sections 2, 3 and 5, and the brief's calculator section: is each required display, file, control and test covered? Cold and warm pilot semantics. The two instructor tests.
- Every rubric line (brief lines 19 to 29), every item under "Evidence Required in the README" (lines 185 to 192), "Save Your Results" (lines 141 to 151), "Definition of Done" (lines 206 to 213) and the "Bring to Class 7" list (line 78): what does the spec produce no artifact for?
- The brief's stage descriptions (lines 105 to 124) and the "awkward paths" list (line 178): owner, input, output, failure behavior and stop condition per stage; retry limits; statuses.
- Rules about the golden 50, about stars and metadata, about synthetic test cases, about revenue and churn claims, about personal details.
- Anything the spec states as a fact about the checker or the contract that the source does not support.

Ask what the spec MISSES ENTIRELY, not only what it gets wrong.

#### Evidence standard

Every finding needs two quotes: the requirement, with `path:line` from a primary source, and the spec line that fails it (or the statement "spec is silent", after you have searched the spec for it). A concern you cannot back that way goes in a separate list headed "Unverified concerns". If the spec already satisfies something, do not list it.

#### Output (cap about 700 words)

A list of findings, most severe first. For each: a one-line claim; severity (BLOCKER = would cost a rubric point or set the checker to `review_required`; SHOULD-FIX; NOTE); the requirement quote with path:line; the spec quote with line number or "silent"; and the smallest change to the spec that closes it. Then "Unverified concerns". No preamble and no summary of the spec.

### Contract and checker compliance: report

Key: CS = check_submission.py, GC = GRADING_CONTRACT.md, CC = COST_CALCULATOR.md, all in `<repo>/feed/Final Assignment - Spotify Reviews Dataset/`; BR = `<repo>/feed/Final Assignment - Multi Agent Large Data Processing Pipeline.md`; Spec = `<repo>/docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md`. Findings come from reading the sources; I did not run the checker.

#### Findings

**1. BLOCKER. Phase and checkpoint are tied to "first session", so ordinary sequences export a flagged run.**
- Req: CS:321 `if not before or not before < after or not after <= set(valid)` (`resume_snapshot_mismatch`); CS:369 needs `initial` calls for every `before` ID and a `resume` call for a new non-cached ID.
- Spec:146 "calls in a run's first session are `initial`"; :238 "`checkpoint_before` is the completed list at the end of the first session"; :93 "at session end".
- Fails when session 1 completes nothing (bad key, 20 straight failures, Spec:144): `before` is empty and every later call is already `resume`.
- Fails when session 1 finishes everything (Spec:220 "about 1.8 hours" inside Spec:284 `--max-hours 8`).
- Fails when the session is killed, since there is no "session end" write.
- Spec:250's end-to-end test cannot return `pass` without a stop either.
- Fix: snapshot `before` at the start of the first session that opens with at least one completed and one pending original. Calls before it are `initial`, after it `resume`. State that the full run is stopped once on purpose.

**2. BLOCKER. Run evidence and stage handoffs exist only in the uncommitted state file.**
- Req: BR:148 "run_log.jsonl and run_summary.json: stage timing, statuses, attempts, failures, usage, actual charges"; BR:143 "a manifest tying source checksum, code version, prompts, model IDs, settings and outputs"; BR:145 "quarantine.jsonl: unresolved records with reasons and attempts"; BR:110 "Output: verifier predictions and a disagreement report"; GC:90 "identify those artifacts in your full run log"; BR:197 "ranking from saved outputs in a clean environment".
- Spec:280 "the state file and run logs (state file not committed)"; :158 saves only "disagreeing review IDs"; :189 `rank` reads "saved records and membership" with no source named.
- The memo, group inputs and evidence pack appear in no table (Spec:85-94) or named file.
- Fix: export a manifest, run summary, quarantine log with attempts, all verifier predictions, and each group and memo input and output. `rank` and `cost replay` read committed files only, with a clean-clone test.

**3. SHOULD-FIX. No path when a nonempty review ends quarantined.**
- Req: GC:7 "Other failures must be retained with reasons and reduce the completed fraction"; CS:255 `unfinished_classification`; BR:199 "Honest failure accounting earns partial credit".
- Spec:20 "`pass` with no flags"; :240 "fails loudly unless the status is `pass`"; :309 option (b) "accept the checker flag" contradicts both.
- Silent on copies of a quarantined original (Spec:104); pointing at it trips `invalid_cache_reuse` (CS:245).
- Silent on review status after 4 failed temporary attempts (Spec:136), and on `pending` rows at export (GC:59 "completed or quarantined").
- A one-session fresh-input demo (GC:17) can never be `pass`.
- Fix: export always writes and reports status; copies inherit the quarantine; exhausted temporary retries stay `pending`; export refuses while any row is `pending`.

**4. SHOULD-FIX. `run.json` fields are unspecified.**
- Req: CS:180-183 check `version`, `analysis_count`, `analysis_sha256`, `classification_input_fields`. CS:248 invalidates every reuse (176,420 copies) without the last.
- Spec:236 names the file only; :170 covers `allow_multi_issue`.
- Fix: list the five fields, with count and SHA computed from the input path.

**5. SHOULD-FIX. The gzip rule is too wide.**
- Req: GC:53 "Large `.jsonl` files may be gzip-compressed"; CS:173 and CS:145 read CSV and JSON plain only.
- Spec:236 "Large files are gzipped". `membership.csv` and `checkpoint_after.json` (about 26 MB; all IDs are 36 characters) are large.
- Fix: "only `records.jsonl` and `calls.jsonl`".

**6. SHOULD-FIX. Requests in flight at an interruption are never logged.**
- Req: CC:55 "Reconcile uncertain in-flight requests where possible"; CC:23 "all attempted calls".
- Spec:96 saves the call row "in one transaction" with its result; silent on orphans.
- Fix: write a dispatched row before sending; on restart mark orphans `failed` and keep the reservation.

**7. SHOULD-FIX. Nothing freezes `label_config` inside a run.**
- Req: CS:355-362 `call_config_mismatch`.
- Spec:130 cut-off is "provisional" then frozen; :89 results carry no `label_config`; :284 has no run selector.
- Fix: fix the config and prompt hashes at run creation; resume raises on a difference.

**8. SHOULD-FIX. The golden report omits required items, and there are no label examples.**
- Req: BR:101 "the number of ambiguous cases ... per-topic counts"; BR:102 "For entities, inspect unsupported additions. Evaluate needs_review as a prediction"; GC:49 "Write examples of how you applied these shared definitions" (also BR:78).
- Spec:258 lists none of these; :275 holds "the label definitions" only.
- Fix: add both.

**9. SHOULD-FIX. Calculator display gaps.**
- Req: CC:31 "Input checksum, 100 IDs"; CC:32 "effort setting"; CC:34 "rate units, currency, dated price-source links"; CC:35 "Editable budget"; CC:68 "cold and warm runs, with run IDs"; CC:70 "scaling decision".
- Spec:226 and :229 omit these ("Controls shown"); :225 makes warm "the same run again".
- Fix: add them, and give the warm pass its own ID and a saved zero-call record.

**10. NOTE. "Forced by the checker" is unsupported.**
- CS:247 only requires a copy to equal its original; a flag propagated to both would pass.
- Spec:160. Fix: reword as a choice.

**11. NOTE. Stage definitions are incomplete.**
- Req: BR:115 "failure behavior, and stop condition"; BR:124 "bounded backoff".
- Spec 6.2 has no stop or LM Studio outage rule; 6.5 has neither.
- Spec:175 halts on an input with no complaints; Spec:204 does not note that a twice-failed memo trips `missing_model_roles` and `missing_claims` (CS:371, CS:302).

#### Unverified concerns

- Golden texts sit first in run order, so "lowest run order" naming samples (Spec:173) and evidence-pack ties (Spec:197) will favour them. GC:10 bars golden examples from "development prompts and examples"; texts may be allowed.
- If sub-issues (Spec:181) are built with Jev calls logged as `enrich`, each trips `reprocessed_checkpoint`.
- A pilot subtotal near $0.004 rounded to cents would break the doubling test.
- An electricity price stored in `rates.csv` may double along with the API rates.
- `export` and `rank` take no run selector, so a fresh-input demo could overwrite `grading/`.
- The recording must show the full run's first stop to match the exported checkpoints (GC:17).
- `needs_review` from probability alone may not meet GC:49 "Missing context should trigger `needs_review`".
- Delivery of the large export (release asset, BR:151) is unstated.
- The jump from 1 to 16 workers skips CC:57 "then try two".

### State and spending controls: brief

You are a systems reviewer. Your one job: find the ways a design spec's state handling, recovery, spending controls and cost measurement would break or silently give wrong results when it runs for real. You are not reviewing label quality or statistics. You have no stake in this spec being good.

#### What to review

Spec (not yet built): `<repo>/docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md`

It describes a resumable, time-boxed pipeline over a 97 MB CSV of 660,622 reviews: about 484,000 paid HTTP requests to a classifier API (Jev, up to 16 at once, near 75 per second, under a hard $25 project spend cap), about 5,000 requests to a local model server (LM Studio at localhost:1234), a handful of local-model calls for naming and a memo, all state in one SQLite file, plus a cost calculator built on a measured 100-review cold and warm pilot.

#### Files you need (read them; do not rely on the spec's summary)

All under `<repo>/`:
- `CLAUDE.md`: decision trail, measured numbers, and the checker rules already known.
- `feed/Final Assignment - Spotify Reviews Dataset/COST_CALCULATOR.md`: the calculator requirements, including saved state, parallelism, spend reservation, timeouts and the two instructor tests.
- `feed/Final Assignment - Spotify Reviews Dataset/check_submission.py`: read `audit()`, especially the checkpoint, phase and call-log checks (roughly lines 313 to 372).
- `feed/Final Assignment - Spotify Reviews Dataset/GRADING_CONTRACT.md`
- `feed/Final Assignment - Multi Agent Large Data Processing Pipeline.md`: READ LINES 1 TO 225 ONLY (the rest is base64). Lines 82 to 96, 124 and 171 to 179 cover the calculator, retries and parallelism.
- `experiments/2026-10-04/tool-choice/jev_spike.py`, `three_tests.py`, `three_tests_out.txt`, `gemma_spike.py`: throwaway probes showing the real request shapes, measured speeds and token counts.
- `docs/red-team-plan-2026-10-04.html`: an earlier review; honour what it settled.

#### Hard rules

- Read-only. Do not create, edit or delete any file in the repo.
- No network and no model calls. Do not contact `localhost:1234` or `api.typesafe.ai`. Do not run the probe scripts.
- Never open `.env`. Never open `evals/golden_50_labeled.csv` or `evals/dev_150_labeled.csv`.

#### Specific things to hunt for

- Crash windows: for each point where the process can die (mid-request, after the HTTP response but before the write, mid-transaction, during export), what is the state on restart? Can a paid call be lost, a review be sent twice, or a review be marked done without a logged call?
- "A completed review is never sent again" against retries, timeouts with unknown outcome, and in-flight requests at the moment a session ends or is killed.
- One writer thread with 16 workers: back-pressure, ordering, what a checkpoint snapshot sees while results are still queued.
- How a run is identified so that "the same command resumes": what happens if the input path, the seed, the prompt or the cut-off differs between sessions, and what stops two processes running at once.
- One SQLite file holding every run, with "each run starts cold": do the cold pilot, the warm pilot and the full run actually get the cache behaviour the spec claims? Are group and memo cache keys defined well enough to be correct?
- The phase rule (first session `initial`, later sessions `resume`) and the checkpoint rule, traced through a realistic sequence: session 1 killed mid-flight, session 2 resumes, failed attempts in both, duplicate texts whose original finishes in a later session.
- The spend ledger: is the reservation rule a true upper bound? What happens to reservations for requests in flight at a crash? Does the cap really span runs? What about provider billing that the local ledger never sees? Is "request bytes counted as tokens" compatible with the tokens-per-second limiter?
- The rate limiter: requests per second and tokens per second across threads; behaviour on 429; what "halve the rate for a minute" does under 16 workers; whether the stop-after-20-failures rule can fire wrongly or fail to fire.
- Verification stage against a local server: server down, wrong model loaded, model swapped mid-run, memory pressure when the same model also names issues and writes the memo.
- Detecting model version drift from the response's `model` field: what happens to the run when it changes halfway.
- Scale: 660,622 rows, raw answers stored per result, export of large JSONL, memory use, time to compute run order and duplicates.
- Determinism claims: rank and export reproducing byte for byte; anything time-dependent or order-dependent leaking into exported files.
- The cost calculator: is wall-clock time measured correctly with one worker and with overlap; are measured and projected values kept apart so the two instructor tests pass by construction; is local compute cost an honest labeled estimate; can importing or opening the calculator ever trigger a call.
- Secrets and untrusted text: the API key reaching a log, an error message, a saved request or the exported call log; review text containing instructions reaching the naming and memo prompts.
- Anything the spec leaves undefined that an implementer would have to guess.

Ask what the spec MISSES ENTIRELY, not only what it gets wrong.

#### Evidence standard

Every finding needs evidence: the spec line (with line number) and, where a requirement is involved, the source quote with `path:line`. Describe the concrete failing sequence (step 1, step 2, result). A concern you cannot make concrete goes in a separate list headed "Unverified concerns". If the spec already handles something, do not list it.

#### Output (cap about 700 words)

A list of findings, most severe first. For each: a one-line claim; severity (BLOCKER = money lost past the cap, work lost, or a flagged or wrong export; SHOULD-FIX; NOTE); the failing sequence; the evidence quotes; and the smallest change to the spec that closes it. Then "Unverified concerns". No preamble and no summary of the spec.

### State and spending controls: report

SPEC = `<repo>/docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md`; CHK = `<repo>/feed/Final Assignment - Spotify Reviews Dataset/check_submission.py`; CC = `COST_CALCULATOR.md` beside it. Measured figures are from an offline read of `<repo>/experiments/2026-10-04/tool-choice/simple.jsonl`; nothing was run against a model or the network.

**1. BLOCKER. Phase and checkpoints follow session number, so ordinary sequences give a flagged export that cannot be repaired.**
- (a) The full pass is estimated at 1.8 hours (SPEC:220) and the command is `--max-hours 8` (SPEC:284): one session, every call `initial`.
- (b) Session 1 dies before any completion (bad key, 20-failure stop): `before` is empty and all later calls are `resume`.
- (c) Session 1 is killed: there is no "session end" (SPEC:93, 238), so no checkpoint.
- Result: `resume_snapshot_mismatch` and `resume_call_evidence`. Repair is a rewritten log or a second $19 pass.
- Evidence: SPEC:146 "calls in a run's first session are `initial`"; CHK:322 `if not before or not before < after`; CHK:369.
- Fix: store only a session ID. Derive phase and both checkpoints at export, with the boundary at the first session that committed a non-copy completion. The runner forces that session to stop with work pending.

**2. BLOCKER. Paid results exist only in memory until the writer commits; writer failure is undefined.**
- Sequence: `export`, `rank` or a database viewer holds a read lock mid-run; the writer hits "database is locked" and dies; 16 workers keep sending at 75 per second; on restart all of it is sent again. About $10.50 per hour is billed and absent from the ledger, so real spend can pass $25.
- The same window exists on any kill between response and commit, against SPEC:96 "a crash cannot leave a paid call without its result". CC:55: "Reconcile uncertain in-flight requests".
- Fix: commit an intent row (request ID, review, session, reservation) before sending; no commit, no send. Bounded queue, WAL, busy timeout. On start, orphan intents become failed calls with usage unknown and the reservation kept. Stopping means stop admitting, drain, flush.

**3. BLOCKER. No run identity and no process lock.**
- `run`, `rank` and `export` take no run argument (SPEC:284-286), yet SPEC:225 needs "a new run" and then "the same run again".
- A: the full run is complete and the command is repeated; a "none unfinished, so start one" guess re-spends up to the cap.
- B: a second terminal starts the same run. Reviews are sent twice, each process holds its own reserved total, and `resume` calls hit IDs in the first checkpoint: `reprocessed_checkpoint` (CHK:365).
- C: a prompt file, the word list or the splitter is edited under an unchanged version string (SPEC:128): mixed labels under one `label_config`, no flag.
- Fix: a required `--run NAME`, with `--new` to create. On resume, compare input SHA, seed and content hashes of prompt, schema, word list, splitter and cut-off; refuse on mismatch. Hold an exclusive file lock.

**4. BLOCKER. No end state after temporary failures; fatal errors fall into "invalid answer".**
- Wi-Fi drops for 15 seconds and 16 in-flight reviews use all 4 attempts (SPEC:136). Pending or quarantined is unstated. If quarantined, nothing requeues them: `unfinished_classification` (CHK:255), so SPEC:20 "pass" is unreachable.
- A 401, 402, 403 or a changed `model` field (SPEC:132) fails validation, so SPEC:137 pays twice per review and quarantines until the stop rule fires. Model drift mid-run has no ruling.
- Fix: only a parsed 200 with a bad answer is invalid. Exhausted temporary errors return to pending. Auth, billing and model-mismatch responses halt the run with no status change.

**5. SHOULD-FIX. Stop and 429 rules break under 16 workers (SPEC:136, 144).** One 2-second blip fails 16 requests plus retries, 32 "in a row", a false stop; a steady 50% failure rate never fires it. Sixteen simultaneous 429s halve once or sixteen times. Fix: stop on zero successes across a time window; one halving per window, gradual ramp.

**6. SHOULD-FIX. The token limiter has no estimator (SPEC:218).** Measured: 2,463 body bytes against 926 input tokens (ratio 2.46 to 2.93, so SPEC:217's bound holds). Reusing bytes caps speed at 41 per second: 3.3 hours, not 1.8. Responses also report about 203 output tokens each, unpriced (SPEC:216). Fix: limiter uses bytes / 2.4; an explicit output row in `rates.csv`; usage-page reconciliation at every gate.

**7. SHOULD-FIX. Verify has no rule for a dead local server.** SPEC:162 covers only "an invalid answer". With LM Studio down, 5,000 connection errors become "verify failed" and no verify call succeeds: `missing_model_roles` (CHK:371). The sample is drawn "among completed reviews" (SPEC:152), so it shifts if drawn early. Fix: preflight; check `model` on every response; connection errors halt; fix the sample at prepare time; later stages wait for classify to finish.

**8. SHOULD-FIX. The tables cannot feed the calculator.** `runs` holds one start and end (SPEC:87): a warm run with no calls has no stored time, and a two-day run reads as two days (CC:49). The ledger holds dollars (SPEC:94), which fails rate doubling (CC:74). The state file is not committed (SPEC:280), so `replay` and `rank` fail in a clean clone if they read it. Fix: a sessions table with per-stage monotonic times; ledger in units; `replay` and `rank` read committed files only.

**9. SHOULD-FIX. Group and memo cache keys omit model, settings and run scope (SPEC:176, 206).** After a memo-model change (SPEC:208) the old memo is served.

**NOTE.**
- The cap lives in one local file: probe spend is not seeded and there is no provider-side limit (CC:57).
- A stale plain `records.jsonl` beside a new `.gz` is the one the checker reads (CHK:155-157).
- `calls` error text (SPEC:90) can carry provider error bodies; add key redaction.
- Undefined: copies of a quarantined original; timeout length; the memo number check on digits inside quotes (SPEC:202).

**Unverified concerns**
- `urllib` opens a new TLS connection per request; 75 per second for hours is untested.
- LM Studio may silently truncate long prompts or answer with whichever model is loaded.
- Laptop sleep mid-session: unknown-outcome timeouts and a limiter burst on wake.
- Whether failed attempts or output tokens are billed.
- Export size against GitHub's 100 MB file limit.
