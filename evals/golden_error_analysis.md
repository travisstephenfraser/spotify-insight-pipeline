# The golden 50: the 20 reviews where Jev and the hand labels differ

The golden 50 was scored once, on the full run (validation log entry 36): topic 40 of 50, intent 43, severity exact 40, all three 30. This file reads the 20 reviews where at least one field differs. **Nothing here changes the score or a label.** The hand labels stay as frozen and 30 of 50 stands.

- Expected labels: [`golden_50_labeled.csv`](golden_50_labeled.csv). Predictions: [`runs/full/grading/records.jsonl.gz`](../runs/full/grading/records.jsonl.gz).
- Case by case, with pass or fail for each field: [`golden_cases_full.csv`](golden_cases_full.csv), written by [`golden_cases.py`](golden_cases.py), which refuses unless its totals equal the saved score.
- Counts and the three confusion tables: [`golden_score_full.json`](golden_score_full.json).

**Who read them.** The 20 were read by the AI assistant that built the pipeline, after the score was saved and with Travis's permission to open the label columns for this purpose. He gave it at about 23:57 on 2026-10-06, and this file was committed at 00:09 on 2026-10-07. The readings are that assistant's, set against the wording of `GRADING_CONTRACT.md`. They are one reading, not a second labeler. The three translations are the assistant's and approximate.

## The 20 by kind

| Kind | Reviews | What differs |
|---|---|---|
| Severity one step apart, topic and intent the same | 6 | Jev is one step higher on 5, one step lower on 1 |
| A topic boundary the contract draws | 6 | One also differs on severity |
| Text not in English | 3 | The hand label is `other`, `unclear`; Jev read the text |
| Boycott or political text | 3 | The hand label is `unclear`; Jev says complaint or cancellation |
| Short or doubtful praise | 2 | Intent |

Each review is given a reading:

- **Jev wrong:** the contract's wording supports the hand label. **3 reviews.**
- **Wording favors Jev:** the contract's own definition or example points at Jev's label. **4 reviews.**
- **Fallback label:** the hand label is the labeling guide's fallback for a language the labeler did not read. **3 reviews.**
- **Open:** the contract does not settle it, or the two labels sit on either side of a line it draws. **10 reviews.**

So 3 of the 50 are plain Jev errors by this reading and 30 of 50 are plain agreements. The other 17 are where the labels, the guide or the contract leave room. The instructor's private sample, which accepts several labels on ambiguous cases, is the better gauge of the middle.

## Case by case

Hand and Jev labels are written topic / intent / severity. "Flagged" means Jev's record carries `needs_review`.

### Severity one step apart

| Review | What it says | Hand | Jev | Reading |
|---|---|---|---|---|
| `947821dc` | A song plays briefly and stops; a phone update fixed it once, then it came back | playback / complaint / 4 | 3, flagged | Open. 3 is "some use or workaround remains", 4 is a blocked core task |
| `47f1406d` | "Cannot playback the songs" since recent updates | playback / complaint / 3 | 4 | Wording favors Jev. The contract's example of 4 is being unable to play music |
| `215463ae` | Could not play a song, reinstalled, now cannot open the app | playback / complaint / 3 | 4 | Wording favors Jev. Nothing works |
| `ac4e860a` | Pays for a plan and cannot play offline | downloads / complaint / 3 | 4 | Open. Offline is blocked; streaming remains |
| `16d640e9` | Basic features have become Premium | billing / complaint / 2 | 3 | Open. 2 is generic criticism, 3 a restricted function |
| `d2f3874f` | Too expensive, and the free version is "pretty much unusable" with ads | billing / complaint / 2 | 3 | Open. Same line as above |

### Topic boundaries

| Review | What it says | Hand | Jev | Reading |
|---|---|---|---|---|
| `3ddb3f4e` | Deleting the app: cannot pick songs or turn off shuffle, "pushing us to upgrade to Premium" | billing / cancellation / 3 | usability / cancellation / 3 | **Jev wrong.** "Explicitly premium-only controls go [to billing]." Jev quoted the sentence about controls and not the one about Premium |
| `dceb14e7` | After an update, cannot play chosen songs or rewind | usability / complaint / 3 | playback / complaint / 4, flagged | **Jev wrong** on both fields. The loss is of controls, and some use remains |
| `1fc8b08f` | Names a paid plan, then "No ads at all!" | other / praise / 1 | usability / praise / 1 | Wording favors Jev. A plan mention alone is not billing; the first specific praised feature is the absence of ads |
| `723f07de` | The app crashed on every open; an update says support fixed it | access / complaint / 4 | playback / complaint / 4 | Wording favors Jev. The contract lists crashes under playback, and access as login and account |
| `b5ee7834` | "Awesome and very diverse" | catalog / praise / 1 | other / praise / 1 | Open. General praise is `other`; whether "diverse" names the catalog is a judgment |
| `46c0b49f` | An ad plays far louder than the music | playback / complaint / 2 | usability / complaint / 2, flagged | Open. Audio quality is playback; ad interruptions are usability |

### Text not in English

The labeling guide says: translate if you can and say so in the notes; if it is still unclear, use `other`, `unclear`, severity 1 and flag it. All three rows carry the note "language".

| Review | Roughly | Hand | Jev | Reading |
|---|---|---|---|---|
| `46842184` | Indonesian: the lyrics are sometimes missing, how come | other / unclear / 1 | catalog / complaint / 3, flagged | Fallback label. Jev's label follows the meaning |
| `ac6cd66d` | Tagalog: all the songs are on Spotify | other / unclear / 1 | catalog / unclear / 1, flagged | Fallback label. Jev's topic follows the meaning; neither side reads it as the praise it seems to be |
| `372d4e67` | Hindi in Latin letters: please reduce the ads, there is one after every song | other / unclear / 2 | usability / request / 1, flagged | Fallback label. Jev's topic follows the meaning; complaint at severity 2 would fit the contract better than request |

### Boycott or political text

The contract: bare boycott slogans and unrelated text are `unclear`, unless there is a product complaint or an explicit personal departure. General "bad app" is a complaint.

| Review | What it says | Hand | Jev | Reading |
|---|---|---|---|---|
| `292ce26a` | Angry political text that says Spotify bans a kind of music | other / unclear / 2 | catalog / complaint / 2, flagged | Open. Whether "they ban these songs" is a product complaint is the question |
| `5de7f95b` | "We are boycotting" the app over a matter unrelated to it | other / unclear / 2 | other / cancellation / 2, flagged | Open. "We are boycotting" may or may not be an explicit departure. The holdout showed the same pattern (entry 26) |
| `8cc4fad4` | "I hate this app", then a political statement | other / unclear / 2 | other / complaint / 2 | Open. Half slogan, half general "bad app" |

All three hand severities are 2 on `unclear`, which the contract's severity rule makes 1. With `372d4e67` these are the four labels the second reading changes.

### Short or doubtful praise

| Review | What it says | Hand | Jev | Reading |
|---|---|---|---|---|
| `fc344263` | "Great..." | other / praise / 1 | other / unclear / 1, flagged | **Jev wrong.** The same weakness as the emoji-only planted cases (entry 26) |
| `2aa566c6` | "Nice app, very less advertising" | usability / complaint / 2 | usability / praise / 1 | Open. The labeler's own note asks whether it is a complaint or praise |

## What the misses say about the ranking

- **Severity leans high at the line between 3 and 4.** Where the two differ by one step on a functional complaint, Jev is higher on 5 of 6. The contract's example supports Jev on 2 of the 5, so part of this is the hand labels being cautious. Either way, severity sums built on Jev's labels sit above what these hand labels would give.
- **Controls behind the paywall can land in usability.** The contract sends premium-only controls to billing. Jev put one such review (`3ddb3f4e`) in usability. In the full run, 9,403 of the 81,756 usability complaints name Premium, and 3,000 name Premium or a subscription together with shuffle, skip, queue or repeat. Counted by code as a what-if, with no label changed: if all 9,403 were billing, usability would still rank first (186,455 against `other`'s 175,815) and billing would pass playback for third. Moving only the 3,000 gives the same order. **First place does not depend on this boundary. Places 3 and 4 do.**
- **Boycott text reads as complaint or cancellation.** Jev did so on all 3 here and on 4 of 28 in the holdout. These land in `other`, which helps explain why `other` holds the most complaints at the lowest mean severity.
- **Unclear by hand, labeled by Jev.** Of the 9 reviews labeled `unclear` by hand, Jev called 4 a complaint or cancellation: the three boycott reviews and one in a language the labeler did not read.

## The other fields

- **Quote.** 50 of 50 are exact copies of the review's text. On 38 the quote is the whole review, because the review is one sentence. On the other 12 Jev chose one sentence; 11 carry the point of Jev's label. One (`b58dd6f0`) is cut mid-sentence, because the review has a line break inside a sentence and the splitter treats every line break as a boundary. In the full file 68 reviews hold a line break and 51 quotes are cut this way, so it is rare. Jev's quote and the hand quote are the same or overlapping text on 49 of 50; on `292ce26a` they are different sentences of the same complaint.
- **Entities.** Code matches a fixed word list, so an entity cannot be invented. 21 entities on 15 reviews; all are words in the text. One is in a doubtful sense: `723f07de` begins "Update:", meaning the reviewer's own update, and matches `update`, though the same review also speaks of updating the app. The hand column uses free words (`catalog`, `access`), so the two columns are not scored against each other.
- **The review flag, as a prediction.** Jev's flag is on 14 of 50: 9 of the 20 with a differing label and 5 of the 30 without. Of the 3 plain Jev errors it is on 2. The hand `needs_review` column is `TRUE` on 8, and the two flags share 4.
- **Tone score.** Mean absolute error 0.18 on the scale from -1 to 1. The hand scores move in steps of 0.5.
- **Ambiguity noted by the labeler.** 10 of the 50 carry a note. 7 of the 20 misses do, against 3 of the 30 agreements.

## Limits

- 50 reviews, one labeler, and a reading of the misses by the assistant that built the pipeline. Travis has not yet confirmed the readings.
- By hand 30 of the 50 are `other`, so most topics have 1 to 6 reviews and no per-topic rate means much.
- The what-if on Premium uses the feature-word matches as a rough marker. It is not a count of paywalled-control complaints.
- No hard case was dropped. All 20 are listed above and in the case table.
