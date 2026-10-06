# Cost and runtime calculator

Replayed offline from the saved pilot files: `pilot_calls.jsonl`, `pilot_records.jsonl`, `usage.csv`, `rates.csv`, `local_compute.csv`, `assumptions.csv` and `text_volume.json`. No key, no model call, no state file.

## Measured on the 100-review pilot

- Input: cost_100.csv, SHA-256 c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e, label_config jev-1.13.0/prompt-v2/schema-v1/cut-0.70. Time is the sum of the run's sessions; idle time between a stop and a resume is left out
- IDs: 100; completed 100, failed 0; unique texts 100, result-cache hits 0

### Cold run

| Stage | Provider | Model | Setup | Batch | Workers | Requests | Attempts | Failed | Input tokens | Output tokens | API cost | Local estimate | Time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classify | TypeSafe | jev-1.13.0 | jev-1.13.0/prompt-v2/schema-v1/cut-0.70 | 1 | 1 | 100 | 100 | 0 | 98996 | 21467 | $0.004158 | $0.000000 | 13.43 s |
| verify | LM Studio (local) | google/gemma-4-26b-a4b-qat | google/gemma-4-26b-a4b-qat/verify-v1-85a7b171251f/schema-v1/max-200 | 1 | 1 | 100 | 100 | 0 | 69090 | 2017 | $0.000000 | $0.000171 | 25.69 s |
| group | LM Studio (local) | google/gemma-4-26b-a4b-qat | google/gemma-4-26b-a4b-qat/group-v1-1a315732eeb2/schema-v1/max-300/quotes-30 | 1 | 1 | 8 | 8 | 0 | 4787 | 279 | $0.000000 | $0.000026 | 3.95 s |
| memo | LM Studio (local) | google/gemma-4-26b-a4b-qat | google/gemma-4-26b-a4b-qat/memo-v1-af34c4657670/schema-v1/max-1500/quotes-5 | 1 | 1 | 1 | 4 | 3 | 20347 | 1835 | $0.000000 | $0.000129 | 19.34 s |

- API spend: $0.004158. Local compute (estimate): $0.000327.
- API cost per 1,000 rows: $0.041578; per completed record: $0.00004158.
- End to end: 62.42 s; throughput 1.60 rows a second.
- Costs that are unknown: none. Every unit above has a price in `rates.csv`.

### Warm run

| Stage | Provider | Model | Setup | Batch | Workers | Requests | Attempts | Failed | Input tokens | Output tokens | API cost | Local estimate | Time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classify | none | none | none | 1 | 1 | 0 | 0 | 0 | 0 | 0 | $0.000000 | $0.000000 | 0.00 s |
| verify | none | none | none | 1 | 1 | 0 | 0 | 0 | 0 | 0 | $0.000000 | $0.000000 | 0.00 s |
| group | none | none | none | 1 | 1 | 0 | 0 | 0 | 0 | 0 | $0.000000 | $0.000000 | 0.00 s |
| memo | none | none | none | 1 | 1 | 0 | 0 | 0 | 0 | 0 | $0.000000 | $0.000000 | 0.00 s |

- API spend: $0.000000. Local compute (estimate): $0.000000.
- API cost per 1,000 rows: $0.000000; per completed record: $0.00000000.
- End to end: 0.00 s; throughput 35919.54 rows a second.
- Costs that are unknown: none. Every unit above has a price in `rates.csv`.

### Rates

| Item | Unit | Price per unit | Source | Checked |
|---|---|---|---|---|
| jev_input_tokens | token | 0.000000042 USD | https://docs.typesafe.ai/models | 2026-10-04 |
| jev_output_tokens | token | 0 USD | TypeSafe usage page | 2026-10-05 |
| memo_input_tokens | token | 0.000002 USD | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-05 |
| memo_output_tokens | token | 0.00001 USD | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-05 |

Local compute is an estimate: measured seconds times 60 W times $0.40 per kWh. Both are assumptions in `local_compute.csv`.

## Estimated before the full run

All 660,622 rows accounted for; 660,609 nonempty outputs; 13 empty-text quarantines. Every figure in this section is an estimate.

| Case | Jev requests | Attempts | Input tokens per request | API cost | Local estimate | Jev time at the rate cap | Jev time with one worker |
|---|---|---|---|---|---|---|---|
| Base: exact-text reuse | 484,189 | 484,189 | 1003 | $20.39 | $0.01 | 1.79 h | 18.07 h |
| No reuse, for comparison | 660,609 | 660,609 | 986 | $27.35 | $0.01 | 2.45 h | 24.65 h |
| Conservative: more retries, output tokens billed at the input rate | 484,189 | 508,398 | 1003 | $21.41 | $0.01 | 1.79 h | 18.07 h |

- Verify: 5,000 reviews, about 0.36 h on this machine. Naming: 8 calls. Memo: 1 call, added once.
- Input tokens per request are scaled from the pilot by the full file's average text length (`text_volume.json`), because pilot reviews are not the average text.
- Unknown costs: none in the base case.
- Spending limit: $35.

### Controls and assumptions

| Item | Value | Note |
|---|---|---|
| rows | 660622 | Rows in the full file (manifest.json) |
| nonempty | 660609 | Rows with nonempty text: the work without exact-text reuse |
| distinct | 484189 | Distinct nonempty texts: the work with exact-text reuse |
| verify | 5000 | Reviews in the verify sample |
| issues | 8 | Naming calls at most: one per topic |
| retry_rate_base | 0 | Extra attempts per request in the base case. The pilot's own failure rate replaces this when it is higher |
| retry_rate_conservative | 0.05 | Extra attempts per request in the conservative case |
| text_copies | 2 | How many times a byte of review text appears in a request: once as the review and once more when it is split into sentences. An assumption |
| max_requests_per_second | 75 | The limiter's ceiling. Sustained speed is unmeasured until the 10000 gate |
| max_workers | 16 | Most requests in flight at once |
| spending_limit_usd | 35 | The cap on total Jev spend |
| fallback_fraction | 0 | Share of reviews sent to a stronger model. Zero by design: there is no fallback model |
| output_token_cap_verify | 200 | max_tokens on a verify call |
| output_token_cap_group | 300 | max_tokens on a naming call |
| output_token_cap_memo | 1500 | max_tokens on the memo call |

### Formulas

- `item_cost = billed_units x price_per_unit`; `total_cost = sum(item_cost)`. A price per million tokens is divided by 1,000,000 first.
- A stage's time is its session clock, not the sum of its request times. A run's time is the sum of its sessions; idle time between a stop and a resume is left out.
- Projected Jev cost = attempts x input tokens per request x input rate, where attempts = requests x (1 + retry rate).
