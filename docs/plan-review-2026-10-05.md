# Outside review of the implementation plan, 2026-10-05

Travis pasted this review into the session on 2026-10-05. It reviews `docs/superpowers/plans/2026-10-05-spotify-insight-pipeline.md` as it stood at commit `cd0c04e`. The report does not name the reviewer. It says it was made with the validation-epistemics skill, changed no repository file, made no provider call and opened no protected label. No session log came with it, so those statements were not checked.

Part 1 is the report as pasted, with links that held paths on this machine reduced to line numbers. Part 2 is what was done with each point.

## Part 1. The report

Seven issues still need correction before execution.

1. **[P1] The wording gate rewards incorrect labels.** Line 431 requires at least three of four slogan cases to be unclear. I checked the imported fixtures: only two expect unclear; one expects cancellation and one complaint. A correct classifier fails this gate. Require correctness against each case's accepted answer instead.
2. **[P1] Recovery can reopen completed classifications after a verifier crash.** Task 5 (line 241) says every pending call returns its review to pending, but the calls table contains all roles. Killing verification could therefore make an already classified review eligible for enrichment again. Only orphaned enrichment calls should reset classification status; recover other stages separately. Add a crash-during-verification test.
3. **[P1] Temporary failures can erase duplicate provenance.** Line 242 applies "copies … carry no cache pointer" to both quarantine and return-to-pending. Clearing pointers on pending copies loses their relationship to the original, risking duplicate requests or unlogged completed records. Preserve that relationship during retries; omit cache pointers only from quarantined exports. Test retry exhaustion followed by successful resume with duplicates.
4. **[P1] HEAD-dirty does not identify the code being resumed.** Line 194 gives different uncommitted implementations the same fingerprint. I reproduced this in a temporary repository: changing the implementation twice produced identical documented fingerprints. Require a clean tree or hash the actual executable source contents.
5. **[P1] Editing calculator rates can change historical budget consumption.** Line 244 recomputes ledger dollars from editable rates at read time. Lowering a rate can make previously incurred spending appear smaller and reopen admission under the $25 cap. Preserve historical charges or immutable billing-rate snapshots. Keep editable replay/projection rates separate from operational spending.
6. **[P1] Offline replay lacks a defined source for its measured clocks.** Task 16 (line 396) requires session measurements, but replay's listed inputs contain no defined session-time representation. No task explicitly owns writing the complete cold/warm pilot evidence. A zero-call warm run cannot derive its duration from call records. Assign an evidence writer and specify persisted stage and end-to-end clocks, including warm-run timing. Test replay in a clean clone without the state file.
7. **[P1] The 500 and 10,000 gates omit the interruption needed for their checker passes.** Lines 433 to 434 require checker pass, but specify no stop/resume. An uninterrupted fresh run has no valid boundary and receives resume_snapshot_mismatch and resume_call_evidence. Add explicit stop, resume and export steps to both gates, with an original completing after interruption.

There are also several smaller corrections:

- **Align fixtures with the request schema.** Task 7 (line 265) renames the evidence question to quote. Of the saved responses, 25 contain evidence and none contain quote. Keep the original name or define a versioned fixture adapter. Also accept finite fractional tone scores: 90 of the 100 saved scores are fractional, despite the score: int interface.
- **Fix the checker assertions.** Tasks 13 to 14 (line 348) compare string ranking fields directly with checker integers and refer to "coverage 1.0." Normalize ranking fields and explicitly assert labelable_completion_fraction, accounted_fraction and empty issue_counts. Required empty quarantines prevent the overall valid-completion fraction from reaching 1.0.
- **Complete the gate criteria.** Add a one-time boycott holdout score and explicit inspection of planted/injection outcomes and verifier failure coverage. Restrict "every response names Jev" at the 100 gate to enrichment responses.
- **Complete lifecycle and call bounds.** Specify recovery from partial preparation and unfinished sessions, exactly-once ledger settlement, and context/output limits for every Gemma role. Ensure paid wording trials use the same spending ledger.
- **Scope distribution guards.** A homogeneous arbitrary CSV or genuine perfect agreement can legitimately trigger the current hard guards. Use inspection flags for arbitrary inputs and validated blocking bands for the supplied corpus.

Reviewed with validation-epistemics. No repository files changed, provider calls made, or protected labels opened.

## Part 2. What was done with each point

Each claim was checked before anything changed. Claims about the plan's wording were read against the cited lines. Two claims about data were rerun with separate code: `experiments/2026-10-05/plan-review/check_claims.py`.

| Point | Checked how | Holds? | What changed in the plan |
|---|---|---|---|
| 1. Wording gate | The four planted slogan cases read from `three_tests.py`: S1 and S2 expect `unclear`, S3 `cancellation`, S4 `complaint` | Yes | The mark is now each case against its own accepted answer, and no case the probe got right may become wrong |
| 2. Recovery reopens reviews | Line 241 as written, against the `calls` table, which holds every role | Yes | `recover_orphans` never changes a review's status. Each stage finds its own unfinished work. A crash-during-verify test is added to Task 12 |
| 3. Copy pointer cleared | Line 242 as written: the bracket covered both functions | Yes | `cache_source_id` is set at prepare and never cleared in the state file. Export leaves it off a quarantined record. A retry-then-resume test with copies is added to Task 9 |
| 4. Commit plus "dirty" | True by construction; the reviewer's reproduction was not rerun | Yes | `state.code_fingerprint` hashes the bytes of every `pipeline/*.py`; resume compares that hash. A real run needs a clean tree. Stand-in runs may be dirty |
| 5. Rates move past spend | Line 244 as written | Yes | Each ledger row stores the rates in force when written. Operational rates live in `pipeline/billing.json`; `cost/rates.csv` is the calculator's copy. Corrections are new `adjust` rows. A request settles exactly once |
| 6. Replay has no clock source | Task 16's replay inputs as written | Yes | `cost/evidence.py` writes the pilot evidence. `usage.csv` carries each stage's and each run's clock seconds, the warm run included. Replay is tested in a clean copy with no state file |
| 7. Gates without a stop | The checker's `resume_snapshot_mismatch` and `resume_call_evidence` rules, read in `check_submission.py` | Yes | The 500 and 10,000 gates are stopped once, resumed and exported, and an original must complete after the stop |
| Fixtures and tone | Rerun: 25 saved answers hold `evidence`, none `quote`; all 100 tone scores are floats, 90 fractional | Yes | The question keeps the name `evidence`. `sentiment_from_tone` takes a real number from 0 to 4 |
| Checker assertions | `audit()` returns ints for counts and rank; `valid_completion_fraction` is valid over all rows | Yes | Ranking fields are compared through `str()`. Tests assert `status`, empty `issue_counts`, `labelable_completion_fraction`, `accounted_fraction` and the coverage point |
| Gate criteria | The gate table as written | Yes | A one-time holdout row; planted and injection outcomes read case by case; verify failures listed at each gate; the model-name mark split by role |
| Lifecycle and call bounds | Tasks 2, 3, 5, 11 and 17 as written | Yes | Prepare is one transaction; crashed sessions are closed at their last heartbeat; each Gemma role has input and output bounds; paid evals use the same ledger |
| Guards by input | Spec section 10 as written | Yes, in part | **Taken in a different form.** Guards still raise for every input. For the supplied file and its nested gate files there is no way past one. Any other input can be restarted with `--accept-guard NAME`, which is logged. The reviewer proposed inspection flags; this project's rule is that a guard raises and never only warns |

Four of these also change the spec, and are recorded there as section 12 item 33: the code fingerprint (item 31), the ledger's stored rates (section 4), the pilot's clocks in `usage.csv` (section 8), and the guard override for other inputs (section 10).

What this review does not show: nothing is built, so no claim was tested by running pipeline code. The reviewer read the plan, not the spec's reasoning, and could not open the label files.
