# Outside review, 2026-10-07

One review of the whole submission by a model from another maker, working from [`../final-review-brief.md`](../final-review-brief.md) in its own fresh clone. It made no paid or model call and changed nothing in the repo.

- **Reviewer:** OpenAI GPT-6-based Codex, desktop app.
- **Its report, as written:** [`independent-final-review.md`](independent-final-review.md).
- **What was done about it:** validation log entry 39, in [`../validation-log.md`](../validation-log.md).

## Read this first

**It reviewed `main` at commit `2caac91`, two commits behind the work it was meant to see.** The brief told it to clone the default branch, and the last two commits were still on an unmerged branch. So some of its findings describe things that already existed and that it could not see: the root `grading/` folder, the rubric map, the traced review, the golden error analysis, the corrected memo model and pilot status. Entry 39 sorts each finding into "already there", "true and fixed" and "true and still open".

One good came of it. The reviewer sorted the 20 golden misses without seeing the builders' own reading of them, because that file was not on `main`.

## The files

The links inside the report point at the reviewer's own temporary folders and no longer open. The files it names under `spotify-review-work/` are the ones here.

| File | What it holds |
|---|---|
| `numbers.json` | Its own recount of the README's figures |
| `blind60-source.json`, `blind60-labels.json` | 60 reviews picked by its own seed from the 10,000-review file, and the labels it gave them before opening the pipeline's |
| `high20-ids.json`, `high20-source.json`, `high20-labels.json` | 20 complaints and cancellations the pipeline rated 4 or 5, and its labels for them |
| `labels-comparison.json` | Its labels beside the pipeline's, and the 23 reviews where they differ |
| `quote-judgements.json` | Whether each of the 80 quotes supports its label |
| `golden-judgements.json` | Its sort of the 20 golden misses |
| `audit.json`, `self-check.json`, `local-reference.json`, `profile.json` | The supplied checker's output on its machine |
| `links.json`, `secret-scan.json`, `own-five-limits.json` | Its link checks, its scan of the history, and the five limits it wrote before reading the README's |

Its agreement figures are agreement with one reviewer's opinion, not accuracy.
