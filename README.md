# Spotify Insight Pipeline

**A staged pipeline that turns 660,622 Spotify app reviews into a ranked list of product issues and a decision memo, with every number traceable to saved evidence.**

This is my final assignment for a Berkeley Haas course on building with AI: advise Spotify on where the next quarter of product effort should go, and make the answer inspectable. The one idea that shaped it is that models only read language and write prose; code owns everything that can be counted. Record accounting, validation, budgets, retries, ranking and every exported number are code. A model never counts, sorts or decides what runs next. That split is enforced, not promised: the supplied checker (`check_submission.py`) passes on an end-to-end test run, and eight deliberate breaks are each named by it.

**Status: built, tested, and run for real on 100, 500 and 10,000 reviews and then on the full file (2026-10-06): 660,609 reviews labeled, 13 empty ones set aside, the supplied checker `pass` with no flags, $20.36 and 2 hours 11 minutes of working time ([`runs/full/`](runs/full/run_summary.json)). Against the 50 hand labels, scored once, Jev has topic, intent and severity all right on 30 of 50. The provider's usage page has not been read against the run.** Every stage is tested end to end with stand-ins that replay saved answers. The 500-review gate (2026-10-05) and the 100-review pilot and 10,000-review gate (2026-10-06) each ran every stage with the real models, stopped once and resumed, and each export passes the supplied checker ([`runs/pilot4-cold/`](runs/pilot4-cold/run_summary.json), [`runs/gate-500/`](runs/gate-500/run_summary.json), [`runs/gate-10k/`](runs/gate-10k/run_summary.json)). Each number below says where it was measured.

**For the grader:** the [rubric map](#rubric-map) links each of the ten rubric points to its evidence. The one export the checker reads is [`grading/`](grading/run.json), a copy of the full run's, and [`cost/`](cost/README.md) holds the calculator.

The repo was built with an AI coding assistant (Claude Code); commits carry its co-author line. Design decisions, the hand labels and every go to spend money are mine. An agent reading this repo should start with [`CLAUDE.md`](CLAUDE.md).

Live URL: Not applicable. This is a command-line pipeline that runs locally; nothing is deployed.

```
Language   Python 3.14, standard library only (no dependency to install)
State      one SQLite file, write-ahead mode
Classify   Jev (TypeSafe), jev-1.13.0, one request per distinct review text
Verify     Gemma 26B, local through LM Studio, blind, on a fixed sample of 5,000
Name       Gemma 26B, local
Memo       Claude Sonnet 5.5 (Anthropic API), one call a run
Tests      545 automated (544 run with no outside network; 1 skipped unless the 97 MB file is present)
Checked    2026-10-07
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
| Issue names | Gemma 26B, local | A small bounded writing task: one name and one sentence per issue, eight calls on the full run, at no API cost |
| Memo | Claude Sonnet 5.5, Anthropic API | One call a run, about two cents. On the first pilot the local model needed four attempts to pass the memo check, so three paid models were compared on the pilot's evidence pack and the cheapest that passed was chosen ([`experiments/2026-10-05/memo-model/`](experiments/2026-10-05/memo-model/bakeoff.py), validation log entry 28) |
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
 6 MEMO        Sonnet   role "memo": recommendation from the ranked table and a
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
| `memo` | Claude Sonnet 5.5 | ranked table, claims, up to 5 quotes per issue, run facts | a markdown memo | Writing an argument | Computes every number first and rejects a memo that changes one |

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

The full dataset, `spotify_reviews_18months.csv` (97,400,616 bytes, 660,622 rows), is not in the repo. Download the course's [dataset ZIP from Google Drive](https://drive.google.com/file/d/1P0rUoAS_wVjp3BYKqXMEyD4u0uJP1Bvf/view), unzip it, and put the CSV in `feed/Final Assignment - Spotify Reviews Dataset/`, beside the smaller supplied files that are committed. It is an 18-month window (2022-05-17 to 2023-11-15) of BwandoWando's [3.4 Million Spotify Google Store Reviews](https://www.kaggle.com/datasets/bwandowando/3-4-million-spotify-google-store-reviews), version 2, on Kaggle, which its publisher lists as CC0. Its SHA-256 is `1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6`; prepare refuses to continue if the file with that checksum does not give its known counts.

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

545 tests: 544 pass with no outside network and no key (two client test files talk to a server on localhost), 1 is skipped unless the 97 MB file is present and `RUN_FULL=1` is set. That one reads the whole file and checks its known counts; it was run once on 2026-10-05 and passed (660,622 rows, 13 empty, 484,189 distinct texts, 159,701 missing app versions).

```console
$ python3 -m unittest discover -s tests -t .
----------------------------------------------------------------------
Ran 545 tests in 15.645s

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
| `test_trace.py` | The trace of one review equals what each exported file says; a copy is traced to its original's request; a failed attempt is listed; three known answers from the full run |
| `test_readme.py` | Every link in the READMEs points at a file a clone would have; the test count stated here is the real one; no run is claimed that has not been made; the memo lines quoted here are lines of the memo |

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

### Rubric map

The ten rubric points, each with the files that answer it. Every link is to a committed file, so nothing here needs a key or a paid call. The last column says where the evidence is thinner than the brief asks.

**Deliverable quality**

| Rubric point | Evidence | Where it is thin |
|---|---|---|
| 1. Accessible code, setup and artifacts | [Local setup](#local-setup): clone and run, Python standard library only. The graded export is [`grading/`](grading/run.json), the run evidence [`runs/full/`](runs/README.md), the calculator [`cost/`](cost/README.md), the labels and scores [`evals/`](evals/README.md). A test makes a fresh copy of the repo with no `.env` and no state file, then runs the ranking and four of the test files in it ([`tests/test_end_to_end.py`](tests/test_end_to_end.py)) | The 97.4 MB source file is linked, not committed |
| 2. Clear architecture, shared schema and provenance | [Architecture](#architecture) with its role table, and the [State file schema](#state-file-schema). The contract's labels and record types are enforced in one place, [`pipeline/labels.py`](pipeline/labels.py), and every record it accepts or refuses is also put through the supplied checker ([`tests/test_labels.py`](tests/test_labels.py)). [`runs/full/run_manifest.json`](runs/full/run_manifest.json) ties together the source checksum, the code commit and hash, the prompt hashes, the model IDs, the seeds and the checksum of every exported file. Every record carries `source_sha256` and `label_config`; a copy carries `cache_source_id`. The prompts are in [`prompts/`](prompts/enrich-v2.json) | None I know of |
| 3. Memo numbers linked to correct calculations and source evidence | Every issue-level number in [`runs/full/memo.md`](runs/full/memo.md) cites one of the 14 claims in [`grading/claims.csv`](grading/claims.csv). Each claim is a cell of [`grading/ranking.csv`](grading/ranking.csv), which `python3 -m pipeline rank` rebuilds from the records and the membership with no model. The supplied checker recomputes the same ranking and compares the claims with it: `pass`, no flags ([`runs/full/run_summary.json`](runs/full/run_summary.json)). [One review traced](#one-real-review-traced-end-to-end) shows a single review's share of CL-001 and CL-002 | The four reviews the memo quotes are among the most severe, as the memo says, not typical ones |
| 4. Coherent recommendation, alternatives and limitations | The memo recommends one issue, weighs four alternatives and lists its own limits. Mine are under [Known limitations](#known-limitations-and-what-i-would-do-next) | The code check proves the numbers were copied correctly, not that the argument is sound. Places 2 to 4 rest on one pass |

**Testing and evaluation**

| Rubric point | Evidence | Where it is thin |
|---|---|---|
| 5. 50 human labels, per-field comparisons and error analysis | The labels: [`evals/golden_50_labeled.csv`](evals/golden_50_labeled.csv), written by hand and frozen by hash before any model saw the texts. The score, made once: [`evals/golden_score_full.json`](evals/golden_score_full.json), with topic 40 of 50, intent 43, severity exact 40 (mean absolute error 0.22), sentiment mean absolute error 0.18, a confusion table for each field, the rows per topic, and the 10 rows where I noted a second defensible label or a translation. One row a review: [`evals/golden_cases_full.csv`](evals/golden_cases_full.csv). The 20 misses read one by one: [`evals/golden_error_analysis.md`](evals/golden_error_analysis.md). The tables are [below](#golden-set-comparison-and-system-checks) | One labeler. 30 of the 50 are `other` by hand, so the score says little about any one topic. The one-by-one readings are the AI assistant's |
| 6. Independent verification, planted-error and injection tests | The verifier is another maker's model and never sees the first label: 5,000 blind predictions, 0 failures, the same three labels on 3,523, and all 1,477 disagreements listed ([`runs/full/verify_report.json`](runs/full/verify_report.json), [`runs/full/verify_predictions.jsonl`](runs/full/verify_predictions.jsonl), [`prompts/verify-v1.md`](prompts/verify-v1.md)). A wrong label planted on purpose in a copy is flagged by the comparison ([`evals/compare_check.py`](evals/compare_check.py)). 25 made-up cases with expected answers, scored once with the frozen wording: 22 of 25, injections 3 of 4 ([`evals/planted_cases.py`](evals/planted_cases.py), [`evals/holdout_score_prompt-v2.json`](evals/holdout_score_prompt-v2.json)). Outside reads of the spec, the plan and the code are in [`docs/validation-log.md`](docs/validation-log.md) | The verifier covers a sample of 5,000. The two engines agree on about 6 complaints in 10 and nothing says which is right. One injection in four moved the answer; injections are tested, not guarded |
| 7. A real 100-review cold and warm pilot, a correct offline calculator, and demonstrated retry, spending and recovery controls | The pilot: [`cost/report.md`](cost/report.md), cold 100 of 100 for $0.0264 in 49.75 seconds, warm 0 calls. Its saved IDs, calls, usage and dated rates: [`cost/pilot_records.jsonl`](cost/pilot_records.jsonl), [`cost/pilot_calls.jsonl`](cost/pilot_calls.jsonl), [`cost/usage.csv`](cost/usage.csv), [`cost/rates.csv`](cost/rates.csv). `python3 -m cost` replays it with no key, and the instructor's two arithmetic tests are in [`tests/test_cost.py`](tests/test_cost.py). Retry: 24 attempts failed on the full run, and each passed when sent again; [one is shown below](#one-real-review-traced-end-to-end). Spending: one ledger, a $35 cap, the worst-case cost reserved before each request ([`pipeline/ledger.py`](pipeline/ledger.py)); the full run came to $20.36 against $20.42 estimated. Recovery: the full run was stopped by hand and resumed ([`grading/checkpoint_before.json`](grading/checkpoint_before.json), [`grading/checkpoint_after.json`](grading/checkpoint_after.json), [`runs/full/run_full_text.txt`](runs/full/run_full_text.txt)) | The record of the stop is a screenshot and the terminal's text, not a video. No real run reached the cap or met a 429, so those two stops are shown by tests only ([`tests/test_ledger.py`](tests/test_ledger.py), [`tests/test_limits.py`](tests/test_limits.py)). The provider's usage page has not been read against the full run |

**Working result**

| Rubric point | Evidence | Where it is thin |
|---|---|---|
| 8. Full ingestion, record coverage and successful classification | [`grading/ingestion.json`](grading/ingestion.json): 660,622 rows, 13 empty texts, 159,701 missing app versions, no repeated ID, the file's checksum as supplied. [`grading/records.jsonl.gz`](grading/records.jsonl.gz): one record for every source ID, 660,609 completed and 13 quarantined as `empty_review_text` ([`runs/full/quarantine.jsonl`](runs/full/quarantine.jsonl)). The supplied checker on `grading/`: `pass`, no flags, every row accounted for, every review with text validly classified, 176,420 valid exact-text reuses, coverage point 1.0 by its own arithmetic ([`runs/full/run_summary.json`](runs/full/run_summary.json)) | A valid record can still carry a wrong label; point 5 is the measure of that |
| 9. A runnable staged program with bounded calls, saved handoffs and demonstrated resume | One command takes any CSV path and runs the six stages, and the same command resumes ([`pipeline/cli.py`](pipeline/cli.py), [Walkthrough](#walkthrough)). Bounded: each of the 484,213 enrich requests in [`grading/calls.jsonl.gz`](grading/calls.jsonl.gz) carries one review, against a limit of 50. Handoffs: each stage's output is saved before the next reads it ([State file schema](#state-file-schema)) and exported for every run under [`runs/`](runs/README.md). Resume: 8,939 requests are marked `initial` and 475,274 `resume`, and no resumed request names a review completed before the stop | The walkthrough at the top is a stand-in run. The real runs are the exports |
| 10. A reproducible baseline ranking and a usable, grounded final output | `python3 -m pipeline rank` rebuilds [`grading/ranking.csv`](grading/ranking.csv) byte for byte from the records and the membership ([`pipeline/rank.py`](pipeline/rank.py); checked on the full run's files on 2026-10-07, validation log entry 38). The memo built on it is [`runs/full/memo.md`](runs/full/memo.md) | The ranking is exactly reproducible from the saved labels. The labels are not: a second paid pass would change about 3 in 100 |

### Results summary

The real runs: the 100-review pilot (four times, last on 2026-10-06 on the final code), the 500-review gate on 2026-10-05, the 10,000-review gate on 2026-10-06, and the full file that night. The golden 50 was scored once, on the full run: all three fields right on 30 of 50 (below).

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

Picked by rule, not by eye. Of the 5,000 reviews in the verify sample, 599 joined the first-ranked issue and were labeled by their own request; this is the first of them by review ID. None of the four reviews the memo quotes fell in the sample. The command reads committed files only, and the source CSV when it is there.

```console
$ python3 evals/trace_review.py 00d13536-bd53-4e93-9c76-22db75d384d5
review 00d13536-bd53-4e93-9c76-22db75d384d5

1 source   row hash 40af9736695222454f40a850d25a074f9f6fd5638dc8111c801d980230d4a337
           hashed again from the file: the same
           text: "Can't help to set as caller tune"
           stars 4, likes 0, app 8.7.44.968, 2022-07-09 19:25:57
2 enrich   usability / complaint / severity 4, sentiment -0.525, needs_review no
           entities []
           quote: "Can't help to set as caller tune"
           the quote is an exact piece of the text: yes
           label_config jev-1.13.0/prompt-v2/schema-v1/cut-0.70
           request 7165bcebebdf4d74b5f3d4900d629be1: succeeded, phase resume, jev-1.13.0, 945 in, 204 out, 0.10 s, session 55
3 verify   other / request / severity 1 (blind, request 513881a87f264d818860b0988d7d9651)
           same as the record: topic no, intent no, severity no
           a disagreement is reported and changes no label
4 group    issue-usability
5 rank     issue-usability is rank 1: 81756 complaints, severity sum 212158, mean 2.595014, score 212158
           this review adds 1 to the count and 4 to the severity sum
6 memo     claims about this issue: CL-001 complaint_count 81756, CL-002 severity_sum 212158, CL-003 mean_severity 2.595014, CL-004 priority_score 212158
           cited in the memo: CL-001, CL-002, CL-003, CL-004
           the memo quotes this review: no
```

| Step | Where it is saved |
|---|---|
| Source row and its hash | The source CSV; `source_sha256` on the record |
| Enrichment | The record in [`grading/records.jsonl.gz`](grading/records.jsonl.gz); its request in [`grading/calls.jsonl.gz`](grading/calls.jsonl.gz), with time and session in [`runs/full/run_log.jsonl.gz`](runs/full/run_log.jsonl.gz) |
| Verification | [`runs/full/verify_predictions.jsonl`](runs/full/verify_predictions.jsonl); the review is among the disagreements in [`runs/full/verify_report.json`](runs/full/verify_report.json) |
| Issue membership | [`grading/membership.csv`](grading/membership.csv) |
| Ranking | [`grading/ranking.csv`](grading/ranking.csv) |
| Memo claim | [`grading/claims.csv`](grading/claims.csv), cited in [`runs/full/memo.md`](runs/full/memo.md) |

**The same review is the ambiguous case.** The rule landed on a review the two engines read differently. Jev called it a usability complaint of severity 4. Gemma, blind, called it a request of severity 1 with no specific topic. The review flag is off, because Jev's lowest top probability was not under the 0.70 cut-off. The recorded handling is the design's: a disagreement is listed in the verify report and changes no label, since there is no fallback model. So the review counts as Jev labeled it, 1 in CL-001 and 4 in CL-002. The pipeline does not decide which engine is right. In the sample the two give the same three labels on 1,294 of 2,196 complaints and cancellations, so a case like this is common. Severity is what the ranking adds up, which is why the limits below say the severity sums lean high.

**A failed case.** The first request for another review timed out after 30 seconds (output trimmed to the enrich block):

```console
$ python3 evals/trace_review.py a1d7bf6e-29bd-439f-b135-b7c059f4227b
2 enrich   usability / complaint / severity 2, sentiment -0.505, needs_review no
           entities ["shuffle"]
           quote: "I don't like because its always shuffle"
           the quote is an exact piece of the text: yes
           label_config jev-1.13.0/prompt-v2/schema-v1/cut-0.70
           request 1fe9e03f30fb483e8d6c86aba6a133f6: failed, phase resume, jev-1.13.0, usage unknown, 30.02 s, session 55
             error: Temporary: TimeoutError: The read operation timed out
           request 903641281ba44c9795bb51913be4b329: succeeded, phase resume, jev-1.13.0, 945 in, 206 out, 0.19 s, session 55
```

The recorded handling: a timeout, a 429 or a 5xx puts the review back in the queue, up to four times. The failed attempt stays in `calls.jsonl` with its own request ID and no usage, its reserved cost stays counted as spent, and the review is completed only by the request that succeeded. The full run had 24 such attempts (16 timeouts, 8 HTTP 520). Each passed when sent again and none left a review unlabeled. The 13 reviews with empty text are the other kind of failure: they are never sent, and are quarantined with the reason `empty_review_text` ([`runs/full/quarantine.jsonl`](runs/full/quarantine.jsonl)).

### Golden-set comparison and system checks

- **Golden 50:** labeled by hand and frozen on 2026-10-05 before any model saw the texts ([`evals/golden_50_labeled.csv`](evals/golden_50_labeled.csv), SHA-256 `b9d25cf271d921ec0a2545d2ca4a3ad8655e3b7056ac492b5a0458c5e4f2b79d`). Scored once, on the full run, on 2026-10-06 by [`evals/score_golden.py`](evals/score_golden.py), after the run's export was committed ([`evals/golden_score_full.json`](evals/golden_score_full.json), validation log entry 36). It gives two readings; the second applies the contract's rule that unclear text, praise and requests are severity 1, which changes 4 of the 50 hand labels.

  | Jev against the golden 50 | Labels as frozen | With the severity rule applied |
  |---|---|---|
  | Topic | 40 of 50 | 40 of 50 |
  | Intent | 43 of 50 | 43 of 50 |
  | Severity, exact | 40 of 50 | 38 of 50 |
  | All three | 30 of 50 | 30 of 50 |
  | Severity error, mean and mean absolute | +0.10, 0.22 | +0.18, 0.26 |
  | Quote is an exact copy of the text | 50 of 50 | 50 of 50 |

  30 of 50 stands for somewhere between about 46% and 72%. Half the topic misses are hand `other` reviews that Jev put in catalog or usability. Five of the seven intent misses are reviews I labeled `unclear` that Jev read as a complaint, a cancellation or a request, so on this sample 4 of Jev's 24 complaints and cancellations are not complaints by hand, and it found 20 of my 21. The review flag is on 9 of the 20 reviews with a wrong label and on 5 of the 30 with none.

  **The 20 misses, read one by one** ([`evals/golden_error_analysis.md`](evals/golden_error_analysis.md); case by case with pass or fail per field in [`evals/golden_cases_full.csv`](evals/golden_cases_full.csv); validation log entry 37). Six are severity one step apart, six sit on a topic boundary the contract draws, three are not in English, three are boycott or political text and two are short or doubtful praise. Read against the contract's wording, 3 are plain Jev errors, 4 are cases where the contract's own example points at Jev's label, 3 carry my fallback label for a language I did not read, and 10 are open. The three plain errors: premium-only controls put in usability where the contract says billing, lost controls read as a playback failure, and "Great..." read as unclear. The reading was made by the AI assistant after the score was saved, with my permission to open the labels; no label and no score changed.
- **Independent verifier procedure:** [Architecture](#architecture) and `pipeline/verify.py`. Run with the real model at every gate and on the full run: 5,000 blind predictions and 0 failures there ([`runs/full/verify_report.json`](runs/full/verify_report.json)).
- **Planted errors and injections:** 25 made-up cases with expected answers ([`evals/planted_cases.py`](evals/planted_cases.py)), kept out of every business total. Measured with the probe wording on 2026-10-04: Jev 21 of 25, missing 2 of 4 injections and 2 of 4 boycott slogans. Injections get a test and a reported miss rate, no guard. On 2026-10-05 a wording trial on 34 items measured a new intent wording, [`prompts/enrich-v2.json`](prompts/enrich-v2.json): 4 of 4 planted slogans (the probe wording got 2 of 4) and the outside raters' shared intent on 23 of 28 real boycott reviews (the probe wording 15) ([`evals/wording_trial_out.json`](evals/wording_trial_out.json)). It is now the frozen wording. With it, scored once on 2026-10-05, the planted cases read 22 of 25: contract rules 9 of 9, slogans 4 of 4, non-English 3 of 3, injections 3 of 4 (one injected instruction moved the answer to topic `support`, intent `request`), and text with no letters 3 of 5 ([`evals/holdout_score_prompt-v2.json`](evals/holdout_score_prompt-v2.json), validation log entry 26). A deliberately wrong label is planted in a copy by [`evals/compare_check.py`](evals/compare_check.py), and the verifier's comparison flags each one.
- **Interruption and resume:** tested with stand-ins: a count stop, Ctrl-C, a hard kill and a simulated sleep, each followed by a resume that sends no completed review again (`tests/test_classify.py`, `tests/test_end_to_end.py`). Every real run was stopped once and resumed with the same command; the full run was stopped by hand with Ctrl-C after 122 seconds, and the checker reads that boundary from the export. The 131,072 reviews completed at the stop are 8,939 finished requests and the 122,133 copies of their texts; that the total is a power of two is chance, and the export rebuilds it (validation log entry 38). The record of it is a screenshot of that terminal session and its text, not a video: [`runs/full/run_full_screenshot.png`](runs/full/run_full_screenshot.png), [`runs/full/run_full_text.txt`](runs/full/run_full_text.txt). The two checkpoint files are [`checkpoint_before.json`](runs/full/grading/checkpoint_before.json) (131,072 completed) and [`checkpoint_after.json`](runs/full/grading/checkpoint_after.json) (660,609).
- **Every check so far, with its limits:** [`docs/validation-log.md`](docs/validation-log.md).

### Baseline, aggregation rules, tie-break and scope

Implemented in [`pipeline/rank.py`](pipeline/rank.py) and checked against the supplied checker's own arithmetic. Every completed complaint or cancellation joins exactly one issue, the one for its topic. For each issue: `complaint_count` is the number of members, `severity_sum` the sum of their severities, `mean_severity` the sum over the count to six decimals rounded half-up, and `priority_score` equals `severity_sum`. Order is score descending, then issue ID ascending. Praise, requests and unclear reviews are never members. Each copy counts as its own review. No trend analysis is in this version.

What the totals do and do not cover:

- **Incomplete classifications: none.** All 660,609 reviews with text carry a label. The 13 with empty text are quarantined: accounted for, not classified. 191,158 labels (28.9%) carry the review flag, and a flagged label still counts in the ranking.
- **Missing data.** 159,701 rows have no app version. Nothing in the ranking uses it, so those rows are labeled like any other. Stars, likes, version and timestamp are kept exactly as read and never reach the classifier, which sees the text only.
- **Review bias.** These are people who chose to write a Play Store review between May 2022 and November 2023. They are not a sample of Spotify's users, and the file holds no plan tier, revenue or confirmed cancellation. A `cancellation` label is what someone wrote, not what they did. Two months hold a quarter of the file: July 2023 (85,079 reviews) and October 2023 (89,104), where no other full month passes 42,000 ([`grading/ingestion.json`](grading/ingestion.json)). So the totals lean toward whatever drove those two bursts, and the first and last months are partial. A review whose text repeats another's is still its own row and counts once, as the contract requires; that is 176,420 of the 660,609.
- **So the ranking says** how many complaints were written and how severe they were rated. It does not say how many users are affected, and nothing here estimates revenue or churn.

### Decision memo

The memo is [`runs/full/memo.md`](runs/full/memo.md), written by Claude Sonnet 5.5 from the full run. Its recommendation, copied as written:

> Put the next quarter's effort on issue-usability (repetitive playback and excessive advertisements). It ranks first, and I am not recommending a different issue. Its priority score is 212158 [CL-004], which comes from a severity sum of 212158 [CL-002] across 81756 complaints [CL-001]. It is the largest on severity sum, though not on complaint count.

The file goes on to the supporting numbers, four alternatives, four quoted reviews with their IDs and six limits. Every issue-level number in it carries a claim ID from [`grading/claims.csv`](grading/claims.csv). `other` holds more complaints than usability (85,466 against 81,756) at a lower mean severity (2.06 against 2.60), which is why usability ranks first on severity sum. What is unresolved is stated in the memo's run facts: 13 reviews quarantined and 191,158 labels (28.9%) flagged for review. No review with text is left unclassified.

The memo is one call of about 6,000 input tokens, so a paid model costs about two cents; the choice among three models is recorded in [`experiments/2026-10-05/memo-model/`](experiments/2026-10-05/memo-model/bakeoff.py). The code check (`pipeline/memo.py`) rejects a memo that cites an unknown ID, changes a number, cites a claim in a paragraph that does not name its issue, or speaks of revenue or churn. A rejected memo's text is kept with the reasons.

### Submission checklist

| Item | State |
|---|---|
| `.env` absent from tracked files and history | Checked 2026-10-07: only `.env.example` is tracked, and a scan of the tree, the history and the gzipped exports finds nothing shaped like a key |
| One `grading/` folder at the root | A copy of the full run's export, file for file. The supplied checker on it: `pass`, no flags (2026-10-07, validation log entry 38) |
| Setup, calculator replay and ranking work in a clean copy with no key | Tested (`tests/test_end_to_end.py`, `tests/test_cost.py`) |
| Importing or opening the calculator starts nothing; the paid pilot is a separate command | Tested |
| Raw-data source link and checksum recorded | Above, under Local setup |
| Repo public, evidence links open signed out | The repo answers signed out (checked 2026-10-07). The links are checked against the tracked files by `tests/test_readme.py`; they have not each been opened signed out |

## Running it for real

All six steps have been done, the full file and the golden score on 2026-10-06. A real run starts only with `--go`, on committed code, and scales in gates. Each gate is stopped once and resumed, because the checker needs to see saved work, an interruption, then new work.

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

- **One full run, made once, with no one watching.** Every figure from it is read from its export. Nothing in it has been repeated, and the usage page has not been read against it.
- **The only accuracy figure is 30 of 50.** All three fields match my hand labels on 30 of the golden 50, about 46% to 72% at that size, from one labeler. On that sample Jev counts some unclear reviews as complaints and rates severity a little high, so the complaint counts and severity sums behind the ranking lean high. By how much on the full file, and whether evenly across issues, is not measured: 30 of the 50 are `other` by hand and no topic besides it has more than 6.
- **The order of places 2 to 4 rests on one pass.** It came out differently at 100, 500 and 10,000 reviews. On the full file it is other, playback, billing, with playback and billing 4% apart ([`runs/full/grading/ranking.csv`](runs/full/grading/ranking.csv)). A second pass would change about 3 labels in 100, and whether that could swap the two is not tested. Usability has ranked first at every size. One boundary alone could swap places 3 and 4: the contract sends premium-only controls to billing, and 9,403 of usability's 81,756 complaints name Premium. Counted as billing they would leave usability first and put billing ahead of playback (a what-if by code, validation log entry 37).
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
