# Cost and runtime calculator

A 100-review pilot, measured once, and a calculator that replays it offline.

## Two commands

```sh
python3 -m cost                 # offline replay, the default. No key, no model call, no state file
python3 -m cost pilot --go      # the paid pilot. Runs only when asked by name with --go
```

Importing or opening the calculator starts nothing.

**Replay** reads only the files in this folder and writes `report.md`. To see that the projection and the measurement are separate, change the projected row count:

```sh
python3 -m cost replay --rows 1000 --nonempty 1000 --distinct 900
```

The measured section of the report does not change. To see that rates and usage are separate, double every price in `rates.csv` and replay: the API subtotal doubles, and the local-compute estimate and every measured time stay the same. Double one price and only its own line moves: with Jev's input price doubled, the pilot's API spend goes from $0.026428 to $0.030586, because the memo's share stays where it was.

**The pilot** runs `cost_100.csv` unchanged through all six stages with one worker, stops once after 50 reviews and resumes (so the run has resume evidence), then makes a warm pass that takes every result from the cold run and makes no call of any role. It then writes the evidence files below. When it ran on 2026-10-06 it cost $0.0042 of Jev spend and $0.0223 for the memo. It needs the local model server running and both keys.

## Files

| File | What it holds | Who writes it |
|---|---|---|
| `rates.csv` | Each billed item, its unit, its price, a dated source link. A blank price means unknown | You. Editable |
| `local_compute.csv` | Assumed power draw and electricity price for the local-compute estimate | You. Editable |
| `assumptions.csv` | Row counts, retry rates, the spending limit, worker and rate limits, output-token caps | You. Editable |
| `text_volume.json` | How much review text the full file and the pilot hold, counted by code | `cost/evidence.py` |
| `pilot_records.jsonl` | One result and status per pilot ID, with the row hash and labels | The pilot |
| `pilot_calls.jsonl` | Every attempted call of the cold run, with its run ID, request ID, usage and time, and one record saying the warm pass made no call | The pilot |
| `usage.csv` | Per run and stage: requests, attempts, failures, tokens, and seconds from the stage's own clock; one row per run for the whole run | The pilot |
| `report.md` | The measured table and the full-run estimates | Replay |

## What the report keeps apart

- **API spend**: billed units times the price in `rates.csv`, exact, never rounded before it is summed.
- **Local compute**: an estimate. Measured seconds times the assumptions in `local_compute.csv`. Running a model on this laptop is not free.
- **Unknown costs**: listed with their units and never counted as zero. Whether Jev bills its output tokens was read from the provider's usage page twice, on 2026-10-05 and again after the full run on 2026-10-07: it does not, so `jev_output_tokens` has a price of 0 and a note with the reading. The second reading matches the saved call log to the token (validation log entry 41). A blank price still means unknown.

A stage's time is its session clock, not the sum of its request times. A run's time is the sum of its sessions; the idle time between the deliberate stop and the resume is left out.

## Status

The files here are from the pilot of 2026-10-06, made on the code the full run used (runs `pilot4-cold` and `pilot4-warm`, validation log entry 34). Cold: 100 of 100 labeled, API spend $0.026428, 49.75 seconds end to end. Warm: no call of any role. The run's own evidence is in [`runs/pilot4-cold/`](../runs/pilot4-cold/run_summary.json).

The full run that followed cost $20.36 against the $20.42 estimated in `report.md`. The report does not print that comparison; the main [README](../README.md#results-summary) does.

The conservative row of the projection was corrected on 2026-10-07. It was labeled as billing output tokens at the input rate, but did so only when the output price in `rates.csv` was blank, and the price there is 0. Its time also counted requests where it should count attempts. It read $21.44 and 1.79 hours when the full run was started; it now reads $26.02 and 1.88 hours. The base case, the no-reuse case and every measured figure are unchanged (validation log entry 39).

With the pilot files missing, replay says so and makes up no number in their place.
