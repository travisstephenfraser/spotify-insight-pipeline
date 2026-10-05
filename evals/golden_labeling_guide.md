# Golden 50: labeling guide

Your 50 labels are the answer key the classifier is graded against. The definitions come from `GRADING_CONTRACT.md`. Lines marked *(ours)* are conventions for this project and can be changed.

## Three slips from the practice round (29 reviews, 2026-10-04)

Read the whole review before you fill in anything. Each of these came from labeling off the first sentence.

1. **Premium-only controls are `billing`.** If the review says a control is locked behind Premium (skipping, picking a song, shuffle-only for free users), the topic is `billing`, even when the first sentence reads like a playback or usability problem. Three practice rows were labeled `playback` or `usability` and should have been `billing`.
2. **Severity follows what stopped working, not how angry the writer is.** A threat to leave does not raise it. Generic criticism such as "very disappointing" is 2. If a workaround exists (wifi fails but mobile data works), it is 3, not 4. Use 4 only when a core task is blocked outright. Four practice rows were one step too high.
3. **Quotes are pasted, one continuous piece.** Do not retype, fix a typo, add a period, change a capital, or join two parts with `[…]`. Five practice quotes failed the exact-copy check this way.

Two smaller ones: a threat to switch to another service anywhere in the review makes the intent `cancellation`, even when a complaint comes first. And the value is spelled `complaint`; type it once and copy it down, since `compliant` slipped in nine times.

## Before you start

- Open `evals/golden_50_labeled.csv` in Numbers. It has the 50 review texts and blank label columns. Star ratings are left out on purpose *(ours)*: labels come from the text alone.
- Numbers saves your work as its own document in iCloud, not back into the CSV. That is fine: say when you are done and the labels get imported by review ID. For the golden set the import reports row numbers and column names only; nobody reads your labels into a prompt or an example.
- Label all 50 before you look at any model output for these reviews.
- Go straight through once, then revisit the rows you were unsure about. Roughly an hour.

## For each review, fill the columns left to right

**1. intent.** Take the first one that fits.

| Value | Use when |
|---|---|
| `cancellation` | They say they are leaving, uninstalling, cancelling or switching, or threaten to |
| `complaint` | Any negative experience, including mixed praise and criticism |
| `request` | They want a change but report no failure |
| `praise` | Positive, no problem reported |
| `unclear` | Meaningless or unrelated text, or a bare boycott slogan |

**2. topic.** The most serious specific problem. On a tie, the first one mentioned. For praise, the first specific feature praised.

| Value | Covers |
|---|---|
| `access` | Login, signup, password, account access |
| `usability` | Navigation, controls, layout, queue and playlist management, ad interruptions |
| `playback` | Playback failure, crashes, lag, connection failures, audio quality, resource use |
| `downloads` | Downloading, saved music, offline listening, disappearing downloads |
| `catalog` | Missing songs or artists, search, recommendations, lyrics |
| `billing` | Price, charges, subscriptions, paywalls, premium-only controls |
| `support` | Contacting support and the response |
| `other` | General praise or criticism, unrelated content, nothing specific |

**3. severity.** A whole number.

| | Meaning |
|---|---|
| 1 | No problem reported: praise, unclear text, or a pure feature request |
| 2 | Dislike, generic criticism, minor annoyance, cosmetic issue |
| 3 | A function is degraded or restricted, but some use or a workaround remains |
| 4 | A core task is clearly blocked (cannot log in, cannot play music) |
| 5 | Explicit serious financial, privacy or data harm |

**4. sentiment.** One of `-1`, `-0.5`, `0`, `0.5`, `1`, from very negative to very positive *(ours)*.

**5. evidence_quote.** Copy and paste the shortest continuous piece of the review that justifies your topic and severity.

**6. entities.** Product features the review names, lowercase, separated by `;` such as `shuffle; playlist` *(ours)*. Blank if none.

**7. needs_review.** `TRUE` if you could not choose confidently or the text is too unclear to judge. Otherwise `FALSE`.

**notes** (optional, *ours*). If a second label is defensible, write it, for example `alt topic: usability`. We report how many cases were ambiguous.

## Other rules that trip people up

- Mentioning Premium is not `billing` by itself. Music crashing for a paying user is `playback`. A subscription that fails to activate is `billing`.
- Ads interrupting listening is `usability`.
- "Bad app" with no detail is `complaint`, `other`, severity 2. Do not guess a defect.
- General praise such as "best for listening to songs" is `other`, not `playback`.
- A boycott slogan or meaningless text is `unclear`, `other`, severity 1.
- One star, angry words, a crash or a high price alone are not severity 5.
- A wish with no failure reported is `request`, severity 1.
- Never add impact the text does not state. Set `needs_review` to `TRUE` instead.
- If you cannot read the language, translating it yourself is fine; say so in notes *(ours)*. If it is still unclear, use `unclear`, `other`, severity 1, `needs_review` `TRUE`. The quote stays in the original words.

## When you finish

Say so in the chat. A format check reports only row numbers and column names with problems: a blank cell, a value outside the lists, or a quote that is not an exact copy. Fix those, then the file is committed and its SHA-256 recorded. That is the frozen answer key, and it is frozen before you see any model output for these reviews.

After the freeze no label changes. If a label turns out to be plainly wrong, it stays as it is, and the report shows the score both ways with the reason.
