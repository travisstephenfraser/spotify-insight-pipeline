# Jev 1.14 canary, 2026-10-15

Validation log entry 44. Run on 2026-10-15 with Travis's go, and added to the repo the same day, after the deadline moved to 2026-10-20.

**The question.** TypeSafe released `jev-1.14.0` on 2026-10-14 and will move the `jev-latest` alias to it about a week later. The pipeline pins `jev-1.13.0`, so nothing here changed by itself. Before a pin moves, two things need an answer: does the new version label these reviews differently, by more than a version differs from itself on a rerun, and is it better?

**The answer.** It labels differently and is not measurably better. The pin stays at 1.13.

## What was sent

The same request for every text, built by the pipeline's own `build_request` with the frozen wording `prompts/enrich-v2.json`; only the `model` field differs. Three arms per text, sent in one shuffled order at 40 requests a second so that time of day cannot pass for a model effect:

| Arm | Model | What it measures |
|---|---|---|
| `s13` | `jev-1.13.0`, the stored label from the full run of 2026-10-06 | |
| `a13` | `jev-1.13.0`, sent now | against `s13`: 1.13's own noise nine days on |
| `b14` | `jev-1.14.0` | against `a13`: the version change plus noise |
| `c14` | `jev-1.14.0`, sent again | against `b14`: 1.14's own noise |

2,508 texts: 2,000 distinct review texts picked by hash, 300 that a word list marks as not English (17 of 20 checked by eye were), and the texts of the golden 50, the development 150, the blind adjudication 39 and the boycott 60. The golden 50 is **not scored**: only its ID and text columns are used, because it is scored once (entry 36).

## Results

Share of texts where topic, intent or severity differs:

| Texts | 1.13 now vs stored 1.13 | 1.14 vs 1.14 again | **1.14 vs 1.13 now** |
|---|---|---|---|
| 2,000 random | 72 (3.6%) | 63 of 1,999 (3.2%) | **210 (10.5%)**: topic 98, intent 50, severity 91 |
| 300 not in English | 19 (6.3%) | 19 of 299 (6.4%) | **49 of 299 (16.4%)** |
| Golden 50 texts | 2 | 0 | 2 |
| Development 150 | 3 | 5 | 21 |
| Adjudication 39 | 0 of 38 | 1 | 6 |
| Boycott 60 | 0 | 1 | 4 |

So about 7 texts in 100 change because of the version, on top of the 3 or 4 that change on any rerun. A second 1.14 run (`c14`) moves 208 of 1,999 from 1.13 now, so the change is not one run's luck.

**Accuracy: no difference that 68 labels can show.** On the reusable hand labels (development 29, adjudication 39):

| All three fields right | As written | With the severity rule |
|---|---|---|
| 1.13 stored (67 of the 68 have a stored label) | 33 | 37 |
| 1.13 now | 33 | 37 |
| 1.14 | 35 | 39 |
| 1.14 again | 35 | 39 |

Topic 53 against 54, intent 59 against 58, severity with the rule 46 against 45 (1.13 now against 1.14). A gap of two on 68 is inside the noise above.

**Where 1.14 moves labels:**

- **Into `other`.** On the 2,000, `other` goes from 839 to 890: 57 texts move in, 6 move out, and 51 of the 57 are `other` again on the second 1.14 run. Billing loses 22 and playback 22. The guide sends general praise to `other`, and 1.14 gets some of those right ("It is amazing app the music are really good"). It also drops named specifics: "Not worth the price", "Won't work on samsung anymore", "I wish you could play music over chromecast". Of 18 read by the assistant, 1.14 is closer on 6, 1.13 on 8, neither on 4 ([`by_eye.md`](by_eye.md)).
- **Severity 4 down to 3:** on the 2,000, 19 texts go from 4 to 3 and 7 from 3 to 4, and severity 4 goes from 253 to 240. That is the direction the outside reader found for 1.13's 4s (entry 39), so it may be a correction, but nothing here measures it. The mean severity moves by only −0.014, because other steps go both ways.
- **Not in English:** 1.14 changes these most, and calls fewer of them `unclear` (62 of 300 for 1.13; 56 and 53 for the two 1.14 runs). TypeSafe says the largest gain is in multilingual text. Of 22 changed ones read by the assistant (Hindi, Hindi in Latin script, Arabic, Indonesian, Spanish, Portuguese, Malay), 1.14 is closer on 8, 1.13 on 7, neither on 7. Movement, not a measured gain.

**Less sure of itself.** The mean of the lowest top probability falls from 0.778 to 0.764 on the 2,000, so the review flag at the 0.70 cut-off would fire on 762 and 748 of them in the two 1.14 runs, against 717 for 1.13 now. The cut-off was chosen on 1.13 (entry 31); a move to 1.14 would need it chosen again.

**Same cost and speed.** 1,001.4 input tokens a request on both versions; median 0.14 s, 95th percentile 0.33 s, on both.

**Two refusals, both from 1.14.** HTTP 499 with `internal_error`, once in each 1.14 arm, on different texts; none in 2,508 calls to 1.13. `pipeline/jev.py` counts any 4xx but 429 as a refusal of that one request and does not send it again, so on 1.14 these would be reviews without a label rather than retries. Not changed here: the full run did not use 1.14.

## Checks on the measurement itself

Each one raises and stops the report; [`tests/test_canary.py`](../../../tests/test_canary.py) plants the failure for the first three and checks that it does.

1. **Every reply names the model that was asked for.** An alias or a silent fallback would make 1.14 look identical to 1.13, the failure that reads as success.
2. **1.13 now reproduces the stored run** within 6% (it was 3.6%; reruns so far changed 2.6% to 4%). Otherwise this script is not the pipeline, or 1.13 has moved, and no 1.14 figure means anything.
3. **The two versions are not one model under two names**: raw answers identical on 50 of 2,507 texts.
4. **The comparison counts planted flips**: seven topics changed in a copy are counted as seven, and a set against itself as none.
5. **No arm collapses onto one answer** on the 2,000.

## Spend, the ledger and the usage page

7,522 successful requests, 7,532,643 input and 1,635,245 output tokens, $0.3164 at $0.042 a million input tokens, 188 seconds. These calls did **not** go through the spend ledger: `evals/common.py` refuses any reply from a model other than `jev.MODEL`, by design, so the cap here was an estimate checked before sending (about $0.38 by bytes, under a $1 stop). The ledger still reads $21.0760; with this, $21.39 of the $35 cap.

Entry 41 predicted the next usage page reading as 495,250 requests and 602,576,401 tokens. With these calls it should read **502,772 requests and 611,744,289 tokens, about $21.11**, if the two refused attempts are not counted (the full run's failed ones were not) and nothing else has used the account since 2026-10-07.

## Limits

- One day, one wording. Another wording could move differently between versions.
- Accuracy rests on 68 hand labels from one labeler. The reads by eye are the assistant's, made on the first 110 or 150 characters and with its own translations; they are agreement with the assistant, not accuracy.
- The non-English set comes from a word list, about 17 in 20 right by eye.
- The images, `box` question and long context that came with 1.14 were not tried; none is used by this pipeline.

## Files

| File | What it is |
|---|---|
| `canary.py` | The script: plan, send, report. `--analyze` rebuilds `report.json` from the saved calls with no key |
| `calls.jsonl.gz` | Every call: arm, model sent and named in the reply, the raw answer, tokens, time, and the record `to_record` made from it |
| `items.json` | The 2,508 texts by review ID, with their sets and language bucket |
| `report.json` | Every figure above |
| `multilingual_diffs.json` | The 49 non-English texts 1.14 labels differently, with their text and all three arms |
| `by_eye.md` | The 40 changed labels read by the assistant |
