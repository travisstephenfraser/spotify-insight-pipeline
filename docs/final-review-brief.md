# Final review brief

Hand a fresh reviewer this one file. It holds everything the reviewer needs from the people who built the project. Written 2026-10-07.

**For whoever starts the review** (the reviewer may read this too):

- Use a model from a different maker than the builder's. The project was built with Claude.
- Push first. The reviewer sees only what is on GitHub, so name the branch or commit you want reviewed.
- Run it in a fresh clone, never in the working folder. The working folder holds `.env`, the state file with the spend ledger, and session notes.
- If you can, put the 97 MB source CSV in place for it. Without that file the instructor's checker cannot be run on the real export.
- Give it nothing else: no handoff, no summary, no list of worries. A reviewer handed a suspicion tends to return it confirmed.
- When the report is back, compare it with `docs/validation-log.md`. A problem found by both is close to certain. A problem found only by the reviewer is why the review was worth running. Record the comparison as a new validation log entry.

---

## Instructions for the reviewer

### Your job

You are the outside check on a finished course project before it is graded. Take the grader's seat: you have the public repository, the assignment and the instructor's checker, and nothing else.

The project is a pipeline that labels 660,622 Spotify app reviews with a classifier, has a second model re-label a sample blind, groups complaints into issues, ranks them in code, and has a model write a short decision memo. It is graded from the repository's README, a `grading/` folder and a `cost/` folder.

You have no stake in it. A finding that something is wrong, missing or overstated is a successful review. So is a claim you checked and found true, when you can show how you checked it. Do not soften findings and do not pad the report with praise.

### Why you are given so little

The builders kept a long record of their own decisions, checks and known weaknesses. You are not given it at the start, on purpose, so that your findings are your own. You open it in the last pass only.

- Report whatever you find, even if you suspect the builders already know it. Overlap is useful.
- Take every claim from the README and the saved files, never from this brief. This brief quotes no result on purpose.
- If your tool loaded `CLAUDE.md` or any other instruction file from the repository by itself, say so at the top of your report and set its contents aside. It is the builders' account, not evidence.

### Setup

```sh
git clone https://github.com/travisstephenfraser/spotify-insight-pipeline.git
cd spotify-insight-pipeline
git rev-parse HEAD        # goes in your report
python3 --version         # the README says which version it needs
```

Review the default branch unless you were given a branch or commit.

The full source file is not in the repository. The README's Local setup section says where to get it and where it goes. If you can get it, check its SHA-256 against the README and `manifest.json` before using it. If you cannot, say so; every check below marked **[full file]** then goes under "Could not check".

If you cannot run commands at all, say so at the top and do each pass by reading. Mark every command-based check as not run. Do not guess its result.

### What to read first

Primary sources. The project must satisfy these. Read them yourself.

| File | What it is |
|---|---|
| `feed/Final Assignment - Multi Agent Large Data Processing Pipeline.md` | The assignment and its 10-point rubric. **Read lines 1 to 225 only.** The rest is image data |
| `feed/Final Assignment - Spotify Reviews Dataset/GRADING_CONTRACT.md` | Label definitions, tie-break rules and the required export format |
| `feed/Final Assignment - Spotify Reviews Dataset/check_submission.py` | The instructor's checker. Read all of `audit()`. Every `flag(...)` call is a way to fail |
| `feed/Final Assignment - Spotify Reviews Dataset/COST_CALCULATOR.md` | Requirements for the cost calculator |
| `feed/Final Assignment - Spotify Reviews Dataset/manifest.json` | Dataset counts, checksums and sampling method |

Then the submission itself: `README.md`, `grading/`, `cost/`, `runs/`, `evals/`, `prompts/`, `pipeline/`, `tests/`. Treat every number and every sentence in the README as a claim to check.

### Hold these until Pass 6

They are the builders' own account. Opening them early turns your review into a reading of theirs.

| Path | What it is |
|---|---|
| `CLAUDE.md` | The builders' decision log, with their conclusions |
| `docs/` (everything except this file) | Their validation log, earlier reviews, rulings, the design and the plan |
| `evals/golden_error_analysis.md` | Their reading of the cases the classifier got wrong |
| `experiments/**/README.md` | Their index of early probes. The scripts and saved outputs beside it may be read at any time |
| The README section "Known limitations and what I would do next" | Their list of weaknesses. Skip it until Pass 5 asks for it |

Never open `.env`. A fresh clone has none; if you find one, stop and say so.

### Hard rules

- **No paid call and no model call.** Do not run anything with `--go`. Do not contact `api.typesafe.ai`, `api.anthropic.com`, `api.openai.com` or `localhost:1234`. The only network use allowed is cloning from GitHub, downloading the dataset, and checking that links answer.
- **Stand-ins only.** The pipeline has a `--standin` mode that replays saved answers and costs nothing. Use it for any run you make.
- **The clone is yours to run commands in, and it must end clean.** Do not commit, push, open a pull request or file an issue. Anything that edits a file, such as a changed price or a deliberately broken check, is done in a scratch copy outside the clone.
- **Do not fix anything.** Name the smallest change that would close a finding and leave it to the owner.
- **Your own labels are an opinion.** Where you label reviews yourself, report agreement, never accuracy.

### How to review

Make six passes, in order. Report each under its own heading. Finish one before starting the next, so one line of thought does not crowd out the others.

**Pass 1. Does it reproduce?** Follow the README's Local setup exactly as written, as a stranger would. Then:

- Run the test suite. Report the count, the skips and any failure, and compare the count with what the README states.
- Run the ranking command on `grading/`. It should rebuild `ranking.csv` to the same bytes; hash the file before and after.
- Run the offline cost replay. Then, in a scratch copy of `cost/`, do the instructor's two tests by hand: double an API rate and confirm the API subtotal doubles while local cost and measured time do not move; change the projected row count and confirm the measured 100-review results do not move.
- Run the README's stand-in walkthrough end to end, including the stop, the resume and the export.
- Build a small made-up CSV of your own with awkward rows (empty text, repeated text, a multi-line review, emoji only, the literal text `None`), run it through the stand-in pipeline with one stop and resume, export it, and run the checker on the export. Report every flag.
- **[full file]** Run the contract's three checker commands (`profile`, `reference`, `check`) on `grading/`. Report the status and every flag. Compare your `profile` output with `grading/ingestion.json`.
- Finish with `git status --short`. Replay and ranking claim to be exact, so a diff here is a finding.

**Pass 2. Do the README's numbers hold?** Recompute them with your own code from the saved files. The repository's own scripts may be run to see what they print, but a number counts as checked only when your code or the instructor's checker produced it. Cover at least these families, and every number in the README's full-file results column and in the memo:

- Record accounting: rows, completed, quarantined and why, exact-text reuse and whether each reuse is valid.
- Calls: how many, how many reviews per request, unique request IDs, failed attempts and what became of each, initial against resume, models named.
- The stop and resume: what the two checkpoint files hold, and whether any resumed request names a review finished before the stop.
- The verifier: sample size, failures, agreement on all three fields, and the split between complaints and the rest.
- Ranking and claims: rebuild every issue's count, severity sum, mean and order from the records and the membership; compare with `ranking.csv`, `claims.csv` and each number and ID in the memo.
- The golden set: rebuild the per-field agreement, the severity error and the confusion tables from the hand labels and the saved predictions.
- Runs against each other: reviews labeled in both the 10,000-review run and the full run, and how many changed.
- Cost and time: tokens times rates for the full run and the pilot, against what the README and `cost/report.md` state; request counts against session lengths and the stated rate limit.

For each number report: the claim, where the README makes it, what you computed, and whether it matches. For each family, name one way the number could be wrong and still look right, and say whether you ruled it out.

**Pass 3. Are the labels any good?** `feed/Final Assignment - Spotify Reviews Dataset/analysis_10000.csv` is in the repository with the review texts, and every one of its reviews was labeled in the full run.

- Pick 60 of its reviews by a seeded rule you state, so anyone can pick the same 60. Label each yourself for topic, intent and severity from `GRADING_CONTRACT.md`. Write your labels down **before** you open the pipeline's labels for those reviews.
- Then pick 20 more by the same kind of rule from reviews the pipeline called a complaint or cancellation at severity 4 or 5. Have your script print their IDs only, so you label them blind as well. Severity is what the ranking adds up.
- Compare field by field. Where you differ, quote the contract line that decides it, or say that the contract leaves it open. Read each evidence quote and say whether it supports the label it sits beside.
- Read the golden reviews where the classifier and the hand labels differ (`evals/golden_50_labeled.csv` against the saved predictions), and sort them yourself: classifier wrong, hand label wrong, or open under the contract.

**Pass 4. Can its measurements be trusted?** List each thing the project measures or uses as a guard: the golden score, the verifier's agreement, the review flag, the planted-error and injection tests, the checks that stop a bad run, the spending cap, the tests themselves. For each one ask:

- Who or what produces the measurement, and is it independent of the thing measured? Shared model, shared wording, shared author and earlier sight of the answer all count against independence.
- Does the measurer see the same evidence the measured thing saw?
- Which direction of failure would look like success?
- Is the sample large enough for the sentence the README builds on it?
- Was any labeled set used for more than one decision?

Then check what the code and the history can show:

- Read the verifier's code and prompt. Is its request truly blind to the first label?
- Can the hand labels reach a prompt, an example, a threshold or the grouping? Search for it.
- Does `git log` bear out the order the README claims: labels frozen, then predictions, then the score?
- Pick three guards the README leans on and break each in a scratch copy. Does a test fail? A test that cannot fail proves nothing.
- The checker says its pass does not prove a model was ever called. Look for anything in the saved calls, timings and usage that is inconsistent with a real run, and say what you looked at.

Close this pass by writing your own list of the five limits that matter most for anyone acting on the ranking.

**Pass 5. Does the README earn each rubric point, and does the memo's argument hold?**

- For each of the ten rubric points, open every file the README's rubric map links for it. Score it 1, 0.5 or 0 by the assignment's own scale (complete, materially incomplete, absent or contradictory), with one line of reason. Where the map links into the hold list, score that part as it stands without the link and revisit it in Pass 6.
- Go through the assignment's "Evidence Required in the README", "Submission Checklist" and "Definition of Done" item by item: met, partly met, or missing.
- Look for contradiction. Do `README.md`, `cost/README.md`, `evals/README.md`, `runs/README.md` and the memo ever say different things about the same fact? Does any sentence describe a state that is no longer true?
- Read the memo as the person who has to act on it. Does the recommendation follow from the numbers? Are the alternatives treated fairly? Does it claim anything the data cannot support, such as revenue, churn or cause? Would another defensible reading of the same ranking change the recommendation?
- Now read the README's "Known limitations" section and set it beside your own five. What did they leave out or soften? What did you miss?
- Publishing: search the tree and the history for anything shaped like a key, for personal details that need not be public, and for links that do not answer signed out. Note the license.

**Pass 6. Open the builders' account.** Now read `CLAUDE.md`, `docs/validation-log.md`, `evals/golden_error_analysis.md` and whatever else in the hold list bears on your findings.

- Where does their record contradict the README, or contradict what you measured?
- Which weaknesses does their record state that the README omits or softens?
- Which of your findings had they already recorded? Mark those "also in their log" and keep them in the report.
- Did reading it change any finding? Say which and why. Do not quietly drop one.

### Evidence standard

- Every finding needs evidence: a quoted line with its path and line number, a command with its output, or a number you computed from a named file.
- The same holds for a claim that something is right. "Verified" with nothing behind it is not a result.
- Do not confirm or refute from general knowledge. A concern you cannot back goes in a separate list headed "Unverified concerns".
- Before you call something a Blocker, try to knock it down yourself, and say what you tried.

### What to hand back

Give the report as your final message, in Markdown. Do not write it into the repository. Keep it under about 2,500 words; tables are welcome.

1. One header block: which model and tool you are, whether any instruction file loaded by itself, the commit you reviewed, your Python version, whether you had the full file, and whether you opened anything on the hold list before Pass 6.
2. The rubric table: ten rows, each with a score, the reason, the strongest evidence and what would raise it.
3. Findings, most severe first. For each: a one-line claim, a severity, the evidence, what you did to try to refute it, and the smallest change that would close it.
   - **Blocker:** the checker would flag the export, a rubric point would be lost or contradicted, a number in the README or memo is wrong or misleading, or something private is exposed.
   - **Should fix:** a real weakness with a workable way around it.
   - **Note:** worth knowing, low cost either way.
4. The numbers you checked in Pass 2, as a table: claim, source, your value, match or not.
5. Your label read from Pass 3: the sampling rule, the counts per field, and the differences with the contract line for each.
6. Your five limits beside the README's.
7. What Pass 6 turned up.
8. "Unverified concerns".
9. "Could not check", with the reason for each.
10. The output of `git status --short` at the end.

No summary of the project and no closing praise. Stop after the report.
