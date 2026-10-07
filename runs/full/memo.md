## Recommendation

Put the next quarter's effort on issue-usability (repetitive playback and excessive advertisements). It ranks first, and I am not recommending a different issue. Its priority score is 212158 [CL-004], which comes from a severity sum of 212158 [CL-002] across 81756 complaints [CL-001]. It is the largest on severity sum, though not on complaint count.

Issue-usability is the first-ranked issue, and no other issue is recommended over it.

## Supporting numbers

- issue-usability: 81756 complaints [CL-001], severity sum 212158 [CL-002], mean severity 2.595014 [CL-003], priority score 212158 [CL-004].
- issue-other: 85466 complaints [CL-005], which is more than issue-usability. Its mean severity is 2.057134 [CL-007], which is lower.
- Run facts: 660609 reviews were completed, 13 were quarantined, and 191158 were flagged as needing review (28.9 percent).

## Alternatives

- issue-other (general dissatisfaction with app updates and quality) ranks second with a priority score of 175815 [CL-008]. It is a broad catch-all with the lowest mean severity among the top four, so it is hard to turn into a specific piece of work. It would matter more if its complaints could be split into concrete defects.
- issue-playback (unreliable playback and app instability) ranks third with a priority score of 147175 [CL-012]. Its mean severity is 3.462697 [CL-011] on 42503 complaints [CL-009], so each complaint is more severe. It would move up if severity were weighted more heavily than volume.
- issue-billing ranks fourth with a priority score of 141482 [CL-016], and a mean severity of 2.918117 [CL-015].
- issue-access has the highest mean severity, 3.936154 [CL-023], but only 10353 complaints [CL-021]. A focus on severity alone would favor it.

## Representative reviews

These are among the most severe examples plus a few picked by hash. They are not typical.

- issue-usability: "Gets stuck in a loop of the same songs." [review:88587f1e-7047-4167-b424-735eddada88e]
- issue-usability: "I have multiple playlist with well over a 1000 songs and Spotify only plays the same 40 songs from each playlist over and over." [review:9eee37ce-f388-4631-aba7-dec28dfb55d0]
- issue-usability: "so I made a playlist and I lost all my musics and it's only the second day!" [review:f05618d9-35bc-45ed-966f-3b76db77bb52]
- issue-playback: "The app stops playing mid-track randomly and starts again multiple times." [review:6030fa74-e183-4142-9f7a-9a81ae2108d2]

## Limits

- The labels come from a model and were checked against only a small hand-labeled set.
- The quote and the topic come from separate questions and can point at different sentences.
- Each issue is a whole topic, not a single defect, so the work inside issue-usability still needs scoping.
- Agreement between the two engines is not accuracy.
- The quotes are the most severe examples and a few picked by hash, not typical ones.
- These numbers show how many complaints there are and how severe they were rated. They do not show causes or business effects.
