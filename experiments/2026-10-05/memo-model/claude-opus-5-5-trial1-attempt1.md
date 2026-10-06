## Recommendation

Put next quarter's product effort on **issue-usability** (frequent and loud advertisements, and limited playback controls). It ranks first, with a priority score of 37 [CL-004] for issue-usability. It also has the most complaints: issue-usability has 15 [CL-001].

Two notes on scope:

- **issue-billing** (restricted playback controls for non-premium users) describes a closely related complaint about skipping, choosing and going back to songs. Teams scoping issue-usability work should review it alongside.
- **issue-other** ranks second, but it is a broad bucket of general dissatisfaction. It does not point to a specific product area to work on.

## Supporting numbers

| Issue | Complaints | Severity sum | Mean severity | Priority score |
|---|---|---|---|---|
| issue-usability | 15 [CL-001] | 37 [CL-002] | 2.466667 [CL-003] | 37 [CL-004] |
| issue-other | 14 [CL-005] | 29 [CL-006] | 2.071429 [CL-007] | 29 [CL-008] |
| issue-playback | 6 [CL-009] | 22 [CL-010] | 3.666667 [CL-011] | 22 [CL-012] |
| issue-billing | 7 [CL-013] | 20 [CL-014] | 2.857143 [CL-015] | 20 [CL-016] |

These figures come from a run that completed 100 reviews. Of those, 30 were flagged for review, a share of 30.0 percent, and 0 were quarantined.

## Alternatives

- **issue-playback** (crashes, stuck loading screens, playback stopping mid-song) has fewer complaints, 6 [CL-009] for issue-playback. Its complaints are more severe, with a mean severity of 3.666667 [CL-011] for issue-playback. If leads weight severity above volume, issue-playback is the strongest alternative.
- **issue-billing** has a priority score of 20 [CL-016] for issue-billing. If leads treat its playback-control complaints as part of the same topic as issue-usability, that combined area becomes even more clearly the top choice.
- **issue-access** has only 2 [CL-021] complaints for issue-access, but the highest mean severity, 4.000000 [CL-023] for issue-access. A larger sample showing more login failures would justify moving it up.
- **issue-catalog**, **issue-downloads** and **issue-support** have priority scores of 12 [CL-020] for issue-catalog, 7 [CL-028] for issue-downloads and 2 [CL-032] for issue-support. Nothing in this data argues for prioritizing them now.

## Representative reviews

These are among the most severe examples or were picked by hash. They are not typical.

- issue-usability: "Can't repeat and play specific part.please solve this matter." [review:e16a4550-43e7-4ae1-b538-a65cc652c31b]
- issue-usability: "The ads are so loud :'(" [review:ab67a772-c3b7-42ba-9b80-8d21d3857018]
- issue-usability: "Rolling out big automatically playing audio elements,without any clear way to disable the automatic playing in the settings?" [review:d455c11e-c530-4c03-a395-38f5a5cdb8d3]
- issue-billing: "The ability to skip a song or go to previous song has been removed from non subscribed users." [review:a3605554-5c3a-441d-836e-e9fdea83eb2e]
- issue-playback: "App is stuck on loading/logo screen" [review:66a29b3c-c14d-440e-b722-b23e0c99ae82]
- issue-access: "Will not except my password" [review:de0a9cdf-8974-48bc-802f-331228df4619]

## Limits

- The labels come from a model and were checked against only a small hand-labeled set.
- Each issue is a whole topic, not a single defect. Fixing issue-usability will likely mean several separate pieces of work.
- The quote and the topic come from separate questions, so a quote can point at a different sentence than the one that set the topic.
- Agreement between the two engines is not accuracy. For complaints and cancellations, all three agreed on 40 and pairs on 52. For the rest, all three agreed on 43 and pairs on 48.
- The quotes are the most severe examples and a few picked by hash, not typical ones.
- 30 reviews were flagged for review, which limits confidence in the exact counts.
- This data cannot show why customers complain. It also cannot show any effect beyond what the reviews themselves say.
