# Spotify Insight Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the staged pipeline in the approved spec so the supplied checker returns `pass` on the full file, the cost calculator replays offline, and the golden 50 is scored once.

**Architecture:** One Python package, `pipeline/`, over one SQLite state file. Code owns state, record accounting, validation, budgets, ranking and export. Three model roles sit behind small client interfaces (Jev for `enrich`; Gemma 26B for `verify`, `group` and `memo`), so every stage is tested with stand-ins before a real call is made. The work is six phases, and each ends with working, tested software. No paid gate runs until Tasks 1 to 17 pass their tests.

**Tech Stack:** Python 3.14, standard library only (`sqlite3`, `csv`, `json`, `hashlib`, `decimal`, `urllib.request`, `threading`, `argparse`, `unittest`). SQLite in write-ahead mode. Tests run with `/opt/homebrew/bin/python3 -m unittest discover -s tests -t . -v`.

**Spec:** `docs/superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md` (approved 2026-10-05; section 12 holds every ruling). Read it with `CLAUDE.md`, which lists the checker rules that are easy to miss.

**How this plan differs from the skill's template:** each task gives exact files, exact interfaces and named tests with what they assert. It does not carry the finished code for every step. Travis asked for speed and the build needs his go, so code is written test-first at execution, one task at a time. The schema, the export rules and the gate pass marks are written out in full because other tasks depend on their exact form.

## Global Constraints

Copied from the spec. Every task inherits them.

- Python 3.14, standard library only. No dependency to install.
- No trimming and no Unicode normalization anywhere. Row hashes use the checker's `row_sha` logic.
- The classifier sees `review_text` only. Stars and other fields never enter a prompt or a cache key.
- Empty text means `review_text.strip()` is empty: status `quarantined`, reason exactly `empty_review_text`, never sent to a model.
- Jev: `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer`, model pinned to `jev-1.13.0`, one request per original text, at most 16 at once, at most 75 requests per second (documented limits: 80 per second, 100,000 tokens per second).
- Budget: $25 of total Jev spend across all runs. Rate $0.042 per million input tokens. The ledger starts with $0.0485 measured plus $0.005 estimated.
- Gemma 26B through LM Studio at `localhost:1234/v1`: `temperature` 0, `reasoning_effort` `none`, `response_format` of type `json_schema`, one review per request.
- No fallback model. Hard cases are flagged, never re-labeled.
- `label_config` names model, prompt version, schema version and cut-off, for example `jev-1.13.0/prompt-v1/schema-v1/cut-0.70`.
- Export types are strict: `severity` an int 1 to 5, `needs_review` a bool, `sentiment` a finite number in [-1, 1], `entities` a list of non-blank strings, `evidence_quote` a non-blank exact substring of the source text.
- Ranking strings: plain integer strings; `mean_severity` to six decimals, half-up, with `Decimal`; order by `priority_score` descending, then `issue_id` ascending.
- Golden labels never reach a prompt, a cut-off or grouping. Scripts that read them print counts only.
- No model call, local or paid, and no gate without Travis's go. Never print a value from `.env`.
- `feed/` is read-only input. Never commit the 97 MB CSV, the state file, `local-reference.json` or `self-check.json`.
- Planted and synthetic cases live in `evals/`, never in `grading/calls.jsonl` or a business total.
- A completed review is never sent again. A review is `completed` only after its answer passes validation.

## Review Focus

Five conditions the spec implies but does not walk through, most likely first. Each has a test in the task that owns the code.

1. **A fresh input CSV** (the instructor may ask for one): a byte-order mark, CRLF line ends, extra columns, a missing required column, repeated review IDs, a one-row file, fewer than 5,000 rows. Expected: the first three are accepted; a missing column or a repeated ID stops prepare with a plain message; the supplied-file guards are skipped and the run says so; the verify sample becomes the whole run. Test in Task 3.
2. **Awkward text:** a multi-line review, quote characters, emoji only, the literal `None`, 30,000 characters. Expected: the row hash equals the checker's, the quote is an exact substring, identical bytes share one result, and nothing is trimmed. Tests in Tasks 1, 3 and 7.
3. **Two terminals on one state file, or a lock left by a dead process.** Expected: the second process refuses with the holder's PID; a lock whose PID is gone is cleared with a message. Test in Task 2.
4. **The laptop sleeps mid-session.** Expected: in-flight requests time out and return to `pending`, the 60-second failure stop ends the session cleanly, nothing completed is lost, and the same command resumes. Test in Task 9 with an injected clock.
5. **The local model server misbehaves:** wrong model loaded, server gone mid-stage, or a review longer than the bound set for a verify prompt. Expected: a wrong model or a lost connection halts the stage and is never counted as a failed review; an over-long review is recorded as a verify failure with its reason and is not sent cut short. Tests in Tasks 11 and 12.

## File structure

```
pipeline/
  __init__.py
  __main__.py     python3 -m pipeline
  cli.py          commands: run, status, export, rank, quarantine-stuck
  hashing.py      row hash, file hash, run-order key, text key
  state.py        schema, connection, lock, run registry, sessions, the save protocol
  prepare.py      stage 1
  labels.py       vocabularies, record validation, severity and tone mapping, the fixed severity rule
  ledger.py       reservations, charges, the cap
  splitter.py     sentence pieces, each an exact substring
  jev.py          request builder, answer parser, HTTP client
  limits.py       shared rate limiter and the 429 rule
  classify.py     stage 2: workers, retries, stops
  gemma.py        LM Studio client: model check, schema, leaked-token check
  verify.py       stage 3
  group.py        stage 4: membership by code, names by Gemma
  rank.py         stage 5: pure, reads committed files
  memo.py         stage 6: claims, evidence pack, the call, the code check
  export.py       grading/, run evidence, then the supplied checker
  standins.py     stand-in Jev (replays saved answers) and stand-in Gemma, for tests only
prompts/
  enrich-v1.json  Jev's questions and choices
  examples.md     worked examples of each definition (the contract asks for these)
  verify-v1.md    the contract's label section word for word, plus the output schema
  group-v1.md, memo-v1.md
  features-v1.txt the feature-word list
cost/
  __main__.py     replay (default) and pilot --go
  calc.py         arithmetic only
  rates.csv, local_compute.csv, usage.csv, pilot_calls.jsonl, pilot_records.jsonl, report.md, README.md
evals/
  planted_cases.py, wording_trial.py, cutoff_table.py, score_golden.py, compare_check.py
tests/
  test_*.py       one file per module, plus test_end_to_end.py
  fixtures.py     synthetic CSV builder and stand-in wiring
runs/             run evidence (committed); state.sqlite (ignored)
```

`experiments/` stays as it is: evidence, not code to reuse. Two things are copied out of it on purpose: the question wording in `tool-choice/jev_spike.py` and the fixed severity rule in `2026-10-05/labels/rule_check.py`.

## Schema (exact; Task 2 creates it)

```sql
CREATE TABLE runs (
  run TEXT PRIMARY KEY, created_utc TEXT NOT NULL,
  input_path TEXT NOT NULL, input_sha256 TEXT NOT NULL, seed TEXT NOT NULL,
  verify_seed TEXT NOT NULL, verify_size INTEGER NOT NULL, sample_seed TEXT NOT NULL,
  code_commit TEXT NOT NULL, label_config TEXT NOT NULL,
  hashes_json TEXT NOT NULL,      -- content hash of each prompt, schema, word list, splitter, and the cut-off
  configs_json TEXT NOT NULL      -- verify, group and memo model, settings and prompt version
);
CREATE TABLE sessions (
  session_id INTEGER PRIMARY KEY, run TEXT NOT NULL, stage TEXT NOT NULL, workers INTEGER NOT NULL,
  started_utc TEXT NOT NULL, started_mono REAL NOT NULL, ended_mono REAL, ended_how TEXT
);
CREATE TABLE reviews (
  run TEXT NOT NULL, review_id TEXT NOT NULL,
  review_text TEXT NOT NULL, review_rating TEXT NOT NULL, review_likes TEXT NOT NULL,
  app_version TEXT NOT NULL, review_timestamp TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, text_key TEXT NOT NULL, run_order INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','completed','quarantined')),
  reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  cache_source_id TEXT,           -- NULL on an original; the original's review_id on a copy
  completed_session INTEGER, in_verify_sample INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (run, review_id)
);
CREATE INDEX reviews_by_text ON reviews (run, text_key);
CREATE INDEX reviews_by_order ON reviews (run, status, run_order);
CREATE TABLE results (
  run TEXT NOT NULL, text_key TEXT NOT NULL,
  topic TEXT NOT NULL, intent TEXT NOT NULL, severity INTEGER NOT NULL, sentiment REAL NOT NULL,
  entities_json TEXT NOT NULL, evidence_quote TEXT NOT NULL, needs_review INTEGER NOT NULL,
  min_top_probability REAL NOT NULL, raw_json TEXT NOT NULL, model TEXT NOT NULL,
  PRIMARY KEY (run, text_key)
);
CREATE TABLE calls (
  request_id TEXT PRIMARY KEY, run TEXT NOT NULL, role TEXT NOT NULL,
  review_ids_json TEXT NOT NULL, model TEXT NOT NULL, label_config TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('pending','succeeded','failed')),
  input_tokens INTEGER, output_tokens INTEGER, usage_known INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER, error TEXT, started_utc TEXT NOT NULL, seconds REAL, session_id INTEGER NOT NULL
);
CREATE TABLE ledger (
  id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, run TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('opening','reserve','actual','kept')),
  input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL DEFAULT 0, created_utc TEXT NOT NULL
);
CREATE TABLE verify (
  run TEXT NOT NULL, review_id TEXT NOT NULL, outcome TEXT NOT NULL,   -- 'predicted' or 'failed'
  topic TEXT, intent TEXT, severity INTEGER, reason TEXT, request_id TEXT,
  PRIMARY KEY (run, review_id)
);
CREATE TABLE issues (run TEXT NOT NULL, issue_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL, model TEXT, PRIMARY KEY (run, issue_id));
CREATE TABLE membership (run TEXT NOT NULL, issue_id TEXT NOT NULL, review_id TEXT NOT NULL, PRIMARY KEY (run, issue_id, review_id));
CREATE TABLE artifacts (key TEXT PRIMARY KEY, run TEXT NOT NULL, role TEXT NOT NULL, input_json TEXT NOT NULL, output_json TEXT NOT NULL, model TEXT NOT NULL, created_utc TEXT NOT NULL);
```

A call row with outcome `pending` is the intent row of spec section 4: it is committed before the request is sent. On `verify`, `group` and `memo` calls, `label_config` holds that stage's own config string; the checker reads it on `enrich` calls only.

## Export rules (exact; Task 14 implements them, read from `check_submission.py`)

- `records.jsonl`: one line per source ID. Completed: `review_id`, `source_sha256`, `status`, `topic`, `intent`, `sentiment`, `severity`, `entities`, `evidence_quote`, `needs_review`, `label_config`, plus `cache_source_id` on a copy. Quarantined: `review_id`, `source_sha256`, `status`, `reason`.
- A copy's eight label fields equal its original's. The original has no `cache_source_id` of its own.
- `calls.jsonl`: `request_id`, `role`, `review_ids`, `model`, `outcome`, `label_config`, `input_tokens`, `output_tokens`, `usage_known`, and `phase` on enrich calls. A call with no usage is written with zeros and `usage_known: false`. Only this run's calls are written.
- **Boundary:** the end of the first classify session that saved at least one new non-copy completion while at least one original was still unlabeled, provided at least one original is completed after it. Enrich calls in sessions up to the boundary are `initial`; later ones are `resume`. `checkpoint_before.json` lists the reviews completed at the boundary, copies included. `checkpoint_after.json` lists every completed review. Neither lists a quarantined review.
- The checker then needs: `before` non-empty and a strict subset of `after`; every non-copy ID in `before` on a succeeded `initial` call with the record's `label_config`; at least one new non-copy ID on a succeeded `resume` call; no `resume` call naming an ID in `before`.
- If no boundary exists, export says so before it runs the checker.
- `membership.csv` header `issue_id,review_id`. `ranking.csv` header `rank,issue_id,complaint_count,severity_sum,mean_severity,priority_score`. `claims.csv` header `claim_id,issue_id,metric,value`.
- `run.json`: `version` `a5-audit-v1`, `analysis_count`, `analysis_sha256`, `classification_input_fields` `["review_text"]`, `allow_multi_issue` `false`.
- Only `records.jsonl` and `calls.jsonl` may be gzipped, and never both forms at once.
- All four roles need at least one `succeeded` call.

---

## Phase 1: foundation (no network, no model)

### Task 1: Skeleton and hashing

**Files:** Create `pipeline/__init__.py`, `pipeline/hashing.py`, `tests/__init__.py`, `tests/fixtures.py`, `tests/test_hashing.py`. Modify `.gitignore` (add `runs/state.sqlite*`).

**Interfaces, produces:**
- `hashing.FIELDS: tuple[str, ...]` (the six source fields in contract order)
- `hashing.row_sha(row: dict[str, str]) -> str`
- `hashing.file_sha(path) -> str`
- `hashing.order_key(seed: str, review_id: str) -> str` (SHA-256 hex of `seed:review_id`)
- `hashing.text_key(text: str) -> str` (SHA-256 hex of the exact UTF-8 bytes)
- `fixtures.checker()` (the supplied `check_submission.py` loaded as a module by path)
- `fixtures.write_csv(path, rows) -> None` and `fixtures.synthetic_rows(n, *, empties=1, copies=2) -> list[dict]`

- [ ] Write `test_row_sha_matches_checker`: for every row of `cost_100.csv`, `hashing.row_sha(row) == fixtures.checker().row_sha(row)`.
- [ ] Write `test_run_order_known_answer`: sorting the IDs of `checkpoint_500.csv` by `order_key("berkeley-fall-2026-assignment-5-v1", id)` gives the file's own order, and every golden ID sorts before every `analysis_10000.csv` ID. (Verified true on 2026-10-05.)
- [ ] Write `test_awkward_text`: multi-line text, quote characters, emoji only, the literal `None` and a 30,000-character text each hash the same as the checker; two texts differing by one trailing space get different `text_key` values.
- [ ] Run the tests; expect failures for the missing module. Implement. Run; expect pass.
- [ ] Commit.

### Task 2: State file, lock, run registry

**Files:** Create `pipeline/state.py`, `tests/test_state.py`.

**Interfaces, produces:**
- `state.connect(path) -> sqlite3.Connection` (creates the schema above; WAL; `busy_timeout` 30 s; rows by name)
- `state.RunLock(path)` with `acquire()` and `release()`; raises `state.Locked(pid)`
- `state.create_run(db, name, *, input_path, input_sha256, seed, verify_seed, verify_size, sample_seed, code_commit, label_config, hashes: dict[str, str], configs: dict) -> None`
- `state.check_resume(db, name, *, input_sha256, seed, code_commit, hashes, allow_commit: str | None = None) -> None`; raises `state.ResumeRefused(names: list[str])`
- `state.open_session(db, run, stage, workers, clock) -> int`, `state.close_session(db, session_id, ended_how, clock) -> None`
- `state.code_commit() -> str` (`git rev-parse HEAD`, with `-dirty` when the tree has changes)

- [ ] Tests: schema is created once and reopening keeps data; `create_run` twice raises; `check_resume` passes when nothing changed and names each differing item (input, seed, each hash key) when something did; a different commit is refused, and passes only when `allow_commit` equals the new commit (the override is written to the run's log row); a second `RunLock.acquire()` raises `Locked` with the PID; a lock file holding a dead PID is cleared with a message.
- [ ] Run, implement, run.
- [ ] Commit.

### Task 3: Prepare

**Files:** Create `pipeline/prepare.py`, `tests/test_prepare.py`.

**Interfaces, consumes:** `hashing.*`, `state.connect`. **Produces:**
- `prepare.prepare(db, run, input_path, *, seed, verify_seed, verify_size=5000) -> dict` returning counts: `rows`, `empty`, `distinct_texts`, `copies`, `missing_app_version`, `verify_sample`, `supplied_file: bool`
- `prepare.SUPPLIED = {"sha256": "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6", "rows": 660622, "empty": 13, "distinct_texts": 484189, "missing_app_version": 159701}`

Rules: read with `csv.DictReader(strict=True)` and `utf-8-sig`; no trimming. `run_order` is the rank by `order_key(seed, review_id)`. Among reviews with byte-identical nonempty text the first in run order is the original; the rest get `cache_source_id`. The verify sample is the `verify_size` nonempty reviews with the lowest `order_key(verify_seed, review_id)`, or all of them when the run is smaller.

- [ ] Tests on synthetic CSVs: every row lands in `reviews`; whitespace-only text is `quarantined` with reason `empty_review_text`; copies point at the first in run order and the original points at nothing; counts add up (`pending + quarantined == rows`); the verify sample is fixed and has the right size.
- [ ] Review Focus 1: a byte-order mark, CRLF and extra columns are accepted; a missing column and a repeated ID each raise with a plain message; a one-row file and a 10-row file work, and the verify sample is the whole run.
- [ ] Guard test: when the file's SHA-256 is the supplied one, wrong counts raise. Simulate by patching `SUPPLIED` to a synthetic file's hash with a wrong row count. For any other input the result says `supplied_file: False`.
- [ ] Known-answer test (slow, skipped unless `RUN_FULL=1`): the real 97 MB file gives 660,622 rows, 13 empty, 484,189 distinct texts, 159,701 missing app versions.
- [ ] Run, implement, run. Commit.

### Task 4: Labels and validation

**Files:** Create `pipeline/labels.py`, `tests/test_labels.py`.

**Interfaces, produces:**
- `labels.TOPICS`, `labels.INTENTS` (tuples, contract order)
- `labels.SEVERITY = {"no_problem": 1, "annoyance": 2, "degraded": 3, "blocked": 4, "serious_harm": 5}`
- `labels.sentiment_from_tone(score: int) -> float` (`score / 2 - 1`; raises `labels.InvalidAnswer` outside 0 to 4, never clamps)
- `labels.validate(text: str, record: dict) -> None`; raises `labels.InvalidAnswer(reason)`
- `labels.by_rule(intent: str, severity: int) -> int` (the contract's fixed rule; evaluation only, never applied to a pipeline label)

- [ ] Tests: each strict type from the checker's schema line is enforced (`severity` as `True`, `3.0` or `"3"` is rejected; `needs_review` as `1` is rejected; `sentiment` `nan` or `1.5` is rejected; an `entities` entry of `" "` is rejected); a quote that is not an exact substring is rejected; a blank quote is rejected; tone 0 to 4 maps to -1, -0.5, 0, 0.5, 1 and tone 5 raises.
- [ ] Cross-check test: build a record `labels.validate` accepts and one it rejects for each reason, export each through a one-row `records.jsonl`, and assert the checker's `audit` agrees (valid, `invalid_schema` or `unsupported_quote`).
- [ ] Run, implement, run. Commit.

### Task 5: Ledger and the save protocol

**Files:** Create `pipeline/ledger.py`, extend `pipeline/state.py`, create `tests/test_ledger.py`, `tests/test_save_protocol.py`, `cost/rates.csv`.

**Interfaces, produces:**
- `ledger.Ledger(db, rates_path, cap_usd=Decimal("25"))`
- `Ledger.would_pass_cap(reserve_tokens: int) -> bool`, `Ledger.spent_usd() -> Decimal`, `Ledger.reserved_usd() -> Decimal`
- `Ledger.opening(usd_measured, usd_estimated)` (written once: the probe spend)
- `state.begin_attempt(db, ledger, *, request_id, run, role, review_ids, model, label_config, session_id, reserve_tokens) -> None` (one transaction: the `pending` call row and the `reserve` ledger row; raises `ledger.CapReached` and writes nothing if the cap would be passed)
- `state.finish_attempt(db, request_id, *, outcome, input_tokens=None, output_tokens=None, http_status=None, error=None, seconds, result: dict | None = None) -> None` (one transaction: the call row, the `actual` or `kept` ledger row, and, when `result` is given, the `results` row plus `completed` on the original and every copy with `completed_session`)
- `state.recover_orphans(db, run) -> int` (each `pending` call becomes `failed` with usage unknown, its reservation is `kept`, its review returns to `pending`)
- `state.return_to_pending(db, run, review_id)`, `state.quarantine(db, run, review_id, reason)` (copies follow their original and carry no cache pointer)

Dollars are computed from tokens and `rates.csv` at read time; the ledger stores billed units only.

- [ ] Tests: reserve then actual leaves spent equal to the actual and reserved at zero; an attempt with no usage keeps its full reservation as spent; `begin_attempt` refuses when spent plus reserved plus the next reservation would pass the cap and writes no row; `finish_attempt` with a result completes the original and its copies in one transaction (kill between is simulated by raising inside the transaction and asserting nothing changed); `recover_orphans` turns a `pending` call into a failed one with `usage_known` 0 and returns the review to `pending`; a quarantined original takes its copies with it.
- [ ] Run, implement, run. Commit.

## Phase 2: classify

### Task 6: Feature-word list (draft for Travis to read)

**Files:** Create `evals/feature_words.py`, `prompts/features-v1.txt`, `evals/feature_words_out.txt`.

- [ ] Count over the full file (code, no model), on lowercased text, how many reviews hold each candidate as a whole word or phrase. An entry matches itself and itself plus `s`. Candidates: shuffle, smart shuffle, playlist, queue, lyrics, podcast, audiobook, offline, download, premium, ads, search, library, liked songs, discover weekly, daily mix, wrapped, dj, radio, autoplay, repeat, skip, crossfade, equalizer, sleep timer, car mode, widget, lock screen, notification, bluetooth, carplay, android auto, chromecast, connect, canvas, video, login, password, account, subscription, free trial, family plan, student, payment, refund, update, recommendation. Keep each candidate found in at least 100 reviews, one per line, and save every count in `feature_words_out.txt`.
- [ ] Test: every listed entry has a saved count of at least 100; no entry is a topic or intent name; the list has no duplicates; the counting function finds `playlists` for `playlist` and does not find `skipping` for `skip`.
- [ ] Commit. Travis reads the list when he gives the go for the 100 gate (spec item 5).

### Task 7: Splitter, Jev request and answer mapping (pure code)

**Files:** Create `pipeline/splitter.py`, `pipeline/jev.py` (builder and parser only), `prompts/enrich-v1.json`, `tests/test_splitter.py`, `tests/test_jev_mapping.py`.

**Interfaces, produces:**
- `splitter.pieces(text: str) -> list[str]` (each piece an exact substring; ported from `pieces()` in `experiments/2026-10-04/tool-choice/jev_spike.py`)
- `jev.build_request(text: str, prompt: dict) -> dict` (questions `topic`, `intent`, `severity`, `tone`, plus `quote` when there is more than one piece; option order shuffled repeatably from the text)
- `jev.to_record(text: str, answer: dict, *, features: list[str], cutoff: float, label_config: str) -> dict` (raises `labels.InvalidAnswer`)
- `jev.entities(text: str, features: list[str]) -> list[str]` (whole lowercase words found in the text)
- `jev.MODEL = "jev-1.13.0"`
- `jev.Reply` (`answer: dict`, `model: str`, `input_tokens: int | None`, `output_tokens: int | None`, `http_status: int`, `request_id: str | None`), and the errors `jev.Temporary`, `jev.Fatal` and `jev.TooLarge`

- [ ] Tests: every piece of every `cost_100.csv` text is an exact substring and no review gives more than 39 pieces; the same text always builds the same request and two texts get different option orders; replaying the 100 saved answers in `experiments/2026-10-04/tool-choice/simple.jsonl` through `to_record` gives 100 records that pass `labels.validate`, with the topic, intent and severity the probe recorded (known answers from `score_spike.py`); `needs_review` is true exactly when the lowest of the three top probabilities is under the cut-off; a one-piece text quotes the whole text with outer whitespace removed; an answer with tone 7 or an unknown choice raises; a request over Jev's documented limits (255 options, or 32,000 tokens estimated as bytes divided by 2.4) raises `jev.TooLarge`.
- [ ] Review Focus 2: an emoji-only text and the literal `None` build a request and map to a valid record.
- [ ] Run, implement, run. Commit.

### Task 8: Stand-in Jev and the limiter

**Files:** Create `pipeline/standins.py`, `pipeline/limits.py`, `tests/test_limits.py`.

**Interfaces, produces:**
- A labeler is any object with `label(text: str, request: dict) -> jev.Reply`. It returns a reply or raises `jev.Temporary` or `jev.Fatal`.
- `standins.ReplayJev(path, *, script: dict | None = None)` replays saved answers by text and falls back to a fixed rule for unseen text; `script` makes named texts raise `Temporary`, return a wrong model, or return an invalid answer a set number of times.
- `limits.Limiter(requests_per_second=75, tokens_per_second=100_000, clock=time.monotonic, sleep=time.sleep)` with `acquire(body_bytes: int)` and `on_429()`; tokens are estimated as bytes divided by 2.4; after a 429 the rate halves at most once per 10 seconds and climbs back.

- [ ] Tests with an injected clock: 150 acquires at 75 per second take about 2 simulated seconds; a large body is held by the token limit; two `on_429()` calls inside 10 seconds halve the rate once; the rate recovers.
- [ ] Run, implement, run. Commit.

### Task 9: The classify loop

**Files:** Create `pipeline/classify.py`, `tests/test_classify.py`.

**Interfaces, consumes:** Tasks 2 to 8. **Produces:**
- `classify.run(db, run, labeler, *, ledger, limiter, workers=1, max_hours=None, stop_after=None, clock=time.monotonic, stop_event=None) -> classify.Outcome` where `Outcome.ended_how` is one of `finished`, `time_box`, `stop_after`, `interrupted`, `cap`, `fatal`, `no_success_60s`, `stuck` and `Outcome.completed`, `Outcome.pending`, `Outcome.quarantined` are counts.

Rules (spec 6.1): originals are taken in run order; one writer thread owns the database and the queue to it is bounded; a temporary error is retried up to 4 times with growing delays and jitter, then the review returns to `pending`; an invalid answer is retried once, then quarantined as `invalid_model_output`; a fatal response or a wrong `model` halts and changes no status; stopping means admit no new work, let in-flight requests finish, save. `stuck` is reported when only reviews that have already failed a full round remain.

- [ ] Tests with `ReplayJev`: 30 synthetic reviews with copies all complete and every copy is completed with its original; a scripted temporary error is retried and succeeds; four in a row return the review to `pending` and never quarantine it; a scripted invalid answer twice quarantines with `invalid_model_output` and its copies follow; a wrong model halts with no status changed; a text that raises `jev.TooLarge` is quarantined with reason `request_over_limit` and is never sent; `stop_after=10` ends with at least 10 new completions and work pending, and a second `run` finishes without sending any completed text again (assert on the stand-in's call log); the cap stops admission before the request that would pass it; 16 workers give the same final labels as 1.
- [ ] Review Focus 4: an injected clock jumps 2 hours while requests are in flight; they time out, the session ends as `no_success_60s`, nothing completed is lost, and the next `run` finishes.
- [ ] Guard tests, one planted failure each (spec section 10, item 25): over 500 stand-in reviews, a labeler that gives one topic to more than 95% raises; `needs_review` all true or all false raises.
- [ ] Crash test: a subprocess is killed mid-run with `SIGKILL`; on restart `recover_orphans` runs first, the ledger shows the kept reservations, and the run finishes with no completed ID sent twice.
- [ ] Run, implement, run. Commit.

### Task 10: Jev HTTP client

**Files:** Extend `pipeline/jev.py`, create `tests/test_jev_client.py`.

**Interfaces, produces:** `jev.Client(api_key, *, url="https://api.typesafe.ai/v1/systemone", timeout=30)` with the labeler interface of Task 8. Status 429, 5xx, timeouts and network errors raise `jev.Temporary`; 401, 402 and 403 raise `jev.Fatal`. The key is read from `TYPESAFE_API_KEY` by the CLI and is never logged; error text is stored with any key removed.

- [ ] Tests against a local `http.server` thread, no network: a good response becomes a `Reply` with usage; each status maps to the right error class; a slow response times out as `Temporary`; a response whose error body echoes the Authorization header is stored with the key removed.
- [ ] Run, implement, run. Commit. **No real Jev call is made in this task.**

## Phase 3: verify, group, rank, memo

### Task 11: Gemma client

**Files:** Create `pipeline/gemma.py`, `tests/test_gemma.py`. Extend `pipeline/standins.py` with `StandinGemma`.

**Interfaces, produces:**
- `gemma.Client(base_url="http://localhost:1234/v1", model=..., timeout=120)` with `check() -> None` (raises `gemma.ServerProblem` if the server does not answer or the expected model is not loaded) and `ask(system: str, user: str, schema: dict) -> gemma.Reply` (`data: dict`, `model: str`, `input_tokens`, `output_tokens`).
- Token counts are `None` when the server reports no usage; the call is then saved with `usage_known` 0.
- Every call sends `temperature` 0, `reasoning_effort` `"none"` and a `json_schema` response format. A response naming another model raises `ServerProblem`. Returned strings are checked for leaked template tokens and raise `gemma.InvalidOutput`.

- [ ] Tests against a local `http.server` thread: the request body carries the three settings; a wrong model in the model list fails `check()`; a wrong `model` on a response raises `ServerProblem`; a string containing a template token raises `InvalidOutput`; a refused connection raises `ServerProblem`.
- [ ] Run, implement, run. Commit. **No real Gemma call is made in this task.**

### Task 12: Verify

**Files:** Create `pipeline/verify.py`, `prompts/verify-v1.md`, `tests/test_verify.py`, `evals/compare_check.py`.

**Interfaces, produces:** `verify.run(db, run, client, *, max_hours=None, max_chars=20_000) -> verify.Outcome` and `verify.report(db, run) -> dict` (four counts: sample size, predictions, verify failures, sampled reviews Jev could not label; agreement per field and the confusion table on pairs where both answered, split by complaints and cancellations against the rest and per topic; the sample ranked on Gemma's labels beside Jev's; the disagreeing IDs with both answers).

`prompts/verify-v1.md` carries the contract's label section word for word, taken at build time by the same function the outside raters used, with its hash recorded.

- [ ] Tests with `StandinGemma`: the request for a review is byte-identical whether or not Jev's result exists (the blind test of item 25); every sampled review ends with a prediction or a recorded failure; an invalid answer is retried once and then recorded as `failed`; a `ServerProblem` halts the stage and records no failure; agreement of exactly 100% on 50 or more reviews raises; `compare_check.py` changes labels in a copy of saved results and the comparison flags each one.
- [ ] Review Focus 5: a review over `max_chars` is recorded as a verify failure with reason `too_long` and is not sent.
- [ ] Run, implement, run. Commit.

### Task 13: Group, rank, memo

**Files:** Create `pipeline/group.py`, `pipeline/rank.py`, `pipeline/memo.py`, `prompts/group-v1.md`, `prompts/memo-v1.md`, `tests/test_group.py`, `tests/test_rank.py`, `tests/test_memo.py`.

**Interfaces, produces:**
- `group.assign(db, run) -> int` (every completed `complaint` or `cancellation` review joins `issue-<topic>`)
- `group.name_issues(db, run, client, *, quotes_per_issue=30) -> None` (quotes picked by `sample_seed` among the issue's originals; cached in `artifacts` by input, model, settings and prompt version; falls back to the topic name and the contract's definition after one retry)
- `rank.rank(records: Iterable[dict], membership: Iterable[tuple[str, str]]) -> list[dict[str, str]]` (pure; every value a string in export form)
- `rank.from_files(grading_dir) -> None` (rewrites `ranking.csv` from `records.jsonl` or its gzip and `membership.csv`; no state file, no model)
- `memo.claims(ranking) -> list[dict]`, `memo.evidence_pack(db, run, *, per_issue=5) -> dict`, `memo.write(db, run, client) -> str`, `memo.check(text: str, pack: dict) -> list[str]` (the list of problems; empty means it passes)

- [ ] Rank tests: the ranking equals the checker's `calculated_ranking` on a synthetic run, string for string; a mean of `2.0000005` rounds half-up to `2.000001`; ties order by issue ID; a member missing from the records, or one that is not a complaint or cancellation, raises; `from_files` run twice in a clean copy gives byte-identical files.
- [ ] Group tests: no praise, request or unclear review is a member; each complaint is in exactly one issue; a warm call with the same inputs makes no new request; an input with no complaints makes no naming call and says so.
- [ ] Memo tests: a memo citing an unknown issue ID, review ID or claim ID fails the check; a number beside a claim ID that differs from the claim fails; a claim ID and its issue ID must share a sentence; a recommendation that names neither rank 1 nor a reason fails; a revenue or churn figure fails; a quote containing an instruction is passed as quoted data and the memo still checks; one retry carries the listed errors.
- [ ] Run, implement, run. Commit.

## Phase 4: export and the whole run

### Task 14: Export

**Files:** Create `pipeline/export.py`, `tests/test_export.py`.

**Interfaces, produces:** `export.export(db, run, out_dir, *, checker_path, input_path, gzip_large=True, evidence_dir=None) -> dict` (the checker's status and flags). It refuses while any review is `pending`, writes every file in "Export rules" above, runs the supplied checker's `profile`, `reference` and `check` as subprocesses, keeps `local-reference.json` and `self-check.json` outside `out_dir`, and prints the status and every flag. With `evidence_dir` it also writes the run manifest, `run_log.jsonl`, `run_summary.json`, `quarantine.jsonl`, every verifier prediction, each group and memo input and output, and `memo.md`.

- [ ] Tests on a synthetic run driven through the real stages with stand-ins and one stop: the checker returns `pass` with no flags and coverage 1.0; the boundary is the first session that left an original unlabeled; a run with no stop is reported as having no boundary before the checker runs; a failed call exports zeros and `usage_known: false`; a run where one nonempty review is quarantined exports and reports `review_required`; both forms of a JSONL file never coexist; a file over the size limit set for the test is named as needing a release asset.
- [ ] Mutation tests, one per flag the checker can raise on our files: break one thing in a good export (a copy with a different label, a quarantined ID in a checkpoint, a `resume` call naming a `before` ID, a decimal token count, a mean with five decimals) and assert the named flag appears. This proves the test would notice a regression.
- [ ] Run, implement, run. Commit.

### Task 15: CLI and the end-to-end test

**Files:** Create `pipeline/cli.py`, `pipeline/__main__.py`, `tests/test_end_to_end.py`, `.env.example` check.

**Interfaces, produces:** the commands in spec section 11, plus `status` and `quarantine-stuck`:

```sh
python3 -m pipeline run --run NAME --new --input PATH.csv [--stop-after N] [--max-hours H] [--workers N] [--cutoff X] [--warm-from RUN] [--standin] [--go]
python3 -m pipeline run --run NAME [--allow-commit SHA]
python3 -m pipeline status --run NAME
python3 -m pipeline quarantine-stuck --run NAME --reason api_failure_after_retries --yes
python3 -m pipeline export --run NAME
python3 -m pipeline rank
```

`run` executes the stages in order and stops at the first one that does not finish. At `--new` it builds `label_config` as `jev-1.13.0/prompt-v1/schema-v1/cut-0.70` from the model, the prompt and schema versions and `--cutoff`. `--warm-from RUN` is the cost pilot's warm pass (spec section 8): the new run takes its results from a finished run with identical hashes, makes no call of any role, and saves a record saying so. Ctrl-C sets the stop event: no new work, in-flight requests finish, everything is saved. `--standin` wires the stand-ins and is the only way a test or a dry run starts a stage; without it a real client is built and the command prints what it is about to spend and asks for `--go`.

- [ ] End-to-end test: a 60-row synthetic CSV with empties, copies and awkward text runs with `--standin --stop-after 20`, resumes with the same command, exports, and the checker returns `pass`. A second run of `rank` leaves `ranking.csv` byte-identical.
- [ ] Interrupted-run test: `SIGINT` mid-run, then resume; the checker passes and the stand-in's log shows no completed ID sent twice.
- [ ] Warm-pass test: a warm run from a finished stand-in run leaves every stand-in's call log empty and writes the zero-calls record; `--warm-from` is refused when any hash differs.
- [ ] Refusal tests: a real run without `--go` prints what it would spend and starts nothing; resuming after editing a prompt file is refused and names the file; a second process on the same state file is refused (Review Focus 3); `quarantine-stuck` without `--yes` changes nothing.
- [ ] Clean-clone test: in a fresh copy of the repo with no `.env`, `rank` and the test suite both work.
- [ ] Run, implement, run. Commit.

## Phase 5: cost calculator

### Task 16: Calculator

**Files:** Create `cost/calc.py`, `cost/__main__.py`, `cost/local_compute.csv`, `cost/README.md`, `tests/test_cost.py`.

**Interfaces, produces:**
- `calc.measured(calls: list[dict], rates: list[dict], sessions: list[dict]) -> dict` (per stage: requests, attempts, tokens, cost, seconds from the session clock; cold and warm apart)
- `calc.project(measured: dict, *, rows=660_622, nonempty=660_609, distinct=484_189, verify=5_000, issues=8, text_volume: dict, retry_rate: float) -> dict` (each stage from its own work count; the memo added once; a base and a conservative case; a warning when a case passes the cap)
- `python3 -m cost replay` (default; reads only `pilot_calls.jsonl`, `usage.csv`, `rates.csv`, `local_compute.csv`) and `python3 -m cost pilot --go` (paid; refuses without `--go`)

- [ ] Tests on made-up pilot files: doubling every API rate doubles the API subtotal and leaves local cost and measured time unchanged; changing the projected row count leaves the measured results unchanged; costs are not rounded before either test; replay never opens the state file and never imports a client (assert on `sys.modules`); a report with zero tokens raises; API spend, local compute and unknown costs are three separate totals and an unknown stays marked unknown.
- [ ] Run, implement, run. Commit.

## Phase 6: evaluation tools and the gate runbook

### Task 17: Evaluation scripts

**Files:** Create `evals/planted_cases.py`, `evals/wording_trial.py`, `evals/cutoff_table.py`, `evals/score_golden.py`, `tests/test_evals.py`.

- `planted_cases.py`: the 25 cases from `experiments/2026-10-04/tool-choice/three_tests.py`, moved here with their expected answers, run through a labeler and scored.
- `wording_trial.py`: runs candidate intent wordings over the planted slogan cases and the boycott `tune` half only; refuses to read a `holdout` row; paid, so it needs `--go`.
- `cutoff_table.py`: for each candidate cut-off on the cut-off half, the count flagged and the differences caught, against every reference side by side (the raters' shared label, Travis's label as written, Travis's with `labels.by_rule`), with the rater-disputed rows as a group of their own (spec item 4).
- `score_golden.py`: the report in spec section 10, both readings (item 32). It prints counts and row IDs of disagreements only, and refuses to run twice on one run unless told.

- [ ] Tests on made-up labels: `cutoff_table` reproduces the four rows of the 2026-10-04 table in `CLAUDE.md` from the saved pilot answers (known answer); `score_golden` gives the built-in counts on a made-up golden file and its second reading changes only rows whose intent is `unclear`, `praise` or `request`; `wording_trial` raises on a `holdout` row.
- [ ] Run, implement, run. Commit.

### Task 18: README and submission checks

**Files:** Create `README.md`, `runs/README.md`, `evals/README.md`.

- [ ] Write the sections in spec section 9 ("README and submission checks"), each rubric point linked to its evidence, with measured values kept apart from estimates and every count of calls with unknown usage stated.
- [ ] Check: `git ls-files -- .env '.env.*'` shows only `.env.example`; every evidence link resolves in a clean clone.
- [ ] Commit.

## Gates (each needs Travis's go; pass marks are shown with the request)

The marks below are proposed under the delegation of 2026-10-05. Travis confirms or changes them when each go is asked for. Any mark missed blocks the next go.

| Gate | What runs | Pass marks |
|---|---|---|
| Wording trial | The probe's intent wording and each candidate on the 4 planted slogans and the 30 boycott `tune` reviews; the usage page read before and after | Planted slogans: at least 3 of 4 `unclear` (2 of 4 with the probe wording). `tune` half: the chosen wording's intent equals the raters' shared answer on at least as many rows as the probe wording's. The usage page is compared with input tokens times the rate; that settles whether output tokens are billed, and `rates.csv` is set to match before the 100 gate |
| 100 | `cost_100.csv`, one worker, all six stages, stopped once with `--stop-after 50`, then a warm pass | 100 of 100 completed, none quarantined; checker `pass`; warm pass makes 0 calls; every response names `jev-1.13.0`; Jev spend under $0.01 (measured $0.0039 on the probe); both calculator tests pass; Travis has read the feature list and the memo and named a provisional cut-off |
| 500 | `checkpoint_500.csv`, up to 16 workers | 500 of 500 completed; checker `pass`; the nested 100 keep their labels; 429 responses under 1% of requests; cost per review within 20% of the 100 gate |
| 10,000 | `analysis_10000.csv` | All completed; checker `pass`; the nested 500 keep their labels; sustained speed at least 50 per second with no fatal response; temporary failures under 1% of attempts; spend so far plus the projected full pass under $24 |
| Full run | The full file, stopped once by hand on camera, then resumed | Wording and cut-off frozen first; usage page reconciled; checker `pass` with coverage 1.0, or the shortfall reported |

After the full run: `score_golden.py` once, the calculator refreshed, the README, the reread for anything personal, and the repo made public.

## Self-review

- **Spec coverage:** sections 4 (Tasks 2, 5), 5 (Task 3), 6.1 (Tasks 6 to 10), 6.2 (Tasks 11, 12), 6.3 to 6.6 (Task 13), 7 (Tasks 5, 8), 8 (Task 16), 9 (Tasks 14, 15, 18), 10 (tests in every task, Task 17), 11 (Task 15). Section 12 items with their own work: 5 (Task 6), 7 (the `stuck` outcome and `quarantine-stuck`), 18 (`--stop-after` and Ctrl-C), 25 (the blind request test, the planted failure per guard, the nested labels at each gate), 28 (the gate table), 32 (`score_golden.py`).
- **Not covered by a task, on purpose:** sub-issues (spec 6.4, not built in this version); a second business ranking.
- **Open at build time:** the bands of item 25 are fixed at each gate from the gate before; the first gate uses the fixed thresholds in spec section 10.
