# Decision memo: where to put next quarter's product effort

## Recommendation

**Put the effort into issue-usability (Frequent and loud advertisements and limited playback controls).** It ranks first.

- issue-usability has the most complaints and the highest priority score in the run.
- Its quotes point at concrete product surfaces a team can own: queue, skip, repeat, shuffle, ad loudness and autoplaying audio.
- issue-other ranks second but is not a good target for a quarter of work. It is a catch-all of general dissatisfaction with no clear surface to fix.
- issue-billing (Restricted playback controls for non-premium users) overlaps heavily with the playback-control part of issue-usability. Scoping the work around playback controls should cover both.

## Supporting numbers

- issue-usability has a priority score of 37 [CL-004], from 15 [CL-001] complaints and a severity sum of 37 [CL-002].
- issue-usability's mean severity is 2.466667 [CL-003]. That is moderate, so its lead comes from volume, not intensity.
- issue-other is next, with a priority score of 29 [CL-008] from 14 [CL-005] complaints.
- These figures come from a run of 100 completed reviews, with 0 quarantined.

## Alternatives

- **issue-playback (App instability and playback interruptions).** This is the strongest alternative. Its priority score is 22 [CL-012], from 6 [CL-009] complaints. Its mean severity is 3.666667 [CL-011], well above issue-usability. If leadership weights severity over volume, issue-playback should take the effort instead.
- **issue-billing.** Its priority score is 20 [CL-016], from 7 [CL-013] complaints. Its theme overlaps with issue-usability. If the two were merged into one playback-controls topic, the case for that area would get stronger. Any merged figure would need a re-run, not arithmetic here.
- **issue-access and issue-downloads.** These are small but severe. issue-access has 2 [CL-021] complaints at a mean severity of 4.000000 [CL-023]. issue-downloads has a mean severity of 3.500000 [CL-027]. More volume in either would justify a focused fix.
- **issue-catalog and issue-support.** These rank lower and do not change the recommendation on current data.

## Representative reviews

These quotes are the most severe examples plus a few picked by hash. They are not typical.

- issue-usability: "Can't repeat and play specific part.please solve this matter." [review:e16a4550-43e7-4ae1-b538-a65cc652c31b]
- issue-usability: "I am using Spotify from past two years From last update they removed basic features of music player" [review:7084ced1-0428-4093-9328-442f74719b4f]
- issue-usability: "The ads are so loud :'(" [review:ab67a772-c3b7-42ba-9b80-8d21d3857018]
- issue-billing: "The ability to skip a song or go to previous song has been removed from non subscribed users." [review:a3605554-5c3a-441d-836e-e9fdea83eb2e]
- issue-playback: "App is stuck on loading/logo screen" [review:66a29b3c-c14d-440e-b722-b23e0c99ae82]

## Limits

- **Label quality.** The labels come from a model and were checked against only a small hand-labeled set. 30 reviews (30.0 percent) were flagged for review.
- **Agreement is not accuracy.** For complaints and cancellations, all three verifiers agreed on 40 and pairs agreed on 52. For the rest, all three agreed on 43 and pairs on 48. Agreement between engines does not show the labels are correct.
- **Topics, not defects.** Each issue is a whole topic, not a single defect. issue-usability mixes ad complaints with control complaints.
- **Quotes and topics can diverge.** The quote and the topic come from separate questions and can point at different sentences.
- **Quotes are not typical.** They are the most severe examples and a few picked by hash.
- **Scope of the data.** The data shows what reviewers complained about. It cannot show why those problems occur or any business effect of fixing them.
