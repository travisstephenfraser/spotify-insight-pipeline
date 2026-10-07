# Spotify Insight Pipeline

**A staged pipeline that turns 660,622 Spotify app reviews into a ranked list of product issues and a decision memo, with every number traceable to saved evidence.**

This is my final assignment for a Berkeley Haas course on building with AI: advise Spotify on where the next quarter of product effort should go, and make the answer inspectable. The one idea that shaped it is that models only read language and write prose; code owns everything that can be counted. Record accounting, validation, budgets, retries, ranking and every exported number are code. A model never counts, sorts or decides what runs next. That split is enforced, not promised: the supplied checker (`check_submission.py`) passes on an end-to-end test run, and eight deliberate breaks are each named by it.

**Status: built, tested, and run for real on 100, 500 and 10,000 reviews and then on the full file (2026-10-06): 660,609 reviews labeled, 13 empty ones set aside, the supplied checker `pass` with no flags, $20.36 and 2 hours 11 minutes of working time ([`runs/full/`](runs/full/run_summary.json)). The golden 50 is not scored yet and the provider's usage page has not been read against the run.** Every stage is tested end to end with stand-ins that replay saved answers. The 500-review gate (2026-10-05) and the 100-review pilot and 10,000-review gate (2026-10-06) each ran every stage with the real models, stopped once and resumed, and each export passes the supplied checker ([`runs/pilot4-cold/`](runs/pilot4-cold/run_summary.json), [`runs/gate-500/`](runs/gate-500/run_summary.json), [`runs/gate-10k/`](runs/gate-10k/run_summary.json)). Each number below says where it was measured.

The repo was built with an AI coding assistant (Claude Code); commits carry its co-author line. Design decisions, the hand labels and every go to spend money are mine. An agent reading this repo should start with [`CLAUDE.md`](CLAUDE.md).

Live URL: Not applicable. This is a command-line pipeline that runs locally; nothing is deployed.

```
Language   Python 3.14, standard library only (no dependency to install)
State      one SQLite file, write-ahead mode
Classify   Jev (TypeSafe), jev-1.13.0, one request per distinct review text
Verify     Gemma 26B, local through LM Studio, blind, on a fixed sample of 5,000
Name       Gemma 26B, local
Memo       Claude Sonnet 5.5 (Anthropic API), one call a run
Tests      523 automated (522 run with no outside network; 1 skipped unless the 97 MB file is present)
Checked    2026-10-05
```

---

## Contents

- [Walkthrough](#walkthrough)
- [Features](#features)
- [Technology stack and why](#technology-stack-and-why)
- [Architecture](#architecture)
- [State file schema](#state-file-schema)
- [Authentication and ownership](#authentication-and-ownership)
- [Secrets](#secrets)
- [Local setup](#local-setup)
- [Environment variables](#environment-variables)
- [Tests](#tests)
- [Grading evidence](#grading-evidence)
- [Running it for real](#running-it-for-real)
- [Known limitations and what I would do next](#known-limitations-and-what-i-would-do-next)
- [License](#license)
- [Contributing](#contributing)

---

## Walkthrough

There is no screen to show, so this is a terminal session. It is a **stand-in run**: the stand-in classifier replays the 100 answers Jev gave on 2026-10-04 for the pilot file, and the stand-in verifier labels by a fixed keyword rule. It proves the plumbing, not the quality of any label. Nothing was sent anywhere and the dollar figure is replayed usage, not a new charge.

```console
$ python3 -m pipeline run --run dry100 --new --input "feed/Final Assignment - Spotify Reviews Dataset/cost_100.csv" --standin --stop-after 50 --state /tmp/dry/state.sqlite
prepared 100 rows: 0 empty, 100 distinct texts, 0 copies, verify sample 100; not the supplied file, so its known-count checks were skipped
classify: stop_after; completed 50, pending 50, quarantined 0; spent $0.0024 of $35

$ python3 -m pipeline run --run dry100 --standin --state /tmp/dry/state.sqlite
classify: finished; completed 100, pending 0, quarantined 0; spent $0.0048 of $35
verify: finished; predicted 100, failed 0, left 0.
verify report: sample 100, predictions 100, verify failures 0, not labeled by Jev 0; all three fields agree on 19 of 100 pairs
group: finished; 52 members, 8 named, 0 reused, 0 fell back.
memo: written and checked
All stages finished. Next: python3 -m pipeline export --run dry100

$ python3 -m pipeline export --run dry100 --state /tmp/dry/state.sqlite --out /tmp/dry/grading
checker status: pass
coverage: 100 classified, 0 quarantined, of 100 rows
```

The first command stops on purpose after 50 reviews. The second is the same command without `--new`: it resumes, sends nothing that was already completed, and runs the remaining stages. The third writes the grading folder and runs the supplied checker on it. The "19 of 100" in the verify report compares replayed answers with a keyword rule, so it says nothing about either model.

## Features

- Reads any CSV with the six source fields; keeps every row exactly as written and hashes it the way the checker does.
- Quarantines empty text with the reason `empty_review_text`; never sends it to a model.
- Labels each distinct text once. Copies keep their own row and point at their original with `cache_source_id`.
- Saves after every response. An intent row is committed before a request is sent, so a kill at any moment loses nothing that was saved.
- Resumes with the same command. A resume is refused if the input, seed, prompts, feature list, sentence splitter, cut-off or code changed.
- Stops on a time box, a count, Ctrl-C, the spending cap, a fatal response, or sixty seconds without a success.
- Holds one spend ledger for every run against one cap, and reserves the worst-case cost before each request.
- Verifies a fixed sample blind: the verifier's request is byte-identical whether or not the first answer exists.
- Groups by code, ranks by code, and rebuilds `ranking.csv` from committed files with no model and no state file.
- Checks the memo by code: every issue ID, review ID, claim ID and number.
- Exports the grading folder and the run evidence, then runs the supplied checker and reports what it says.
- Replays the cost calculator offline with no key.

## Technology stack and why

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.14, standard library only | Setup is clone and run. No dependency can drift, and a grader needs nothing installed. `urllib` and `sqlite3` are enough at this scale |
| State | One SQLite file in write-ahead mode | Every save is one transaction, so two workers cannot double-count and a crash cannot leave half a result. A folder of JSON files would need its own locking |
| Classifier | Jev `jev-1.13.0`, direct TypeSafe API | Measured on 2026-10-04 against 29 hand labels: Jev 24 right on all three fields, local Gemma 23, too close to call, and Jev was far faster and cost $0.0039 per 100 reviews. The tie went to the faster engine. Jev through a gateway was ruled out: its rate cap meant about 40 hours a pass |
| Verifier | Gemma 26B, local, one review per request | A second opinion from another maker, at no API cost. Ten reviews per request was dropped because labels shifted with their neighbors (15 of 100 changed when regrouped) |
| Names and memo | Gemma 26B, local | Small bounded writing tasks. No model has written either yet, so this choice is reviewed at the 100-review pilot |
| Fallback model | None | A hard case is flagged for review, never re-labeled by a stronger model. A fallback would put two setups under one `label_config` |
| Tests | `unittest` | In the standard library. No test runner to install |

## Architecture

```
 input CSV (any path)
      |
 1 PREPARE     code     rows, exact hashes, empty-text quarantine, copies, run order,
      |                 verify sample fixed here, before any model call
      v
 2 CLASSIFY    Jev      role "enrich": topic, intent, severity, tone, which sentence
      |        code     validation, quote, entities, needs_review, ledger, limiter
      |                 retry x4 on 429/5xx/timeout -> back to pending
      |                 invalid answer: retry once -> quarantine invalid_model_output
      |                 wrong model or 401/402/403 -> HALT, no status changed
      |                 other 4xx: that one review waits, then is listed as stuck
      |                 8 failures in a row -> nothing new is sent, session ends "outage"
      v
 3 VERIFY      Gemma    role "verify": blind re-label of the fixed sample
      |        code     comparison, agreement report, disagreement list
      |                 server problem -> HALT (never counted as a failed review)
      |                 a request the server refuses (400/413/422) is one failed review
      v
 4 GROUP       code     membership: one issue per topic
      |        Gemma    role "group": a name and one sentence per issue
      v
 5 RANK        code     count, severity sum, mean, order. No model.
      v
 6 MEMO        Gemma    role "memo": recommendation from the ranked table and a
      |                 bounded pack of quotes; never the raw file
      |        code     checks every ID and every number; one retry, then stop
      v
   EXPORT      code     grading/, run evidence, then the supplied checker

 ---- everything above the model calls is saved in one SQLite file ----
 runs  sessions  reviews  results  calls  ledger  verify  issues  membership  artifacts
```

| Role | Model | Input | Output | Why a model at all | What code does instead |
|---|---|---|---|---|---|
| `enrich` | Jev | one review's text, fixed choices | a choice and probabilities per question | Reading messy customer language | Maps the choice to a label, picks the quote, finds entities, sets the review flag, validates, saves |
| `verify` | Gemma | one review's text, the contract's definitions word for word | topic, intent, severity | An independent read | Samples, compares, reports. Disagreement changes no label |
| `group` | Gemma | a topic, its definition, up to 30 quotes | a name and a description | Summarizing what customers say | Decides membership and never lets a name change it |
| `memo` | Gemma | ranked table, claims, up to 5 quotes per issue, run facts | a markdown memo | Writing an argument | Computes every number first and rejects a memo that changes one |

### The design decision worth explaining

A request is saved in two steps. Before it is sent, an intent row and a reservation of its worst-case cost are committed. When the response arrives, its usage, its charge and, if the answer is valid, its result and the completion of the original and every copy are saved in one transaction. A crash between the two leaves an intent with no outcome; on restart it becomes a failed call with usage unknown and its reservation stays counted as spent. So a paid request can never be invisible, and a completed review is never sent again.

What this design does not claim: that the labels are right. A record can pass every check and still be wrong, because an exact quote may not support its label. Agreement between the two engines is not accuracy either. The golden 50, the instructor's private sample and a human read of the memo are the checks on quality.

## State file schema

One SQLite file, `runs/state.sqlite`, holds every run. It is not committed. The schema is created by `pipeline/state.py`.

**`runs`**

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `run` | TEXT | primary key | The run's name |
| `created_utc` | TEXT | not null | When it was created |
| `input_path`, `input_sha256` | TEXT | not null | The input file and its checksum |
| `seed`, `verify_seed`, `sample_seed` | TEXT | not null | Run order, verify sample, quote samples |
| `verify_size` | INTEGER | not null | Size of the verify sample |
| `code_commit`, `code_hash` | TEXT | not null | Git commit, and a hash of every `pipeline/*.py` |
| `label_config` | TEXT | not null | Model, prompt version, schema version, cut-off |
| `hashes_json` | TEXT | not null | Content hash of the prompt, feature list, splitter, and the cut-off |
| `configs_json` | TEXT | not null | Stage settings, accepted guards, allowed code changes |

**`sessions`**

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `session_id` | INTEGER | primary key | One stage, one process |
| `run`, `stage` | TEXT | not null | Which run and stage |
| `workers` | INTEGER | not null | Requests in flight at most |
| `started_utc` | TEXT | not null | Wall-clock start |
| `started_mono`, `last_mono`, `ended_mono` | REAL | | Monotonic clock: start, last heartbeat, end |
| `ended_how` | TEXT | | finished, stop_after, interrupted, time_box, cap, fatal, no_success_60s, outage, stuck, crashed |

**`reviews`**

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `run`, `review_id` | TEXT | primary key together | One source row in one run |
| `review_text`, `review_rating`, `review_likes`, `app_version`, `review_timestamp` | TEXT | not null | The source fields, exactly as read |
| `source_sha256` | TEXT | not null | The checker's row hash |
| `text_key` | TEXT | not null | SHA-256 of the exact text: identical bytes share one result |
| `run_order` | INTEGER | not null | Rank by SHA-256 of `seed:review_id` |
| `status` | TEXT | pending, completed or quarantined | Where the review stands |
| `reason` | TEXT | | Why it was quarantined |
| `attempts` | INTEGER | default 0 | Failed rounds so far |
| `cache_source_id` | TEXT | | On a copy, its original's ID. Never cleared |
| `completed_session` | INTEGER | | The session that completed it; fixes the checkpoint boundary |
| `in_verify_sample` | INTEGER | default 0 | Chosen at prepare |

**`results`**

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `run`, `text_key` | TEXT | primary key together | One result per distinct text |
| `topic`, `intent` | TEXT | not null | The labels |
| `severity` | INTEGER | not null | 1 to 5 |
| `sentiment` | REAL | not null | -1 to 1 |
| `entities_json`, `evidence_quote` | TEXT | not null | Feature words found; the exact quote |
| `needs_review` | INTEGER | not null | The review flag |
| `min_top_probability` | REAL | not null | What the flag is computed from |
| `raw_json`, `model` | TEXT | not null | Jev's whole answer and the model it named |

**`calls`**

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `request_id` | TEXT | primary key | One attempt |
| `run`, `role` | TEXT | not null | Which run; enrich, verify, group or memo |
| `review_ids_json` | TEXT | not null | The reviews sent |
| `model`, `label_config` | TEXT | not null | What was asked, under which setup |
| `outcome` | TEXT | pending, succeeded or failed | `pending` is the intent row, committed before sending |
| `input_tokens`, `output_tokens` | INTEGER | | Reported usage |
| `usage_known` | INTEGER | default 0 | 0 when no usage came back |
| `http_status`, `error` | | | What went wrong, with any key removed |
| `started_utc`, `seconds`, `session_id` | | | When, how long, in which session |

**`ledger`**

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | INTEGER | primary key | |
| `request_id`, `run` | TEXT | not null | What the row is for |
| `kind` | TEXT | opening, reserve, actual, kept or adjust | A reservation, a charge, a reservation kept for unknown usage, a correction |
| `input_tokens`, `output_tokens` | INTEGER | not null | Billed units |
| `usd_per_mtok_in`, `usd_per_mtok_out` | TEXT | not null | The rates in force when the row was written |
| `usd_fixed`, `note` | TEXT | | A dollar amount and its reason, on opening and adjust rows |
| `created_utc` | TEXT | not null | |

A request settles exactly once: a unique index refuses a second `actual` or `kept` row.

**`verify`**: `run`, `review_id` (primary key together), `outcome` (predicted or failed), `topic`, `intent`, `severity`, `reason`, `request_id`.

**`issues`**: `run`, `issue_id` (primary key together), `name`, `description`, `model`.

**`membership`**: `run`, `issue_id`, `review_id` (primary key together).

**`artifacts`**: `key` (primary key: the run, then a hash of the role, the setup and the input), `run`, `role`, `input_json`, `output_json`, `model`, `created_utc`. Names and memos are cached here by what went in, within one run. The setup string carries a hash of the prompt file, so an edited prompt is new work. A warm pass reads the artifacts of the run it names.

## Authentication and ownership

Not applicable: a local command-line tool with no users, no accounts and no server.

## Secrets

Keys live in a local `.env` that `.gitignore` excludes. Only the blank [`.env.example`](.env.example) is committed. A key's value is never printed or logged; an error that echoes it is saved with the key removed. The tests, the offline calculator replay, the ranking and the supplied checker need no key at all.

## Local setup

```sh
git clone https://github.com/travisstephenfraser/spotify-insight-pipeline.git
cd spotify-insight-pipeline
python3 --version          # 3.14; nothing to install

# The tests: no network, no key
python3 -m unittest discover -s tests -t .

# Every stage with the stand-in models, on the supplied 100-review file
python3 -m pipeline run --run dry100 --new --standin --stop-after 50 \
  --input "feed/Final Assignment - Spotify Reviews Dataset/cost_100.csv" --state /tmp/dry/state.sqlite
python3 -m pipeline run --run dry100 --standin --state /tmp/dry/state.sqlite
python3 -m pipeline export --run dry100 --state /tmp/dry/state.sqlite --out /tmp/dry/grading

# Rebuild the ranking from saved files: no model, no state file
python3 -m pipeline rank --grading /tmp/dry/grading

# The cost calculator, offline
python3 -m cost
```

A `--standin` run with no `--state` uses `runs/standin.sqlite`. The file that guards real spend, `runs/state.sqlite`, is only ever used by a real run, and each file holds one kind.

The repository is private until submission. The full dataset, `spotify_reviews_18months.csv` (97.4 MB, 660,622 rows), is not in the repo. It comes from the course's dataset link and goes in `feed/Final Assignment - Spotify Reviews Dataset/`. Its SHA-256 is `1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6`; prepare refuses to continue if the file with that checksum does not give its known counts.

A real run also needs LM Studio serving `google/gemma-4-26b-a4b-qat` at `localhost:1234` (`lms server start`), a TypeSafe key, and an Anthropic key for the memo. See [Running it for real](#running-it-for-real).

## Environment variables

| Name | Where | Purpose |
|---|---|---|
| `TYPESAFE_API_KEY` | local `.env` or the environment | Jev. Needed only for a real run started with `--go` |
| `ANTHROPIC_API_KEY` | local `.env` or the environment | The memo model, one call a run. Needed only for a real run started with `--go`. Also used by the outside-rater experiment in `experiments/` |
| `OPENAI_API_KEY` | local `.env` | Used only by the outside-rater experiment in `experiments/`, not by the pipeline |

See [`.env.example`](.env.example).

## Tests

```sh
python3 -m unittest discover -s tests -t .
```

523 tests: 522 pass with no outside network and no key (two client test files talk to a server on localhost), 1 is skipped unless the 97 MB file is present and `RUN_FULL=1` is set. That one reads the whole file and checks its known counts; it was run once on 2026-10-05 and passed (660,622 rows, 13 empty, 484,189 distinct texts, 159,701 missing app versions).

```console
$ python3 -m unittest discover -s tests -t .
----------------------------------------------------------------------
Ran 523 tests in 13.100s

OK (skipped=1)
```

| File | What it proves |
|---|---|
| `test_hashing.py` | The row hash equals the checker's on real and awkward rows; the run order reproduces the supplied sample files |
| `test_state.py` | Schema, explicit transactions, one process per state file, resume refusal, the code fingerprint |
| `test_prepare.py` | Rows kept exactly, empty text quarantined, copies pointed at originals, fresh-input cases, the supplied file's known counts |
| `test_labels.py` | Each record the validator accepts or refuses is put through the supplied checker, which must agree |
| `test_ledger.py`, `test_save_protocol.py` | Reservations, the cap, stored rates, one settlement per request, recovery that never reopens a review |
| `test_features.py` | The one matcher behind entities and the feature-word counts |
| `test_splitter.py`, `test_jev_mapping.py` | The request builder reproduces all 100 requests the probe sent; the mapping gives the probe's labels on all 100 saved answers |
| `test_limits.py`, `test_standins.py` | Pacing, the 429 rule, and the stand-ins themselves |
| `test_classify.py` | Copies, each failure path, every stop, a hard kill, a simulated laptop sleep, 16 workers against 1, the guards |
| `test_jev_client.py`, `test_gemma.py` | Both HTTP clients against a local test server: status mapping, timeouts, no key in any error |
| `test_verify.py` | The blind test, failures counted not dropped, a kill mid-verify, the agreement report |
| `test_rank.py`, `test_group.py`, `test_memo.py` | The ranking equals the checker's own; membership rules; each way a memo can fail its check |
| `test_export.py` | The supplied checker passes on a full stand-in run, and names each of eight deliberate breaks |
| `test_end_to_end.py` | The command line from a stopped run to a passing export; Ctrl-C; the warm pass; refusals; a clean copy of the repo |
| `test_cost.py` | The instructor's two calculator tests; replay with no state file and no client; the measured pilot cost |
| `test_evals.py` | The planted cases, the wording trial's holdout guard, the cut-off table, the golden score |
| `test_readme.py` | Every link in the READMEs points at a file a clone would have; the test count stated here is the real one; no run is claimed that has not been made |

**Falsification.** A test that cannot fail proves nothing. In a scratch copy of the repo, never in the working tree, I removed the check that an evidence quote is an exact piece of the review, and ran the label tests:

```console
FAIL: test_each_bad_record_is_refused (tests.test_labels.Validate.test_each_bad_record_is_refused) (name='quote is not in the text')
AssertionError: InvalidAnswer not raised
FAIL: test_the_quote_must_be_an_exact_piece_not_a_close_one (tests.test_labels.Validate.test_the_quote_must_be_an_exact_piece_not_a_close_one)
AssertionError: InvalidAnswer not raised
Ran 13 tests in 0.014s
FAILED (failures=2)
```

Output was trimmed to the failing lines. `test_export.py` does the same thing against the supplied checker: it breaks a good export eight ways and asserts the checker's flag for each.

## Grading evidence

The brief lists the evidence the README must hold. Each item is answered below with what exists today. Items that need a real run say so and report nothing in its place.

### Results summary

The real runs: the 100-review pilot (four times, last on 2026-10-06 on the final code), the 500-review gate on 2026-10-05, the 10,000-review gate on 2026-10-06, and the full file that night. There is no golden agreement to report yet: the golden 50 is scored once and has not been.

Measured ([`runs/pilot4-cold/`](runs/pilot4-cold/run_summary.json), [`runs/gate-500/`](runs/gate-500/run_summary.json), [`runs/gate-10k/`](runs/gate-10k/run_summary.json), [`runs/full/`](runs/full/run_summary.json), [`cost/report.md`](cost/report.md), [`docs/validation-log.md`](docs/validation-log.md) entries 30 and 32 to 35):

| Measure | 100-review pilot | 500-review gate | 10,000-review gate | Full file |
|---|---|---|---|---|
| Labeled / quarantined | 100 / 0 | 500 / 0 | 10,000 / 0 | 660,609 / 13, all 13 empty text |
| Stopped and resumed | at 50 | at 283 | at 6,534 | at 131,072, by hand |
| Supplied checker | `pass`, no flags | `pass`, no flags | `pass`, no flags | `pass`, no flags |
| Jev requests | 100, 0 failed, one worker | 479 for 500 reviews (21 copies reused), 0 failed, 16 workers, 71.5 a second | 8,448 for 10,000 reviews (1,552 copies reused), 0 failed, 16 workers, 73.8 a second | 484,189 for 660,609 reviews (176,420 copies reused); 24 attempts failed and passed when sent again; 16 workers, 73.5 a second for 1.8 hours |
| Jev cost | $0.0042 | $0.0199 | $0.3525 | $20.3386 |
| Verifier (Gemma, blind) | 100 predictions, 0 failures | 500 predictions, 0 failures | 5,000 predictions, 0 failures | 5,000 predictions, 0 failures |
| Jev and Gemma give the same topic, intent and severity | 80 of 100 | 363 of 500: 146 of 241 complaints and cancellations, 217 of 259 others | 3,495 of 5,000: 1,307 of 2,243 complaints and cancellations, 2,188 of 2,757 others | 3,523 of 5,000: 1,294 of 2,196 complaints and cancellations, 2,229 of 2,804 others |
| Top issues by severity sum | usability 37, other 31, playback 25, billing 17 | usability 167, playback 143, other 135, billing 128 | usability 3,311, other 2,661, billing 2,319, playback 2,296 | usability 212,158, other 175,815, playback 147,175, billing 141,482 |
| Memo (Claude Sonnet 5.5) | passed first time, $0.022 | passed first time, $0.025 | passed first time, $0.026 | passed first time, $0.025 |
| Warm pass | 0 calls of any role | not part of this gate | not part of this gate | not part of this run |
| Time | 50 seconds end to end | classify 7 seconds, verify 124 seconds | classify 115 seconds, verify 1,301 seconds | classify 1 hour 50 minutes, verify 21 minutes |

The calculator's estimate against the full run:

| | Estimated from the pilot | Measured on the full run |
|---|---|---|
| Jev requests | 484,189 | 484,189, plus 24 failed attempts sent again |
| Input tokens a request | 1,003 | 1,000.0 |
| API cost, Jev and memo | $20.42 ($21.44 with 5% retries, $27.37 with no reuse) | $20.36 |
| Classify time | 1.79 hours | 1.83 hours |
| Verify time | 0.34 hours | 0.34 hours |

The measured cost prices Jev's output tokens at zero, as the calculator does. If the usage page shows they are billed, the run cost about $24.75 (*estimate*); see the limits below.

Two things these runs showed that the design did not expect: Jev's answers are not fully repeatable (the full run changed topic, intent or severity on 258 of the 10,000 reviews it shares with the gate, every one a review both runs had flagged), and the two engines agree much less on complaints than on other reviews.

What was measured before the build, in throwaway probes on 2026-10-04 (small samples, single runs; evidence in [`experiments/2026-10-04/`](experiments/2026-10-04/README.md) and [`docs/validation-log.md`](docs/validation-log.md)):

| Measure | Result | Kind |
|---|---|---|
| Jev on the 100 pilot reviews | 0 failed, 926 input tokens per request, $0.0039 per 100 reviews | measured |
| Jev speed | 78 requests a second with 16 workers, for 6 seconds | measured |
| Jev against 29 hand labels, all three fields | 24 (21 before five labels were revised) | measured |
| Gemma 26B against the same labels | 23 | measured |
| Money spent so far | Jev $0.056 by the provider's usage page on 2026-10-05; two outside raters $1.12 and $2.77 | measured |
| One full pass, 484,189 distinct texts | about $19 at the probe wording's request size; the frozen wording's requests are about 64 input tokens longer, about $1.30 more | estimate |
| One full pass at 75 requests a second | about 1.8 hours | estimate |

The calculator and its replay command are in [`cost/`](cost/README.md). Its report, [`cost/report.md`](cost/report.md), is built from the pilot of 2026-10-06 and holds the estimates above; it does not yet print the full run beside them.

### Architecture diagram

See [Architecture](#architecture): the six stages, where code ends and a model begins, each role's input and output, the saved tables and the stop and retry paths.

### One real review traced end to end

Not written up yet. The 500 gate's files hold everything a trace needs: [`records.jsonl`](runs/gate-500/grading/records.jsonl) (the label and its `label_config`), [`calls.jsonl`](runs/gate-500/grading/calls.jsonl) (the request that produced it), the verifier's prediction ([`verify_predictions.jsonl`](runs/gate-500/verify_predictions.jsonl)), `membership.csv`, `ranking.csv` and `claims.csv`. The traced review in the final README comes from the full run.

### Golden-set comparison and system checks

- **Golden 50:** labeled by hand and frozen on 2026-10-05 before any model saw the texts ([`evals/golden_50_labeled.csv`](evals/golden_50_labeled.csv), SHA-256 `b9d25cf271d921ec0a2545d2ca4a3ad8655e3b7056ac492b5a0458c5e4f2b79d`). Not scored yet: it is scored once, on the final setup, by [`evals/score_golden.py`](evals/score_golden.py), which gives two readings. The second applies the contract's rule that unclear text, praise and requests are severity 1; that rule would change 4 of the 50 hand labels.
- **Independent verifier procedure:** [Architecture](#architecture) and `pipeline/verify.py`. Run with the real model at every gate and on the full run: 5,000 blind predictions and 0 failures there ([`runs/full/verify_report.json`](runs/full/verify_report.json)).
- **Planted errors and injections:** 25 made-up cases with expected answers ([`evals/planted_cases.py`](evals/planted_cases.py)), kept out of every business total. Measured with the probe wording on 2026-10-04: Jev 21 of 25, missing 2 of 4 injections and 2 of 4 boycott slogans. Injections get a test and a reported miss rate, no guard. On 2026-10-05 a wording trial on 34 items measured a new intent wording, [`prompts/enrich-v2.json`](prompts/enrich-v2.json): 4 of 4 planted slogans (the probe wording got 2 of 4) and the outside raters' shared intent on 23 of 28 real boycott reviews (the probe wording 15) ([`evals/wording_trial_out.json`](evals/wording_trial_out.json)). It is now the frozen wording. The injection cases have not been measured with it yet.
- **Interruption and resume:** tested with stand-ins: a count stop, Ctrl-C, a hard kill and a simulated sleep, each followed by a resume that sends no completed review again (`tests/test_classify.py`, `tests/test_end_to_end.py`). Every real run was stopped once and resumed with the same command; the full run was stopped by hand with Ctrl-C after 122 seconds, and the checker reads that boundary from the export. A recording of it is not in the repo.
- **Every check so far, with its limits:** [`docs/validation-log.md`](docs/validation-log.md).

### Baseline, aggregation rules, tie-break and scope

Implemented in [`pipeline/rank.py`](pipeline/rank.py) and checked against the supplied checker's own arithmetic. Every completed complaint or cancellation joins exactly one issue, the one for its topic. For each issue: `complaint_count` is the number of members, `severity_sum` the sum of their severities, `mean_severity` the sum over the count to six decimals rounded half-up, and `priority_score` equals `severity_sum`. Order is score descending, then issue ID ascending. Praise, requests and unclear reviews are never members. Each copy counts as its own review. No trend analysis is in this version.

### Decision memo

The memo is [`runs/full/memo.md`](runs/full/memo.md), written by Claude Sonnet 5.5 from the full run. It recommends the usability issue, which ranks first on severity sum though `other` holds more complaints. The memo is one call of about 6,000 input tokens, so a paid model costs about two cents; the choice among three models is recorded in [`experiments/2026-10-05/memo-model/`](experiments/2026-10-05/memo-model/bakeoff.py). The code check (`pipeline/memo.py`) rejects a memo that cites an unknown ID, changes a number, cites a claim in a paragraph that does not name its issue, or speaks of revenue or churn. A rejected memo's text is kept with the reasons.

### Submission checklist

| Item | State |
|---|---|
| `.env` absent from tracked files and history | Checked 2026-10-05: only `.env.example` is tracked |
| Setup, calculator replay and ranking work in a clean copy with no key | Tested (`tests/test_end_to_end.py`, `tests/test_cost.py`) |
| Importing or opening the calculator starts nothing; the paid pilot is a separate command | Tested |
| Raw-data checksum recorded | Above, under Local setup |
| Repo public, evidence links open signed out | Not yet: the repo is private until submission |

## Running it for real

Steps 1 to 5 have been done, the full file on 2026-10-06; step 6 has not. A real run starts only with `--go`, on committed code, and scales in gates. Each gate is stopped once and resumed, because the checker needs to see saved work, an interruption, then new work.

1. Start the local model server and load `google/gemma-4-26b-a4b-qat`.
2. Wording trial on the tuning cases only: `python3 evals/wording_trial.py --go`.
3. The 100-review pilot, cold then warm: `python3 -m cost pilot --go`, then `python3 -m cost`. The pilot reads the state file before each step, so if it stops partway the same command picks up from there. `python3 -m cost evidence` writes the pilot files again from finished runs.
4. 500 reviews, then 10,000, then the full file:
   `python3 -m pipeline run --run NAME --new --go --workers 16 --input PATH.csv --stop-after N`, then the same command without `--new`.
   After each gate, `python3 -m pipeline nested --run NAME --against EARLIER` lists any review labeled at both gates whose labels changed.
5. `python3 -m pipeline export --run NAME --evidence runs/NAME`.
6. `python3 evals/score_golden.py --run NAME`, once.

Three commands for the cases a run can meet:

| Case | Command |
|---|---|
| The memo was edited by hand | `python3 -m pipeline memo --run NAME --file memo.md --save` runs the same number and citation check a model's memo must pass |
| The provider's usage page differs from the ledger | `python3 -m pipeline adjust --usd 0.25 --note "what the page showed"` |
| A review's request keeps failing | `python3 -m pipeline quarantine-stuck --run NAME --reason api_failure_after_retries`, on the owner's call only |

The step that is easy to miss: the prompt wording and the review cut-off are part of `label_config`. Changing either after the full run starts means a second full pass, which the $35 cap does not cover. Both are settled first.

## Known limitations and what I would do next

- **One full run, made once, with no one watching.** Every figure from it is read from its export. Nothing in it has been repeated, the golden 50 is not scored, and the usage page has not been read against it.
- **The order of places 2 to 4 rests on one pass.** It came out differently at 100, 500 and 10,000 reviews. On the full file it is other, playback, billing, with playback and billing 4% apart ([`runs/full/grading/ranking.csv`](runs/full/grading/ranking.csv)). A second pass would change about 3 labels in 100, and whether that could swap the two is not tested. Usability has ranked first at every size.
- **Jev does not repeat itself exactly.** The same 100 reviews, labeled twice an hour apart with the same wording, changed severity on 2 and the review flag on 3; the tone score moved by 0.03 or less on 9 in 10. A day apart it was more: of 500 reviews labeled at both the 500 and the 10,000 gate, Jev's own answer changed on 14 (severity on 7, topic on 6, intent on 2), and every one was a close call that carries the review flag in both runs (validation log entry 32). Forty minutes apart, 4 of 100 changed (entry 33). The full run changed 258 of the 10,000 gate's labels (2.6%), all flagged in both runs (entry 35). A rerun of the full file would not reproduce every label. The gate check on reviews seen at two gates allows for this: it stops only when more than 5 in 100 change topic, intent or severity.
- **One labeler.** No second person labeled anything, so nothing measures how firm the hand labels are. My severity labels differ from two outside raters' more than my topic and intent labels do. Fix: every score against hand labels is shown two ways, and the instructor's private sample is the outside check.
- **One issue per topic.** An issue names a topic, not a single defect, and `other` can rank high with nothing specific to fix. Fix: sub-issues inside a topic, decided after the first full pass.
- **The quote and the topic come from separate questions** and can point at different sentences. How often is unmeasured.
- **Injections are tested, not guarded.** The measured miss rate is reported as a limit.
- **Jev's output tokens are not billed, by one reading of the usage page.** On 2026-10-05 the page showed $0.056 for 1,640,194 tokens and 1,451 requests, which is input tokens times the rate; it would have shown about $0.069 if every token were billed ([`experiments/2026-10-05/billing/`](experiments/2026-10-05/billing/usage_page_check.py)). The ledger and the calculator price them at zero. The full run wrote 105,139,277 output tokens, so the page should rise by about $20.34 if they are not billed and about $24.75 if they are (*estimates*); the next reading settles it. Either way the total is under the $35 cap.
- **The verifier runs one request at a time.** 21 minutes for 5,000 reviews, measured. It checks a sample of 5,000, not the file.
- **The memo check proves the numbers were copied correctly, not that the argument is sound.** A person reads the memo.

## License

No license chosen yet; all rights reserved by default.

## Contributing

Not accepting outside contributions. This is individual coursework.
