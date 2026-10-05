# Spotify Insight Pipeline: design spec

Date: 2026-10-04. Status: draft for Travis's review, revised the same day after an independent review (section 13). Nothing here is built.

Every line is marked by where it stands:

- **Decided**: Travis ruled on it. The full trail is in `CLAUDE.md`.
- **Proposed**: drafted here to complete the design. It needs Travis's yes. Section 12 lists every proposed item in one table.

Numbers are labeled *measured* (with the file that holds the evidence) or *estimate*. Nothing unmeasured is stated as fact.

## 1. Goal

Turn 660,622 Spotify app reviews into a ranked list of product issues and a short decision memo. Every number in the memo traces to a saved calculation and to source reviews.

The memo answers the brief's question: where should the next quarter of product effort go?

Done means:

- `check_submission.py check` returns `pass` with no flags and a coverage value of 1.0. That is the target. If a nonempty review ends quarantined, the checker says `review_required`; the export is still written and the README reports the shortfall.
- All 660,609 nonempty reviews have valid labels. The 13 empty ones are quarantined as `empty_review_text`.
- Ranking regenerates from committed files with no model call and gives identical files.
- The cost calculator replays offline and passes both instructor tests.
- The golden 50 is scored once, on the final setup.
- The README links evidence for each rubric point.

Not in this version: sub-issues inside a topic (decided later, section 6.4), a second business ranking, trend analysis by month, a web interface, any cloud model.

## 2. Decisions this design rests on

All **Decided**, 2026-10-04.

| Area | Decision |
|---|---|
| Labeler | Jev `jev-1.13.0`, direct TypeSafe API, one request per review, simple style, Jev picks the quote sentence |
| Speed | One request at a time for the cost pilot. Later runs: up to 16 at once, capped near 75 per second |
| Second opinion | Gemma 26B, local, blind, on a random sample of 5,000, one review per request |
| Review flag | `needs_review` is true when the lowest of Jev's three top probabilities (topic, intent, severity) is under a cut-off. Travis sets the number later, on development labels only |
| Weak spots | Tighter intent wording for slogans. Planted slogan and injection tests in `evals/`. Injections get a test only, no guard |
| Fallback | None. Hard cases are flagged, never re-labeled |
| Grouping | One issue per topic, eight at most. Code assigns. The group model only names and describes |
| Writing model | Gemma 26B for issue names and the memo. Travis reads the pilot memo and rules on keeping it |
| Budget | $25 of total Jev spend for the whole project |
| Golden 50 | Labeled by Travis by hand. Scored once at the end. Never in a prompt, a cut-off or grouping |
| Gates | 100, then 500, then 10,000, then the full file. Each needs an explicit go |

Known limits already accepted: the quote and the topic can come from different sentences (how often is unmeasured); the injection miss rate is reported, not fixed.

## 3. Shape

```
input CSV (any path)
   |
1. prepare    code            rows, hashes, duplicates, run order, quarantine of empty text
   |
2. classify   Jev             role "enrich": topic, intent, severity, tone, quote sentence
   |          code            mapping, validation, entities, needs_review
3. verify     Gemma 26B       role "verify": blind re-label of a declared sample
   |          code            comparison and disagreement report
4. group      code            membership: one issue per topic
   |          Gemma 26B       role "group": issue names and descriptions
5. rank       code            counts, severity sums, means, order
   |
6. memo       Gemma 26B       role "memo": recommendation from the ranked table and evidence pack
   |          code            checks every cited ID and number
export        code            grading/, cost/, evals/, run evidence, then the supplied checker
```

What code owns: reading the file, record accounting, hashing, duplicate reuse, validation, budgets, rate limits, retries, state, arithmetic, ranking, every exported number.

What models own: reading review language (Jev, Gemma) and writing prose (Gemma). A model never counts, sorts or decides what runs next.

The classifier sees `review_text` only. Stars and other fields are kept for analysis and never enter a prompt or a cache key.

## 4. State

**Decided:** state lives in one SQLite file; a run saves after every request and resumes with the same command; runs are time-boxed (`--max-hours`).

**Proposed:** the one file holds every run. The spend ledger sits in the same file and covers all runs, which is how the $25 cap spans the gates and the full run. The ledger starts with the $0.053 already spent on probes (*measured*, `experiments/2026-10-04/README.md`).

**Proposed:** every command names its run (`--run NAME`; `--new` creates one). At creation the run saves the input's SHA-256, the seed, and a content hash of each prompt, the schema, the feature-word list, the sentence splitter and the cut-off. A resume compares all of them and refuses on any difference, so one `label_config` can never cover two different setups. One process at a time holds a lock on the state file.

**Proposed:** each run starts cold. A run reuses only its own saved results (that is what resume is). The one exception is the warm pilot, a second run pointed at the cold pilot's results on purpose. The full run does not reuse results from the 100, 500 or 10,000 gates. Re-labeling those reviews costs about $0.41 (*estimate*). In return the final export contains only full-run calls, and the open instructor question about reusing early-run calls no longer matters.

**Proposed** tables:

| Table | Holds |
|---|---|
| `runs` | run name, input path and SHA-256, seed, code version, `label_config`, verify, group and memo configs, and the content hashes above |
| `sessions` | per session and stage: start and end on a monotonic clock, worker count, how it ended |
| `reviews` | per run: `review_id`, the six source fields, `source_sha256`, text key, run order, status (`pending`, `completed`, `quarantined`), reason, attempt count, `cache_source_id` |
| `results` | per run and text key: topic, intent, severity, sentiment, entities, quote, `needs_review`, Jev's raw answer with probabilities, the `model` field from the response |
| `calls` | one row per attempt: `request_id`, role, review IDs, model, outcome, `label_config`, token counts, HTTP status, error text with any key removed, start time, seconds, session ID |
| `verify` | per run and review: Gemma's topic, intent and severity, and the request ID |
| `issues`, `membership` | issue ID, name, description; one row per issue and review pair |
| `artifacts` | each group and memo input and output, keyed by a hash of the input plus the model, settings and prompt version |
| `ledger` | every reservation and actual charge in billed units (tokens), with the request ID. Dollars are computed from the rates file |

**How a request is saved:**

1. Before sending, the run commits an intent row: request ID, review, session and reservation. No commit, no send.
2. After the answer passes validation, the result, the finished call row and the actual charge are saved in one transaction.
3. If the process dies between the two, the intent has no result. On restart it becomes a failed call with usage unknown, its reservation stays counted as spent, and the review goes back to `pending`. So a crash can cost one paid request per in-flight worker, 16 at most, and each is visible in the log.
4. If the writer cannot commit, the run admits no new work. The file uses write-ahead logging and a busy timeout, and the queue to the writer is bounded.

## 5. Stage 1: prepare (code)

- **Input:** any CSV with the six source fields. Read with Python's `csv` module in strict mode. No trimming and no Unicode normalization anywhere.
- **Hashing:** `source_sha256` uses the checker's `row_sha`. The pipeline keeps its own copy of that function, and a test asserts both give the same hash on real rows.
- **Empty text:** `review_text.strip()` is empty. Status becomes `quarantined`, reason exactly `empty_review_text`. Never sent to a model.
- **Everything else is labeled.** That includes the 12,268 reviews with no letter or digit and the reviews whose text is the literal `None`.
- **Duplicates:** reviews with byte-identical text share one result. The first in run order is the original and gets the model call. Each copy keeps its own row and points to the original with `cache_source_id`. Copies are counted separately in every total.
- **Run order:** ascending SHA-256 of `seed:review_id`. The seed comes from `manifest.json` (`berkeley-fall-2026-assignment-5-v1`) and can be set for other inputs. Any finished stretch of a run is a fair sample of the file.
- **Verify sample:** picked here, before any model call (section 6.2).
- **Output:** the `reviews` table and `grading/ingestion.json` (from the checker's `profile`).
- **Guards that raise, when the input is the supplied file:** 660,622 rows, 13 empty texts, 484,189 distinct nonempty texts, 159,701 missing app versions, no repeated IDs, file SHA-256 `1fc85de6...2fcef6`. For any other input these are skipped and the run says so.
- **Stop:** every row is in the table and completed-or-pending plus quarantined equals the row count.

## 6. Stages 2 to 6

### 6.1 Classify (Jev, role `enrich`)

**Request, Decided:** one request per original text, model pinned to `jev-1.13.0`. Questions: topic (8 choices), intent (5 choices), severity (5 named choices, never digits), tone (a 5-step score). If code splits the text into more than one sentence, a fifth question asks which sentence states the most serious problem. Option order is shuffled in a repeatable way derived from the text.

**Wording, Proposed:** prompts live in `prompts/` as versioned files, with a file of worked examples showing how each definition was applied (the contract asks for these). The starting point is the wording in `experiments/2026-10-04/tool-choice/jev_spike.py`. The slogan change to the intent question is drafted with Travis, then tried on planted cases and development rows (a paid call of a few cents that needs a go). The wording is settled before the 100 gate, so the pilot measures the real setup. Any change is a new `label_config`: after a gate that means rerunning the gate, and after the full run it means a second full pass, which the $25 cap does not cover.

**Code turns the answer into a record:**

| Field | Rule |
|---|---|
| `topic`, `intent` | Jev's choice |
| `severity` | named choice mapped to an integer 1 to 5 |
| `sentiment` | tone score divided by 2, minus 1. A score outside 0 to 4 is an invalid answer, never clamped into range |
| `evidence_quote` | the sentence Jev picked. For one-sentence text, the whole text with outer whitespace removed. Always an exact piece of the source |
| `entities` | words from a fixed feature-word list found in the text. May be empty. **Proposed:** the list itself still has to be agreed |
| `needs_review` | lowest of the three top probabilities is under the cut-off |
| `label_config` | **Proposed:** one string naming model, prompt version, schema version and the cut-off, for example `jev-1.13.0/prompt-v1/schema-v1/cut-0.70` |

**Cut-off, Proposed:** each gate run needs a number, so Travis names a provisional one when he gives the go for the 100 gate. He freezes the final number before the full run. Because it is part of `label_config`, it cannot change after the full run starts without new work.

**Validation:** allowed labels, strict types, finite sentiment in range, and a non-blank quote that is an exact substring. The `model` field is logged on every call.

**Failure behavior:**

- *Temporary error (429, 5xx, network, timeout):* wait and retry with growing delays and jitter, **Proposed** up to 4 attempts. If all fail, the review goes back to `pending` and is tried again later in the run or in the next session. A temporary error never quarantines a review.
- *Fatal response (401, 402, 403, or an answer whose `model` is not the pinned one):* the run halts at once and changes no review's status. A changed model version is Travis's call.
- *Invalid answer (a normal response that fails validation):* retry once (the brief's limit). If it fails again, the review is `quarantined` with reason `invalid_model_output` and counts as not classified. Its copies are quarantined with the same reason and carry no cache pointer.
- *Request over Jev's documented limits (255 options, 32,000 tokens):* quarantined with a reason. Nothing is cut short silently. The red team measured a maximum of 164 sentence pieces, so none is expected.
- Every attempt is its own row in `calls` with a unique `request_id`.

**Finished means finished:** a review is marked `completed` only after its answer passes validation. A completed review is never sent again.

**Stop:** nothing pending; or the time box ends; or the next reservation would pass the cap; or a fatal response; or the failure stop (**Proposed**: no request has succeeded for 60 seconds while requests are being sent). Stopping means admit no new work, let in-flight requests finish, save.

**Resume evidence:** the checker needs a `before` checkpoint that is non-empty and strictly smaller than `after`. The full pass is about 1.8 hours (*estimate*), so it would finish inside one session unless it is stopped. So the full run is stopped once on purpose with work still pending, and that stop is what the recording shows. Every completion is saved with its session ID, so nothing depends on a clean shutdown. At export, code finds the boundary: the end of the first session that saved at least one new (non-copy) completion while reviews were still pending. Calls up to the boundary are `initial`. Later calls are `resume`. `checkpoint_before` is the completed list at the boundary. If a run has no such boundary, export says so plainly, because the checker will flag it.

### 6.2 Verify (Gemma 26B, role `verify`)

**Decided:** blind. Gemma gets the review text and the label definitions. It never sees Jev's answer. One review per request. Code compares.

**Sample, Proposed:** the nonempty reviews with the lowest SHA-256 of `verify-seed:review_id`, using a second seed so the sample is not the development reviews the wording was tuned on. It is fixed at prepare time, before any model call, so it cannot depend on which reviews Jev managed to label. Size is 5,000, or every review when the run is smaller. So the 100 pilot verifies all 100, which also scores Gemma at one per request against the development labels at no extra cost. The seed and size are saved with the run. Verify starts after classify has finished.

**Call settings (from the probe):** LM Studio at `localhost:1234/v1`, `temperature` 0, `reasoning_effort` `none`, `response_format` of type `json_schema`. Code checks returned strings for leaked template tokens.

**Proposed:** one request at a time in the pilot, up to four at once in later runs (0.27 s per review *measured* at four, single run of 50).

**Before the first request:** the stage checks that the server answers and that the expected model is loaded. It checks the `model` field on every response.

**Output:** every verifier prediction, saved, and `evals/verify_report`: agreement per field, a confusion table, and the disagreeing review IDs with both answers.

**Proposed:** a disagreement is reported but does not change `needs_review`. This is a choice, not a checker rule. The checker only requires a copy to carry the same label fields as its original. Keeping the flag a function of the text and `label_config` alone makes that automatic and gives the flag one meaning for sampled and unsampled reviews.

**Failure:** an invalid answer is retried once, then recorded as "verify failed" in the report. The Jev record is untouched. A connection error or a wrong model halts the stage; it is never counted as a failed review, because an export with no succeeded `verify` call is flagged.

**Stop:** every sampled review has a prediction or a recorded failure; or the time box ends; or the server check fails.

**Guard that raises, Proposed:** agreement of exactly 100% on 50 or more reviews. Section 12 item 25 proposes a stronger version, because a real leak would more likely show as 95% than 100%.

**Comparison test:** a separate test copy of saved results with labels changed on purpose. The comparison must flag each one. This tests the comparison code, not Gemma's ability to catch Jev's mistakes. It lives in `evals/` and never touches `grading/`.

**What agreement does and does not show:** agreement between the two engines is not accuracy. On the 100 pilot reviews they matched on 43 of 48 non-complaints but only 34 of 52 complaints and cancellations, the rows that feed the ranking (*measured*, saved answers, Gemma at 10 per request). On the same reviews the billing severity sum was 20 from Jev and 9 from Gemma, and usability 38 against 55. The top four topics kept the same order.

### 6.3 Group (code, then Gemma 26B, role `group`)

**Decided:** every completed `complaint` or `cancellation` review joins exactly one issue, the one for its topic. `allow_multi_issue` stays `false`.

- **Issue IDs, Proposed:** `issue-access`, `issue-billing`, and so on. They are stable and sort in a fixed order for ties.
- **Naming:** one Gemma call per issue that has members. **Proposed:** it reads up to 30 quotes with their review IDs and returns a short name and a one-sentence description. The quotes are picked by a third seed among the issue's originals. Run order is not used here, because it would put the golden 50 texts first. Code checks length and that both are non-blank.
- Names and descriptions never change membership or ranking.
- **Failure:** retry once, then fall back to the topic name and the contract's definition, and log it. If no naming call succeeds, the stage stops, because the checker needs one succeeded `group` call. An input with no complaints has no issues and no naming call; the run reports that.
- **Cached by input:** the same sample under the same model, settings and prompt version reuses the saved name, so a warm run makes no new call.
- **Output:** `issues` and `membership` tables, saved as `issues.json` and `grading/membership.csv`.

### 6.4 Sub-issues (not built in this version)

**Decided:** the baseline is one issue per topic. Splitting a topic into sub-issues is an optional later step. Travis decides after the first full Jev pass and before the final export, because it changes issue IDs. It would need a raise of the cap (up to about $10, *estimate*).

Why it may be wanted: on the 100 pilot reviews, `other` ranked second by severity sum (*measured*, saved Jev answers), and `other` names nothing to fix.

### 6.5 Rank (code only)

For each issue: `complaint_count` (members), `severity_sum`, `mean_severity` (sum over count, six decimals, half-up, using `Decimal`), `priority_score` equal to `severity_sum`. Order by score descending, then issue ID ascending. Ranks start at 1. All other numbers are plain integer strings.

One command rebuilds `ranking.csv` from `grading/records.jsonl` and `grading/membership.csv`, which are committed files, with no model call and no state file. A test runs it twice in a clean copy of the repo and compares the files byte for byte.

**Failure and stop:** the command raises if a member review is missing from the records or is not a complaint or cancellation. It ends when the file is written.

### 6.6 Memo (Gemma 26B, role `memo`)

**Input, never the raw CSV:**

- the ranked table and the issue names and descriptions;
- a claims table that code builds first: one claim ID for each issue and metric;
- an evidence pack, **Proposed:** up to 5 quotes per issue with review IDs, taken from its members sorted by severity (highest first), then by the third seed. The pack labels them as the most severe examples, not typical ones;
- run facts: completed and quarantined counts, the verifier's agreement on complaints and on the rest, the share flagged `needs_review`, and the list of known limits.

**Output:** a markdown memo with the priority, the supporting numbers with their claim IDs, the alternatives, representative review IDs, and the limits.

**Code check:** every issue ID, review ID and claim ID in the memo exists in the input. Every number beside a claim ID equals that claim's value. Any other number must be one of the run facts. Revenue, churn and causal claims are rejected, because the data cannot support them. This check proves the memo copied its numbers correctly. It does not prove the argument is sound; that is the human read.

**Failure:** one retry with the errors listed. If it fails again the stage stops with no final memo, and Travis decides what to do. An export with no memo is flagged for a missing role and missing claims.

**Cached by input:** the same ranked table and evidence pack under the same model, settings and prompt version reuse the saved memo, so a warm run makes no new call. A change of memo model is a new key.

**People:** Travis reads the pilot memo at the 100 gate and rules on the memo model. He inspects the final argument, and any edit he makes goes through the same code check. `grading/claims.csv` holds the claims the final memo cites.

**Limit:** quotes are customer text and can contain instructions or personal details. The memo prompt passes them as quoted data, the code check catches invented IDs and numbers, and Travis reads the final memo for personal details.

## 7. Money, speed and time

**Decided:** $25 cap on total Jev spend. Workers share one rate limiter and one ledger. Before each request the run reserves its worst-case cost. It stops admitting work when spent plus reserved plus the next reservation would pass the cap.

- **Rate:** $0.042 per million input tokens (docs.typesafe.ai/models, checked 2026-10-04, as used in the probe). Jev also reports about 215 output tokens per response (*measured*, `simple.jsonl`). Whether those are billed is unknown. `rates.csv` carries an output-token row, and spend is checked against the TypeSafe usage page at every gate.
- **Reservation, Proposed:** the request body's size in bytes, counted as tokens. A request body is 2.46 to 2.93 bytes per input token (*measured* on the 100 pilot requests), so this always overstates.
- **Limiter:** requests per second (75) and tokens per second, both under the documented 80 and 100,000. **Proposed:** the token limiter estimates tokens as bytes divided by 2.4. Using raw bytes would hold the run to about 41 requests per second.
- **After a 429, Proposed:** the shared rate halves at most once per 10-second window and climbs back slowly.
- **The ledger is local.** It cannot see provider billing it was not told about, and the spec knows of no limit on TypeSafe's side. Travis checks the console for one.
- **What $25 covers (*estimates* from $0.0039 per 100 reviews *measured*):** the gates, about $0.41 together, and the full pass, about $19, which labels the gate reviews again. With the $0.05 already spent, about $5 is left for retries and the wording trial. A second full pass or sub-issues needs Travis to raise the cap.
- **Time (*estimates*):** full Jev pass about 1.8 hours at 75 per second; Gemma on 5,000 about 23 to 48 minutes. Sustained Jev speed is unmeasured until the 10,000 gate.

## 8. Cost calculator (`cost/`)

- **Two commands.** Offline replay is the default and needs no key. The paid pilot is a separate command that must be asked for by name. Importing or opening the calculator starts nothing.
- **Replay reads committed files only:** `pilot_calls.jsonl`, `usage.csv` and `rates.csv`. It never opens the state file.
- **Pilot:** `cost_100.csv` unchanged, a new run, one worker, all six stages. Then a warm pass under its own run ID that points at the cold run's saved results: zero new enrich and verify calls, and zero group and memo calls because those are cached by their inputs. The warm pass saves a record that says zero calls were made.
- **Report:** the input checksum and the 100 IDs; per stage: provider, model, effort setting, prompt and schema version, batch size, workers, completed and failed, unique texts, cache hits, requests and attempts, tokens, rate with its unit, currency and dated source link, cost, seconds. Also cost per 1,000 rows, cost per completed record, throughput, cold and warm time, and the scaling decision.
- **Time** comes from the monotonic clock in the `sessions` table, per stage, never from summed request times.
- **Three separate totals:** Jev API spend; local compute for Gemma as a labeled estimate (measured seconds times an assumed power draw and electricity price, both editable, kept in their own file so the rate-doubling test does not touch them); and unknown costs, which stay marked unknown.
- **Projection:** each stage from its own work count. Enrich: 484,189 requests with reuse, 660,609 without. Verify: 5,000. Group: at most 8. Memo: 1, added once. Input size is projected from the full file's text volume computed in code, plus the per-request overhead measured in the pilot, because pilot reviews are shorter than the average distinct text (red team). A base case and a conservative case with more retries. A warning when a case passes the cap.
- **Controls, all editable:** spending limit, output-token cap, maximum workers, fallback fraction (zero by design).
- **Instructor tests, as automated tests:** doubling the API rates doubles the API subtotal and leaves local cost and measured time unchanged; changing the projected row count leaves the measured results unchanged. Costs are not rounded before these tests, since the pilot's total is under one cent.
- **Files:** `pilot_records.jsonl`, `pilot_calls.jsonl` (cold and warm, each with its run ID), `rates.csv`, `usage.csv`, `report.md`, and a README with both commands.
- The calculator is refreshed after the 500 and 10,000 gates.

## 9. Export

### `grading/`

Code writes these from the full run's state:

- `run.json` with all five fields: `version` (`a5-audit-v1`), `analysis_count` and `analysis_sha256` computed from the input file, `classification_input_fields` (`["review_text"]`), and `allow_multi_issue` (`false`).
- `ingestion.json`, `records.jsonl`, `membership.csv`, `ranking.csv`, `claims.csv`, `calls.jsonl`, `checkpoint_before.json`, `checkpoint_after.json`.
- Only `records.jsonl` and `calls.jsonl` may be gzipped. The checker reads every other file plain. Export removes the plain file when it writes the gzipped one, since the checker flags both together.
- Both checkpoints list completed reviews only, never quarantined ones. The boundary rule is in section 6.1.
- `calls.jsonl` holds the full run's calls only. Planted cases, wording trials and gate runs stay in `evals/` and the run logs.

Export refuses to run while any review is still `pending`. Otherwise it always writes the folder, runs the supplied checker, and reports the status and every flag. It does not hide a `review_required` result. This happens before memo numbers are treated as final, since one bad record changes the ranking. `local-reference.json` and `self-check.json` stay outside `grading/`.

**Open, Travis to rule:** a failed call has no token counts. The checker flags a missing count, and the project rule says an unknown is never silently zero. The two choices are in section 12.

### Run evidence (committed, large files as release assets)

The brief asks for these beside the grading folder: a run manifest (source checksum, code version, prompts, model IDs, settings, outputs), `run_log.jsonl`, `run_summary.json` (stage timing, statuses, attempts, failures, usage, charges or labeled estimates, the spending limit, resume evidence), `quarantine.jsonl` with reasons and attempt counts, every verifier prediction, each group and memo input and output, and `memo.md`. All are written from the state file by the export command, so a reader never needs the state file itself.

## 10. Tests and evaluation

**No network, run on every change:**

- hashing equals the checker's `row_sha`; sentence pieces are exact substrings; label mapping; ranking strings and rounding; duplicate reuse rules; limiter and ledger (reserve, stop at the cap); the boundary rule for checkpoints and phases; the memo check.
- **End to end with stand-in models:** a small synthetic CSV runs through all six stages, including one deliberate stop and resume, then the supplied checker must return `pass`. The stand-in for Jev replays the 100 recorded responses in `simple.jsonl`, so the test exercises real answer shapes, not invented ones.
- **Interrupted run:** kill mid-run, resume, the checker passes, and no completed ID is sent twice.
- **Awkward paths from the brief:** malformed output, missing text, an ambiguous label, a temporary API failure, an injected instruction, a deliberately wrong label. Each has a test and a recorded outcome.

**With real models, each needing a go:**

- planted slogan and injection cases against the final wording (results in `evals/`);
- development-label scores for Jev and for Gemma at the 100 gate, per field;
- the two outside raters (section 12 item 30): already run on the development, boycott and planted reviews; run on the golden texts only after the golden labels are frozen, for an agreement figure and a count of ambiguous cases;
- the golden 50, once, after the full run. The report holds: topic and intent agreement; exact severity agreement and mean error, signed and unsigned; sentiment mean error; per-topic counts and confusion tables; the number of ambiguous cases; `needs_review` scored as a prediction (how many wrong labels it caught, how many right ones it flagged); the exact-copy quote check; and the list of disagreements. Travis inspects whether each quote supports its label and whether any entity is unsupported. The script reads the label columns; they never reach a prompt or the assistant's context.

**Known weaknesses of the labels (open, section 12 items 19, 20, 23 and 24):**

- Development labels were revised only on rows where a model disagreed. Before revision Jev scored 21 of 29 on all three fields; after, 24 of 29 (*measured*, `experiments/2026-10-04/README.md`). One row still carries a severity the guide itself calls a slip, and it counts as a Jev hit because Jev made the same call. Two outside raters later gave the revised value on all five revised rows, and sit below the hand label's severity on four other rows (*measured*, `docs/validation-log.md` entry 12).
- The same 29 rows are used to tune wording, to pick the cut-off and to compare engines. Nothing is held back.
- The planted slogan and injection cases were written by the assistant, who also tunes the wording against them. The outside raters matched that answer key on 24 and 25 of 25, and a real boycott sample with a held-back half now exists.
- One person labels. There is no second labeler to measure how firm the labels are. The instructor's private sample is the only independent check.

**Guards against a measure that reads itself (raise, never warn):**

- known counts in prepare (section 5);
- one topic above 95%, or `needs_review` all true or all false, over 500 or more reviews;
- verifier agreement of exactly 100%;
- a cost report with zero tokens.

These thresholds are placeholders. Section 12 item 25 proposes bands tied to the previous gate and a test that each guard fires.

**Human only:** the golden labels, the interrupt-and-resume recording, reading the final memo.

## 11. Layout and commands (Proposed)

Python 3.14, standard library only, so setup is clone and run. No dependencies to install.

```
pipeline/     prepare, classify, verify, group, rank, memo, export, state, limits, jev, gemma, cli
prompts/      one versioned file per role, the label definitions, and worked examples
cost/         calculator, pilot evidence, report
grading/      the export
evals/        label sheets, planted cases, reports
tests/
runs/         run evidence (committed); the state file (not committed)
```

```sh
python3 -m pipeline run    --run NAME --new --input PATH.csv   # start a run
python3 -m pipeline run    --run NAME --max-hours 8            # resume it; same command each time
python3 -m pipeline export --run NAME                          # grading/, run evidence, then the checker
python3 -m pipeline rank                                       # ranking from committed files, no model
python3 -m cost replay                                         # offline, default
python3 -m cost pilot --go                                     # paid, explicit
```

Order of work: the wording trial, then the 100 gate (cost pilot, all stages), 500, 10,000, the full run in time-boxed sessions with one deliberate stop, the golden score, the README. Class 7 needs the 500 run, the golden labels and the calculator.

## 12. Proposed items that need Travis's ruling

Items 1 to 16 are from the first draft. Items 17 to 29 came out of the review.

| # | Item | Proposed | Section |
|---|---|---|---|
| 1 | Runs and reuse | One state file for all runs; every run starts cold; no reuse of gate results in the full run | 4 |
| 2 | Tables | The tables listed | 4 |
| 3 | `label_config` | Names model, prompt version, schema version and the cut-off | 6.1 |
| 4 | Cut-off timing | Provisional number at the 100 gate, frozen before the full run | 6.1 |
| 5 | Feature-word list | Contents to be agreed | 6.1 |
| 6 | Prompt wording | Start from the probe's wording; slogan change drafted together and tried before the 100 gate | 6.1 |
| 7 | Retries and stops | 4 attempts on temporary errors, then back to pending; after a 429 the rate halves at most once per 10 seconds; stop when nothing has succeeded for 60 seconds | 6.1, 7 |
| 8 | Verify sample | Second seed; fixed at prepare time; 5,000 or the whole run if smaller; up to four Gemma requests at once after the pilot | 6.2 |
| 9 | Disagreement and `needs_review` | Disagreement is reported only; it does not change the flag. A choice, not a checker rule | 6.2 |
| 10 | Issue IDs and naming input | `issue-<topic>`; up to 30 quotes per naming call, picked by a third seed | 6.3 |
| 11 | Memo evidence pack | Up to 5 quotes per issue, most severe first | 6.6 |
| 12 | Reservation rule | Request bytes counted as tokens | 7 |
| 13 | Failed calls with unknown tokens | (a) write 0 plus a field `usage_known: false` and report the count in the README, or (b) leave the counts out and accept the checker flag | 9 |
| 14 | Dependencies and layout | Standard library only; the folders and commands shown | 11 |
| 15 | Key name | **Done 2026-10-04.** `.env` now uses `TYPESAFE_API_KEY`, the brief's name | |
| 16 | Instructor questions | Still worth sending: is one issue per topic acceptable, and where are side experiments reported. The reuse question is moot under item 1 | |
| 17 | Run names and locking | Every command takes `--run NAME`; resume refuses if the input, seed, prompts, schema, word list, splitter or cut-off differ; one process per state file | 4, 11 |
| 18 | The deliberate stop | The full run is stopped once on purpose with work pending. Either Travis stops it by hand during the recording, or a `--stop-after N` option does it | 6.1 |
| 19 | Label freeze | **Decided 2026-10-04: yes.** A label file is committed and its SHA-256 recorded before model output for its rows is seen. A golden label does not change after the freeze; a plainly wrong one stays and the score is shown both ways. The guide's last lines now say this. The development sheet as it stands is commit `bb5f440`, SHA-256 `febbfaee...00cd6dd6` | 10 |
| 20 | Development labels already seen | **Decided 2026-10-04: keep them.** Always report both scores (21 of 29 before revision, 24 after). They are no longer used to pick the cut-off. Two outside raters then labeled them blind: both give the revised value on all five revised rows | 10 |
| 21 | Verifier report depth | Agreement split by complaint and cancellation against the rest, and per topic; the sample ranked on Gemma's labels beside Jev's, to show whether the order holds | 6.2 |
| 22 | Verifier wording | Gemma gets the contract's definitions word for word, not the paraphrase written for Jev, so the two share less | 6.2 |
| 23 | Slogan and injection cases | **Decided 2026-10-04.** 60 real boycott reviews picked by hash (`evals/boycott_60.csv`), 30 to tune on and 30 held back to score once. Two outside raters label them first; Travis labels blind only where they differ, plus a check sample. The raters also confirmed the planted cases' answer key (24 and 25 of 25) | 10 |
| 24 | Cut-off evidence | **Decided 2026-10-04.** The outside raters label all 150 development rows blind. Travis hand-labels the rows where they differ plus 15 agreed rows picked by hash. The rows are then split by hash into a wording half and a cut-off half | 6.1, 10 |
| 25 | Guards | Bands around the previous gate's values in place of fixed thresholds; a test that verifier requests are identical with and without Jev's answers present; one planted failure per guard; the nested 100 must get identical labels at every gate | 10 |
| 26 | Memo check | Claim ID and issue ID in the same sentence; the recommendation names rank 1 or says why not; run facts recomputed from exported files; some quotes picked by hash beside the most severe | 6.6 |
| 27 | Output tokens and the limiter | **Decided 2026-10-04: settle it with a test batch.** Send a small known batch, then compare the usage page with input tokens times the rate. Until then output-token billing stays marked unknown. Still proposed: the token limiter uses bytes divided by 2.4, and `rates.csv` carries an output-token row | 7 |
| 28 | Gate pass marks | Before each gate runs, name the numbers that would block the next go | 11 |
| 29 | Provider-side limit | Travis checks whether the TypeSafe console offers a spending limit and sets it | 7 |
| 30 | Outside raters | **Decided and run 2026-10-04.** Claude Fable 5.1 and GPT-6 Astra label reviews blind as third-party raters, under a $10 cap per provider. They see the review text and the contract's definitions word for word, and nothing from Jev, Gemma or Travis. Their labels tune and mark disputed rows; they never support an accuracy claim. The golden 50 is frozen before either sees those texts. Results are in `docs/validation-log.md` | 10 |

## 13. Independent review, 2026-10-04

The full record, with each reader's brief and report as written and the outcome of every finding, is `docs/spec-review-2026-10-04.md`. Every check run so far is listed in `docs/validation-log.md`.

Three readers who had not seen the reasoning behind the first draft each read it against the source files: one for measurement validity, one for the contract and checker, one for state and spending controls. Every finding had to quote a source line. The top findings were then checked against those lines. All three are the same model family as the draft's author, so they can share its blind spots.

Fixed in this revision, because the source files leave one answer:

- **Resume evidence (two readers).** The first draft took the `before` checkpoint at the end of the first session. A run that finishes in one session would have been flagged. Now the run is stopped once on purpose and the boundary is found at export (6.1).
- **Lost paid calls (two readers).** The first draft claimed a crash could not leave a paid call without its result. That was wrong. Now an intent row is saved before each request (4).
- **Failure end states (two readers).** Temporary errors return a review to pending; fatal responses halt the run; copies of a quarantined original are quarantined (6.1).
- **Ranking and replay** read committed files only, so a clean clone can rerun them (6.5, 8).
- **Export** always writes and reports the checker's status, and writes all five `run.json` fields. Only the two JSONL files may be gzipped (9).
- **Run evidence** the brief asks for is now listed (9).
- **Golden report** now includes the measures the brief asks for, among them `needs_review` scored as a prediction (10).
- **Verify** has a server check and a fixed sample, and saves every prediction (6.2).
- **Cache keys** for names and the memo include the model and settings (6.3, 6.6).
- **Naming and evidence samples** no longer use run order, which would have put golden texts first (6.3, 6.6).
- **A wrong claim removed:** the first draft said the checker forces disagreement to stay out of `needs_review`. It does not (6.2).

Left for Travis, because each is a real choice: items 17 to 29 in section 12.

Raised but not checked against a source: whether Jev bills output tokens or failed attempts; whether one new connection per request holds at 75 per second for hours; whether LM Studio silently cuts long prompts; laptop sleep mid-session; whether the gzipped export fits under GitHub's 100 MB file limit.
