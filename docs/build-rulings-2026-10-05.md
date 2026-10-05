# Decisions made during the build, 2026-10-05

Travis said "build" and asked not to be checked in with. The pipeline was then built task by task from `docs/superpowers/plans/2026-10-05-spotify-insight-pipeline.md`. Wherever the plan was silent, wrong, or in conflict with itself, the executor decided and wrote the decision down with what it costs if it is wrong. This file is that record, in the order the decisions were made. Nothing here was asked of Travis at the time; each can be reversed.

Lines marked **Note** record a fact found while building, not a decision.

## Setup

- **Ruling 1.** Work on a feature branch in this checkout, not a separate worktree. the gates need the gitignored inputs that live only here (the 97 MB CSV, .env) and Travis reads files in this directory; he asked not to be checked in with. *Cost if wrong: main's checkout sits on build/pipeline until the branch is merged; `git switch main` undoes it.*
- **Ruling 2.** No model call, local or paid, at any point in this run. Real clients are built and tested against a local http.server only. Gates need Travis's go. *Cost if wrong: none.*

## Before Task 1

- **Ruling 3.** T2 create_run / T3 prepare: T3 says the run row and every review row are written in one transaction, but T2 produces create_run as its own call. neither function commits; the caller wraps both in one transaction (`with db:`). T3's crash test raises inside that block. *Cost if wrong: one wrapper moved.*
- **Ruling 4.** T5 begin_attempt(db, ledger, ...) / finish_attempt(db, request_id, ...): finish_attempt has no ledger argument but must write a ledger row holding rates. the reserve row stores the rates in force at begin_attempt; the actual or kept row copies them from its reserve row, so finish_attempt and recover_orphans need no ledger. *Cost if wrong: a rate change between send and settle is priced at the earlier rate (seconds apart).*
- **Ruling 5.** T5 ledger on local roles: verify, group and memo calls spend no Jev money. begin_attempt accepts ledger=None and then writes no ledger row; recover_orphans tolerates a call with no reserve row. *Cost if wrong: none for the cap, which is Jev-only.*
- **Ruling 6.** T7 to_record / T5 finish_attempt(result): the results table needs min_top_probability, raw_json and model, which to_record's eight label fields do not carry. to_record also returns `min_top_probability`; the classify loop adds `raw` and `model` before finish_attempt. *Cost if wrong: one key renamed.*
- **Ruling 7.** T8 labeler.label(text, request) / T9 classify.run: classify must build each request and record, which needs the prompt, the feature list, the cut-off and label_config; T9's signature does not carry them. classify.run takes `setup: jev.Setup` (prompt, features, cutoff, label_config), built by `jev.load_setup(prompts_dir, cutoff)`. *Cost if wrong: one argument.*
- **Ruling 8.** T6 feature matching / T7 jev.entities: T6 defines the matching rule (an entry matches itself and itself plus `s`), T7 says whole lowercase words. one matcher, `pipeline/features.py` (`features.load`, `features.find`), created in T6; jev.entities delegates to it and evals/feature_words.py imports it. *Cost if wrong: entities and the counts would disagree, which this prevents.*
- **Ruling 9.** T10 Reply.request_id / calls.request_id: the intent row is written before the request is sent, so calls.request_id is generated locally. the provider's id, when present, is kept inside raw_json only. *Cost if wrong: none for the checker, which needs uniqueness only.*
- **Ruling 10.** T14 claims.csv "claims the final memo cites" / T13 memo: no function returns the cited claims. memo.cited_claims(text, claims) -> list[dict]; export writes those. *Cost if wrong: claims.csv would list uncited claims, which the checker accepts either way.*
- **Ruling 11.** T17 paid evals through the ledger: calls.run and calls.session_id are NOT NULL and an eval has no pipeline run. evals log under run name `evals` with a session of stage `eval`. *Cost if wrong: none; those rows are never exported to grading/.*

## Task 2

- **Ruling 12.** Transactions are explicit. the connection is in autocommit mode and `state.tx(db)` does BEGIN IMMEDIATE / COMMIT / ROLLBACK; the pre-flight's `with db:` is `with state.tx(db):`. why: `with db:` does not open a transaction in autocommit mode, and implicit transactions hide where a save lands. *Cost if wrong: none, one helper.*
- **Ruling 13.** Check_resume takes an optional `code_commit`, stored with an allowed code change. the brief's signature had no way to record the new commit. *Cost if wrong: the run would keep its first commit after an allowed change.*
- **Ruling 14.** Added `state.heartbeat`, `state.require_clean_tree(root, *, real)`, `state.load_run`, and the errors RunExists, NoSuchRun, DirtyTree. the brief names the behaviors but not these functions. *Cost if wrong: names only.*

## Task 3

- **Note.** Full-file known-answer test run once with RUN_FULL=1; 660,622 rows, 13 empty, 484,189 distinct texts, 159,701 missing app versions, verify sample 5,000; 11.7 s. It is skipped in the normal suite.
- **Ruling 15.** A CSV with a header and no rows raises BadInput. the brief does not say; a run with nothing in it can do nothing downstream. *Cost if wrong: an empty fresh input is refused instead of producing an empty export.*
- **Ruling 16.** The supplied-file guards cover the full file only (by its SHA-256); the three nested gate files are checked by the known-answer run-order test instead. *Cost if wrong: a damaged gate file is caught later, by the checker's reference step.*

## Task 5

- **Ruling 17.** Finish_attempt and recover_orphans take an optional keyword `ledger` (revises the pre-flight row). the ledger holds its totals in memory so admission is not a table scan per request at 75 a second, and it must hear about every settlement; rates are still copied from the reserve row. *Cost if wrong: a caller that forgets to pass it leaves totals stale until `reload()`.*
- **Ruling 18.** Pipeline/billing.json counts Jev output tokens at the input rate until the usage page settles it (spec item 27). unknown billing must not read as zero, and counting too much is the safe direction for a cap. *Cost if wrong: the ledger overstates spend by about a fifth and the cap bites early; Travis resets the rate after the test batch.*
- **Ruling 19.** Added index ledger_by_request (request_id, kind) and Ledger.reserve / settle / reload, and the errors DuplicateRequest and AlreadySettled. the schema's unique index alone made each settlement a scan. *Cost if wrong: none, an index.*
- **Note.** "editing cost/rates.csv leaves spent unchanged" is covered by construction: the ledger has no path to that file. The test edits billing.json, the only rate file it reads.

## Task 6

- **Ruling 20.** Where a phrase and a word inside it both match, the phrase wins ("smart shuffle" is not also counted as "shuffle"). the brief does not say; one regex pass gives one deterministic answer. *Cost if wrong: "shuffle" is undercounted by the 1,589 reviews that say "smart shuffle".*
- **Note.** 45 of 47 candidates kept (crossfade 66 and carplay 20 left out). Counts over all 660,622 rows in evals/feature_words_out.txt. The list is a draft for Travis to read at the 100 gate.

## Task 7

- **Note.** Known answers hold; build_request reproduces all 100 requests the probe sent, byte for byte as objects; to_record gives the probe's topic, intent, severity, quote and sentiment on all 100; flag counts at cut-offs 0.6/0.7/0.8/0.9 are 17/26/38/54, the table in CLAUDE.md.
- **Ruling 21.** Jev.Setup and jev.load_setup live here (the pre-flight row put them at Task 9), with Setup.hashes() giving the run's content hashes: prompt file, feature list, splitter source, cut-off. *Cost if wrong: names only.*
- **Ruling 22.** Prompts/enrich-v1.json was generated from the probe's own dictionaries, so the wording is the measured wording; the slogan change is a later enrich-v2 after the paid wording trial. *Cost if wrong: none until the trial.*
- **Ruling 23.** "255 options" is checked on the evidence question (the only one that grows with the text), and the 32,000-token limit on the request body's bytes divided by 2.4. *Cost if wrong: an over-long review is quarantined rather than sent.*

## Task 8

- **Ruling 24.** The limiter paces by slots (no saved-up burst after idle time), and recovery after a 429 is +1 request a second per second, capped at the ceiling, floor of 1 a second. the spec says "climbs back slowly" with no number. *Cost if wrong: a slower or faster recovery; `recover_per_second` is one argument.*
- **Ruling 25.** ReplayJev's script is a list of steps per text ("temporary", "fatal", "wrong_model", "invalid"), consumed in order, then normal answers; an unknown step raises. *Cost if wrong: test-only.*

## Task 9

- **Ruling 26.** Classify.run takes three keywords the brief does not list: `setup` (pre-flight row), `backoff` (seconds before tries 2 to 4; tests pass zeros) and `accept_guards`. *Cost if wrong: names only.*
- **Ruling 27.** A review that fails a whole round of four tries is given one more round after everything else is done; if it fails again the session ends as `stuck` and the review stays pending with its attempt count raised. the spec says "tried again later in the run or in the next session" and item 7 says such reviews are listed, never quarantined automatically. *Cost if wrong: up to four extra failed calls per stuck review per session.*
- **Ruling 28.** `no_success_60s` fires when a temporary failure is processed and no request has succeeded for 60 seconds on the run's clock (counted from the session's start if none has). *Cost if wrong: after a long pause the first failure ends the session and the same command resumes, which is the behavior Review Focus 4 asks for.*
- **Ruling 29.** An exception from a client that is neither Temporary nor Fatal halts the run as `fatal` with its text saved. a bug must not spin the loop. *Cost if wrong: a harmless error stops a run that could have continued; resume is one command.*
- **Ruling 30.** Outcome also carries `new_completions` (originals completed this session), `session_id` and `stuck`; `completed` counts reviews, copies included. *Cost if wrong: names only.*
- **Ruling 31.** The degenerate-label guards run when classify finishes, on 500 or more labeled texts, and raise GuardFailed(names, supplied) after the session is closed and everything is saved; "supplied" means the input's hash is one of the five in manifest.json (the golden file is listed there too). *Cost if wrong: none; a fresh input can accept a guard by name.*
- **Ruling 32.** State.connect takes `synchronous` (default FULL, the safest); tests use OFF. a killed process loses nothing either way. *Cost if wrong: none in production, which keeps FULL.*
- **Note.** With the token limit at 100,000 a second and bodies near 2.4 KB (about 1,000 estimated tokens), the token limit alone allows about 97 requests a second, so the 75-a-second request limit is the one that binds, as the spec intends.
- **Note.** The stand-in's `log_path` option was added in the same step as its test, so that one test was not watched failing; the crash test that depends on it was.

## Task 10

- **Ruling 33.** Any 4xx other than 429 is Fatal (400, 404 and the rest, not only 401/402/403). a request the server refuses as sent will be refused again, so retrying wastes attempts and halting puts it in front of Travis. *Cost if wrong: one review-specific 4xx stops the run; resume is one command.*
- **Ruling 34.** A 200 whose body is not a JSON object raises Temporary, and token counts that are not whole non-negative numbers are saved as unknown. *Cost if wrong: up to four tries on a garbled response.*
- **Note.** The client opens a new connection per request (urllib), as the probe did at 78 requests a second for six seconds. Whether that holds for hours is unmeasured until the 10,000 gate. No real Jev call was made.

## Task 11

- **Ruling 35.** The model is `google/gemma-4-26b-a4b-qat`, the ID the probe used with LM Studio. the brief wrote `model=...`. *Cost if wrong: check() fails with the list of models the server does have, before any work.*
- **Ruling 36.** Template-token leaks are matched by a fixed list (start/end of turn, bos, eos, pad, unusedN, and `<|...|>` forms), not by any angle bracket, so "<3 this app" in a quote is not a leak. *Cost if wrong: an unlisted token gets through to a name or memo; Travis reads both.*
- **Ruling 37.** Any HTTP error, timeout, refused connection or unreadable body from the model server is ServerProblem (halts the stage); only a 200 with a bad answer is InvalidOutput. *Cost if wrong: a single bad request halts verify instead of being counted as a failure; resume is one command.*
- **Ruling 38.** StandinGemma answers inside the schema; topic, intent and severity follow the stand-in Jev's keyword rule read from the user message; `respond` overrides the answer for roles that need more. *Cost if wrong: test-only.*

## Task 12

- **Ruling 39.** Verify.run also takes `clock`, `stop_event`, `accept_guards` and `prompt_path`, returns `not_ready` while any review is pending, and returns `server_problem` (it does not raise) when the server check or a request fails. the CLI reports it and stops; nothing is recorded as a failed review. *Cost if wrong: names only.*
- **Ruling 40.** State.recover_orphans takes `roles`; classify closes only orphaned enrich calls (with the ledger) and verify only orphaned verify calls. each stage settles its own. *Cost if wrong: an orphan of another stage stays `pending` until that stage runs.*
- **Ruling 41.** Every sampled nonempty review is sent to the verifier, including one Jev could not label; the report counts those as `jev_unlabeled` and computes agreement on the pairs both labeled, with the pairs' share of the sample beside it. the sample is fixed before any model call and must not depend on Jev. *Cost if wrong: a few local requests on reviews that have no Jev label to compare with.*
- **Ruling 42.** The verify system prompt is the outside raters' wrapper around the contract's label section (2,522 characters, SHA-256 21b37d5f43750bc9…, the same section the raters got), asking for topic, intent and severity only. *Cost if wrong: prompt wording; it is one versioned file.*
- **Ruling 43.** Guard acceptance moved to classify.settle_guards and is shared by both stages; verify's guard is `verifier_agreement_100` on 50 or more pairs. *Cost if wrong: none.*
- **Note.** Verify is sequential (one request at a time), as the spec says until more at once is measured.

## Task 13

- **Ruling 44.** Rank.rank raises BadMembership for a member with no record or one that is not a completed complaint or cancellation; `rank.mean_string` is the checker's own arithmetic. *Cost if wrong: none; the checker's ranking is the test's known answer.*
- **Ruling 45.** Group.name_issues returns an Outcome (finished, no_complaints, server_problem, no_success) and always opens a `group` session when there are issues, so even a cached pass has a measured time. the brief said `-> None`. *Cost if wrong: names only.*
- **Ruling 46.** Names and memos are cached in `artifacts` by a hash of role, config string and input; the memo saved for a run is also kept under the key `final-memo:<run>`, read by `memo.final`. the schema has no memo table. *Cost if wrong: none; export reads it through that one function.*
- **Ruling 47.** Claim IDs are `CL-001`, `CL-002`, … in rank order and metric order, and the memo cites them as `[CL-001]` and reviews as `[review:ID]`. markers the check can find without guessing. *Cost if wrong: prompt wording only.*
- **Ruling 48.** The memo check ignores numbers and words inside double-quoted customer text; ranks ("rank 2") and list numbering are not treated as claims; any other number must equal a claim cited in the same sentence or a run fact, compared as decimals. *Cost if wrong: a number hidden in a quote is not checked; Travis reads the memo.*
- **Ruling 49.** The "causal claims" part of the memo check is keywords only (revenue, churn, ARPU, LTV, money amounts). Causal language in general is left to the human read, as the spec says the check cannot prove an argument is sound. *Cost if wrong: a causal sentence without those words passes the code check.*
- **Ruling 50.** The evidence pack takes originals only, three most severe then two picked by the sample seed (item 26), each quote at most 500 characters; memo.write raises MemoFailed, NothingToWrite or the server problem. *Cost if wrong: names only.*

## Task 14

- **Note.** A synthetic run through the real stages with the stand-ins, stopped once and resumed, exports and the supplied checker returns status `pass`, no flags, labelable completion 1.0, accounted 1.0, coverage point 1.0. Nine mutation tests each break one thing and the checker names it.
- **Ruling 51.** The brief's `gzip_large=True` is `gzip_over=BYTES` (default 50 MB): a JSONL file is gzipped only when it is larger, with a fixed timestamp so the bytes are reproducible. small gate exports stay readable. *Cost if wrong: one argument.*
- **Ruling 52.** Export also takes `size_limit` (default 95 MB, under GitHub's 100), `work_dir` (where the checker's two files go; default the grading folder's parent), `cap_usd` (for the summary) and `log`; it prints nothing unless given `log`, and the CLI passes print. *Cost if wrong: names only.*
- **Ruling 53.** Export refuses when any call is still `pending` as well as when a review is. an unsettled call would export with an outcome the checker rejects. *Cost if wrong: a crashed run must be resumed once before export, which closes it.*
- **Ruling 54.** The saved memo is checked again at export against the numbers being exported; problems are returned as `memo_problems` and reported, and the export is still written. spec section 9: this happens before memo numbers are treated as final. *Cost if wrong: a stale memo is reported, not blocked.*
- **Ruling 55.** The boundary is the first classify session that completed an original when a later session completed another. the same rule as the spec's, stated on saved completions. *Cost if wrong: none; the checker's own resume checks are the test.*

## Task 15

- **Ruling 56.** `--new` on a run name that exists is refused; resuming is the same command without `--new`. the spec's own example shows `--new` on the first command only. *Cost if wrong: one flag.*
- **Ruling 57.** A state file holds real runs or stand-in runs, never both. a stand-in's made-up charges must not sit in the ledger that guards the $25 cap. *Cost if wrong: a second `--state` path for dry runs.*
- **Ruling 58.** A real run without `--go` creates nothing and prints the request count, a cost estimate from the measured $0.0039 per 100, and the spend so far; with `--go` it needs a clean tree and a key. The probe spend ($0.0485 measured, $0.005 estimated) is written to the ledger on the first real run. *Cost if wrong: none before a go.*
- **Ruling 59.** A warm pass copies results, statuses and verifier predictions from the source run, opens a session for each of the four stages so each has a measured time, and saves the record `warm:<run>` with the number of calls made; any call at all makes it exit as not finished. *Cost if wrong: none; the checks are the count of calls and equal statuses.*
- **Ruling 60.** Exit codes: 0 done, 1 exported but the checker did not pass, 2 refused, 3 a stage did not finish (stopped, interrupted, stuck, server problem), 4 a guard. *Cost if wrong: names only.*
- **Ruling 61.** Hidden options `--standin-latency` and `--standin-log` exist for the interrupt test; `--prompts` picks the prompts folder. *Cost if wrong: test-only.*
- **Ruling 62.** The clean-clone test copies tracked and unignored files to a fresh folder with no .env and no key in the environment, runs four test modules there and rebuilds a ranking; running the whole suite inside itself would recurse. *Cost if wrong: a module that only fails in a clean copy and is not among the four would be missed.*
- **Note.** Two stand-ins that label by the same rule agree on every pair, so a stand-in run with 50 or more sampled reviews trips `verifier_agreement_100`; it is accepted by name with --accept-guard. A test pins this.
- **Note.** Dry run of cost_100.csv through every stage with the stand-ins (which replay Jev's real saved answers): checker `pass`; 52 members; ranking usability 38, other 29, playback 22, billing 20; the figures recorded in CLAUDE.md on 2026-10-04 from a separate script. Pinned as a test. Ledger shows $0.0048 per 100 because output tokens are counted at the input rate; input alone is the measured $0.0039.

## Task 16

- **Ruling 63.** Replay also reads `pilot_records.jsonl`, `assumptions.csv` and `text_volume.json`, all committed files. the brief listed four; completed and failed counts, unique texts and cache hits come from the records, the editable projection controls from assumptions.csv, and the full file's text volume from text_volume.json (counted by code over the 97 MB file: 660,622 rows, 484,189 distinct texts). *Cost if wrong: none; replay still opens no state file and imports no client, and a test pins that.*
- **Ruling 64.** Calc.measured and calc.project take keyword arguments beyond the brief's (local, records; conservative_retry_rate, text_copies, max_rps, cap, rates, local). *Cost if wrong: names only.*
- **Ruling 65.** Projected input tokens per request = (pilot request bytes + (average full-file text bytes − average pilot text bytes) × text_copies) × pilot tokens per byte, with text_copies 2 as a stated assumption. the spec asks to scale by text volume because pilot reviews are not the average text. *Cost if wrong: the base estimate moves by a few percent; it is refreshed after the 500 and 10,000 gates.*
- **Ruling 66.** The conservative case adds 5% retries and bills output tokens at the input rate while the output rate is unknown. *Cost if wrong: it overstates.*
- **Ruling 67.** `python3 -m cost pilot` has a hidden `--standin` for tests and dry runs; no stand-in evidence is ever written into cost/, which holds no pilot files until the paid pilot is run with Travis's go. *Cost if wrong: none.*
- **Note.** Known answers hold. The stand-in pilot replays Jev's 100 saved answers with their real token counts and the calculator gives $0.0039 of API spend, the figure measured on 2026-10-04. The base projection is $19.11 (spec: about $19); without reuse $25.57, over the cap; conservative $24.65, just under it.

## Task 17

- **Ruling 68.** Added evals/common.py (the label sheets, the two halves, and `Paid`, which sends every eval call through begin_attempt and the ledger under run name `evals`). the brief lists five scripts and says all paid calls use the ledger; one shared module does that once. *Cost if wrong: none.*
- **Ruling 69.** The candidate wording is prompts/enrich-v2.json (version prompt-v2): only the intent question differs from v1. cancellation must be about the writer's own account, and a bare boycott or cancel slogan is `unclear`. Drafted under spec item 6; unmeasured until the paid trial. `python3 -m pipeline run --prompt-file NAME` picks the wording at --new and a resume keeps it. *Cost if wrong: wording only; the trial's pass marks decide.*
- **Ruling 70.** A stand-in run of an eval script prints its result, uses a state file in a temp folder and saves nothing into evals/; only --go writes result files. a stand-in's keyword-rule answers must never sit beside real evidence. *Cost if wrong: none.*
- **Ruling 71.** The two halves are the 121 development rows sorted by SHA-256 of `halves-v1:<id>`, first 61 to wording and 60 to cut-off. spec item 24 says "split by hash" without a rule. *Cost if wrong: a different split of the same rows.*
- **Ruling 72.** Score_golden counts a review with no completed prediction as wrong on every field and lists it as "no prediction"; needs_review is scored on the rows that have a prediction; disagreements carry the review ID and the field names only. *Cost if wrong: none; it follows the contract's "missing predictions remain in the denominator".*
- **Ruling 73.** RunLock.acquire now creates the state file's folder; on a fresh clone with no runs/ folder the first command failed before it could say anything. test added. *Cost if wrong: none.*
- **Note.** Known answers hold. cutoff_table reproduces the 2026-10-04 table (flagged 17, 26, 38, 54 of 100; mistakes caught 2, 4, 4, 5 of 5; right answers flagged 1, 4, 8, 11 of 24) and shows 13 differences from the raters' shared label on 92 rows, which is Jev's 79 of 92 in validation log entry 15.

## Task 18

- **Ruling 74.** The README is an interim one that says no real run has been made and reports no result from one; each of the brief's evidence items is answered with what exists today or "Not run yet". The rubric-mapped final version is written after the full run. the brief makes the README the grading surface, and a results section filled before a run would be invented. *Cost if wrong: none; a test asserts the README does not claim a run while no pilot or export file exists.*
- **Ruling 75.** The README's links, its stated test count and the absence of secret-shaped strings and home paths are tests (tests/test_readme.py). "every evidence link resolves in a clean clone" had no check. *Cost if wrong: none.*
- **Note.** Correction to an earlier count. test_export has eight deliberate breaks plus one untouched control, not nine breaks; the Task 14 commit message and ledger line say nine. The README says eight.
- **Note.** A key-shaped fake string in tests/test_jev_client.py tripped the README skill's secret scan; replaced with a string that does not look like a key. It was never a credential. It remains in one commit of this unpushed branch until that commit is rewritten.
- **Note.** The dataset's download link is not known to the executor and is not in the README; Travis adds it before submission. No license is chosen.

## Final review

One reviewer with none of the build's context read the whole branch, read-only: no critical finding, 7 important, 12 minor. Verdict: ready with fixes. Every finding was first reproduced by a test that failed, then fixed, in one pass. The suite stands at 462 tests, 1 skipped.

- **Note.** Branch history was rewritten once (21 commits, tree unchanged) to take a key-shaped fake test string out of every commit; commit SHAs in the task lines above are the old ones. Secret scan now: tree 0, history 0.

### Re-grade, before the fix pass

- Findings 1 to 7 stand as Important and enter the fix pass.
- Minor 8 (a rejected verify request stalls verify for good) is re-graded Important: it would block the memo and the export.
- Minor 11 (stand-in runs default to the real state file; evals apply no kind check) is re-graded Important: the cap is the money guard and it could split across two files.
- Minor 12 (key text could survive truncation or the catch-all path into committed run_log.jsonl) is re-graded Important: a key in a public repo.
- Minor 13 (a malformed golden cell would be printed in a traceback) is re-graded Important: the project's hard rule is that no golden label is ever printed.
- Minor 14 (a cut-off with three decimals gives two cut-offs under one label_config) is re-graded Important: it breaks the one-setup-per-label_config rule the checker relies on.
- Minor 16 (run_log.jsonl for the full run is too big for GitHub and is not gzipped) is re-graded Important: it would block the submission push.
- Minors 9, 10, 15, 18, 19 and the malformed-CSV traceback are small and sit in code the fix pass already touches; they are fixed with tests in the same pass.
- Minor 17 stays Minor and is deferred.

### Fixed

- Finding 1 (names and memos cached across runs): test_a_second_run_on_the_same_file_makes_its_own_group_and_memo_calls RED→GREEN; artifacts are keyed by run, and a warm pass reads its source run's.
- Finding 3 (an outage books a failed call per review): test_a_run_of_failures_with_no_success_stops_admitting_new_reviews and test_a_request_that_never_left_the_machine_costs_nothing RED→GREEN; after 8 failures in a row (or twice the workers) nothing new is admitted and the session ends `outage`; a request that never connected releases its reservation; `python3 -m pipeline adjust` corrects the ledger.
- Finding 4 (a request refused for one review halts the run for good): test_a_review_whose_request_is_refused_is_set_aside_and_the_rest_complete RED→GREEN; a 4xx other than 401, 402, 403 and 429 is `jev.Rejected` and counts against the review.
- Finding 12 (key text could reach the run log): test_a_key_that_straddles_the_cut_of_a_long_error_is_still_removed and test_an_unexpected_error_inside_the_client_comes_out_fatal_and_without_the_key RED→GREEN.
- Finding 14 (cut-off precision): test_a_cut_off_with_more_than_two_decimals_is_refused RED→GREEN.
- Finding 15 (workers unbounded): test_more_than_sixteen_workers_is_refused RED→GREEN.
- Finding 18 (--allow-code needs a hash nothing printed): test_a_refusal_over_changed_code_says_how_to_allow_it RED→GREEN.
- Finding 5 (the verify, group and memo prompts shaped nothing that was saved): test_an_edited_memo_prompt_gets_a_new_memo_not_the_saved_one, test_an_edited_naming_prompt_gets_new_names and test_the_verify_prompt_cannot_change_partway_through_a_sample RED→GREEN; each stage's config string now carries the first 12 hex characters of its prompt's SHA-256.
- Finding 5, related (no command checked a hand-edited memo): test_a_good_edit_passes_the_check_and_becomes_the_runs_memo and test_an_edit_that_breaks_a_number_is_refused_and_nothing_is_saved RED→GREEN; `python3 -m pipeline memo --run NAME --file PATH [--save]`.
- Finding 6 (two gate pass marks had no code): test_a_review_whose_label_changed_between_runs_stops_the_gate_and_is_listed and test_the_verify_reports_four_counts_are_printed_and_saved RED→GREEN; `python3 -m pipeline nested --run NEW --against OLD`, a verify report line after the stage, and verify_report.json in the run evidence.
- Finding 8 (a request the model server refuses stalls verify): test_a_request_the_model_server_refuses_is_one_invalid_answer_not_a_dead_stage RED→GREEN; HTTP 400, 413 and 422 on one request are InvalidOutput.
- Finding 9 (an open eval call stays reserved): test_an_eval_call_left_open_by_a_kill_gives_its_reservation_back_to_spend RED→GREEN.
- Finding 10 (a memo call left open blocks export): test_a_memo_call_left_open_by_a_kill_is_closed_even_when_the_memo_is_already_saved RED→GREEN.
- Finding 11 (stand-in runs defaulted to the real state file; evals had no kind check): test_a_stand_in_run_has_its_own_default_state_file and test_a_real_eval_refuses_a_state_file_that_holds_stand_in_runs RED→GREEN.
- Finding 13 (a malformed golden cell would be printed): test_a_golden_cell_that_is_not_a_number_is_reported_without_its_value RED→GREEN.
- Finding 16 (run evidence too large for the repo): test_large_run_evidence_is_gzipped_and_named_when_it_is_too_big_for_the_repo RED→GREEN.
- Finding 19 (a warm pass that could not finish reported a clean pass): test_a_warm_pass_that_could_not_finish_does_not_report_a_clean_pass RED→GREEN.
- (reviewer's Review Focus 1) an unreadable CSV raised a traceback: test_a_csv_that_cannot_be_read_stops_with_a_plain_message RED→GREEN.
- Finding 2 (the paid pilot could not be run again and took any unfinished ending for its planned stop): test_the_pilot_command_finishes_a_pilot_that_was_cut_off_after_its_first_step, test_the_pilot_command_can_be_run_again_after_it_finished and test_a_cold_run_that_was_never_stopped_cannot_be_the_pilot RED→GREEN; the pilot reads the state file before each step, and `python3 -m cost evidence` writes the pilot files from finished runs.
- Finding 7 (changing only the projected row count gave a report that contradicts itself): test_changing_only_the_row_count_scales_the_counts_that_depend_on_it and test_counts_that_cannot_be_true_together_are_refused RED→GREEN; nonempty and distinct are scaled at the full file's shares and the report says so.
- (found while fixing 6) a run compared with itself passed the nested check: test_a_run_compared_with_itself_is_refused RED→GREEN.
- (found while fixing 3) a ledger correction that is not an amount raised a traceback: test_an_adjustment_that_is_not_an_amount_is_refused_and_nothing_is_written RED→GREEN, suite 461/461 (1 skipped).
- (found while writing the docs) the stand-in state file was not ignored by git: test_neither_default_state_file_can_be_committed RED→GREEN, suite 462/462 (1 skipped).

### Left open

- **Minor, deferred.** Finding 17, Ctrl-C. During naming or the memo call the run prints "stopping" and the call in flight still finishes (at most 8 short calls and one memo call, minutes at worst). Under `cost pilot` Ctrl-C kills the child a quarter second after the signal instead of letting it close its session; the next pilot command recovers the open call and picks up.

### Rulings made on the review

- **Ruling 76.** The Task 10 ruling "every 4xx other than 429 is Fatal" is overturned as the reviewer asked; tests/test_jev_client.py's status table was changed to match (400 and 404 are now Rejected). Its stated cost, "resume is one command", was wrong: resume replays the same review first. *Cost if wrong: a 4xx that really is about the whole request shape costs up to 8 failed calls before the session ends `outage`.*
- **Ruling 77.** The Task 9 ruling is amended, not replaced: `no_success_60s` stays, and the breaker is added in front of it. A new ended_how, `outage`, exists. *Cost if wrong: a burst of 8 unrelated failures in a row with one worker ends a session that could have continued; resume is one command and nothing is lost.*
- **Ruling 78.** *(The reviewer's Review Focus 4)* On macOS the monotonic clock does not advance during sleep, so a real sleep does not trip the 60-second stop; requests in flight fail on wake and are retried. The test proves the stop with an injected clock only. The behavior on a real sleep is safe either way. *Cost if wrong: none.*
- **Ruling 79.** Spec section 4 says a resume refuses when any prompt's hash differs. That is kept for what shapes a label (the enrich prompt, feature list, splitter, cut-off). For the three downstream prompts the rule is by stage: an edited naming or memo prompt gets a new call and the old artifact is kept; an edited verify prompt is refused once verify has started on the run, because one sample under two prompts is two measurements. Refusing the whole resume would force a second paid classify pass just to reword a memo. *Cost if wrong: a naming or memo prompt can change between sessions of one run without a new run name; every call row names the prompt content it used.*
- **Ruling 80.** The Task 11 ruling "every HTTP error from the model server is ServerProblem" is overturned in part, as the reviewer asked: 400, 413 and 422 on one request are one invalid answer; tests/test_gemma.py's status list was changed to match. *Cost if wrong: a 400 that is really a broken setup is recorded as verify failures for every sampled review instead of halting; the verify report's failure count shows it at once.*
- **Ruling 81.** The Task 15 ruling "one kind per state file" is amended: `--standin` now defaults to runs/standin.sqlite and a real eval refuses a state file that holds stand-in runs. *Cost if wrong: `status`, `export` and `nested` on a stand-in run need `--state runs/standin.sqlite`.*
- **Ruling 82.** The Task 13 ruling "the cache key leaves the run out" is overturned (finding 1); it contradicted spec section 4, each run starts cold. *Cost if wrong: a rerun of the same file makes up to 8 naming calls and 1 memo call again, all local.*
- **Ruling 83.** The Task 15 ruling "one exit code, 3, for every unfinished ending" is kept and its user changed: the pilot no longer reads the exit code, it reads how the session ended from the state file. Changing the exit codes would break the README and every test that names them. *Cost if wrong: any other script that drives the commands by exit code alone still cannot tell a planned stop from an outage; `status` shows which.*
- **Ruling 84.** The Task 5 ruling "finish_attempt takes the ledger as an optional keyword" is kept, with its stated cost corrected as the reviewer said: a paid call finished without the ledger leaves its reservation held for the life of the state file, and reload() does not release it. Every caller passes it. *Cost if wrong: the cap is reached early by the size of the held reservations; it can never be passed late, so the error is on the safe side.*
- **Ruling 85.** The Task 5 ruling "Jev output tokens are counted at the input rate until the usage page settles it" is kept, and the `adjust` command the reviewer said it needs now exists. *Cost if wrong: the ledger reads high until Travis compares it with the usage page and corrects it.*
- **Ruling 86.** *(The reviewer set aside: `.env` contents and whether the key reader parses them)* Off limits by project rule and left unread. If the key cannot be read, the first real command refuses by naming the missing variable before anything is sent. *Cost if wrong: one refused start, no spend.*
- **Ruling 87.** *(The reviewer set aside: golden label column contents)* Off limits by project rule. The golden file is read once, by evals/score_golden.py, which prints counts and review IDs and now names a malformed cell by row without showing it. *Cost if wrong: none.*
- **Ruling 88.** *(The reviewer set aside: how LM Studio behaves: the model name it echoes, whether /models lists only loaded models, integer choices under a strict schema, context length)* Unknown until the first real local call, which is the 100 gate. A wrong name or an unusable answer is recorded as an invalid answer and a server problem halts with nothing lost. *Cost if wrong: the 100 gate's verify step stops or reports a high failure count and the client needs a fix before the gate can be judged. No money.*
- **Ruling 89.** *(The reviewer set aside: whether Gemma writes a memo that passes the check within 1,500 tokens and 120 seconds)* Unknown until the pilot. Two memos that fail the check stop the run with the list of problems, and Travis reads the pilot memo by his own earlier ruling. *Cost if wrong: the pilot cannot finish until the memo prompt or its limits change; that is new memo work only, not a new classify pass.*
- **Ruling 90.** *(The reviewer set aside: whether TypeSafe returns a 4xx for one review, sustains 75 requests a second with a new connection per request, or bills output tokens)* Unknown until the gates. Each direction has a brake: a refused review is set aside, 8 failures in a row end the session, 429 slows the limiter, and the ledger counts output tokens until the usage page says otherwise. *Cost if wrong: the full pass is slower than the 1.8-hour estimate, or the ledger reads high.*
- **Ruling 91.** *(The reviewer set aside: how fast the state file commits with a disk sync on every save)* Measured after the review. A stand-in pass over the 10,000-review file with 16 workers and the default full sync saved 8,448 requests in 5.66 seconds, about 1,490 a second, against a limit of 75. On macOS the sync asks the drive to write but does not force its cache to flush, so "survives a power cut" is weaker here than on Linux. *Cost if wrong: after a power cut the last few saved answers could be missing and would be sent again, a fraction of a cent.*
- **Ruling 92.** *(The reviewer set aside: prompt wording, the feature list, the cut-off, the gate pass marks, the sampling design)* These are Travis's, drafted or proposed under his delegation and confirmed by him at each gate. *Cost if wrong: none from the build.*
- **Ruling 93.** *(The reviewer set aside: the interim README and the tests' internals)* The README is interim by Ruling 74 and is rewritten against the rubric after the full run. The tests were not reviewed as evidence, so the suite passing is the author's check only. *Cost if wrong: a test that asserts the wrong thing hides a defect until a gate; each gate is judged on the supplied checker and known answers, not on the suite.*
- **Ruling 94.** *(The reviewer set aside: whether the instructor's final check uses the full file as its analysis file)* Unknown and not among the questions already drafted for the instructor. Both the 10,000 gate and the full run are exported, so either can be submitted. *Cost if wrong: the wrong export is in `grading/` at submission; worth adding to the instructor questions.*

## After the review

- **Not a ruling of the executor's.** Travis raised the cap on total Jev spend from $25 to $35 on 2026-10-05 (spec item 34). Where a line above says $25, read $35. The number is now held once in the ledger's code, and a test holds the calculator's copy equal to it. The suite stands at 465 tests, 1 skipped.
