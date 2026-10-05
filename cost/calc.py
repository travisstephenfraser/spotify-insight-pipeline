"""The cost and runtime calculator's arithmetic. Standard library only.

It reads the saved pilot files and nothing else: no state file, no client, no key. Money
is exact Decimal and is never rounded before it is summed. API spend, the local-compute
estimate and costs that are unknown are three separate totals.
"""

import csv
import json
from decimal import Decimal
from pathlib import Path

STAGES = ("classify", "verify", "group", "memo")
ROLE = {"classify": "enrich", "verify": "verify", "group": "group", "memo": "memo"}
LOCAL_STAGES = ("verify", "group", "memo")  # run on this machine; they have no API charge
PILOT_FILES = ("pilot_records.jsonl", "pilot_calls.jsonl", "usage.csv")


class Degenerate(Exception):
    """A pilot that reports no tokens is a measurement reading nothing. Never report it as cheap."""


class NoPilot(Exception):
    pass


def _csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def load(folder):
    """Everything replay needs, from committed files."""
    folder = Path(folder)
    missing = [name for name in PILOT_FILES if not (folder / name).exists()]
    if missing:
        raise NoPilot(f"no pilot evidence in {folder}: {', '.join(missing)} missing")
    return {
        "calls": _jsonl(folder / "pilot_calls.jsonl"),
        "records": _jsonl(folder / "pilot_records.jsonl"),
        "usage": _csv(folder / "usage.csv"),
        "rates": _csv(folder / "rates.csv"),
        "local": _csv(folder / "local_compute.csv"),
        "assumptions": _csv(folder / "assumptions.csv"),
        "text_volume": json.loads((folder / "text_volume.json").read_text(encoding="utf-8")),
    }


def _rate(rates, item):
    """The price of one unit, or None when the rate is unknown (a blank cell)."""
    row = next((r for r in rates if r["item"] == item), None)
    return Decimal(row["usd_per_unit"]) if row and row["usd_per_unit"].strip() else None


def _stage(calls, usage_row, role):
    mine = [c for c in calls if c.get("role") == role]
    succeeded = sum(c["outcome"] == "succeeded" for c in mine)
    if role in ("enrich", "verify"):
        requests = len({tuple(c["review_ids"]) for c in mine})
    else:
        requests = succeeded or (1 if mine else 0)
    return {
        "provider": usage_row["provider"],
        "model": usage_row["model"],
        "config": usage_row["config"],
        "batch_size": int(usage_row["batch_size"]),
        "workers": int(usage_row["workers"]),
        "requests": requests,
        "attempts": len(mine),
        "succeeded": succeeded,
        "failed": len(mine) - succeeded,
        "input_tokens": sum(c["input_tokens"] for c in mine),
        "output_tokens": sum(c["output_tokens"] for c in mine),
        "calls_usage_unknown": sum(not c["usage_known"] for c in mine),
        "request_bytes": sum(c.get("request_bytes", 0) for c in mine),
        "seconds": Decimal(usage_row["seconds"]),
    }


def measured(*, calls, rates, usage, local, records=(), **_):
    """What the pilot measured, cold and warm apart. Nothing here depends on a projected row count."""
    rate_in, rate_out = _rate(rates, "jev_input_tokens"), _rate(rates, "jev_output_tokens")
    assumptions = {r["item"]: Decimal(r["value"]) for r in local}
    usd_per_second = assumptions["power_draw_watts"] / 3_600_000 * assumptions["electricity_usd_per_kwh"]
    out = {}
    for which in ("cold", "warm"):
        rows = {u["stage"]: u for u in usage if u["pass"] == which}
        mine = [c for c in calls if c.get("pass") == which and "role" in c]
        stages = {name: _stage(mine, rows[name], ROLE[name]) for name in STAGES}
        api, unknown = Decimal(0), []
        for name, stage in stages.items():
            stage["api_usd"] = Decimal(0)
            stage["local_usd_estimate"] = stage["seconds"] * usd_per_second if name in LOCAL_STAGES else Decimal(0)
            if name == "classify":
                if rate_in is None:
                    unknown.append({"what": "Jev input tokens at an unknown rate", "units": stage["input_tokens"], "unit": "token"})
                else:
                    stage["api_usd"] += stage["input_tokens"] * rate_in
                if rate_out is None:
                    if stage["output_tokens"]:
                        unknown.append({"what": "Jev output tokens at an unknown rate", "units": stage["output_tokens"], "unit": "token"})
                else:
                    stage["api_usd"] += stage["output_tokens"] * rate_out
                if stage["calls_usage_unknown"]:
                    unknown.append({"what": "Jev calls that returned no usage", "units": stage["calls_usage_unknown"], "unit": "call"})
            api += stage["api_usd"]
        out[which] = {
            "stages": stages,
            "api_usd": api,
            "local_usd_estimate": sum((s["local_usd_estimate"] for s in stages.values()), Decimal(0)),
            "unknown": unknown,
            "seconds": Decimal(rows["end_to_end"]["seconds"]),
            "note": rows["end_to_end"]["note"],
        }
    if not sum(s["input_tokens"] + s["output_tokens"] for s in out["cold"]["stages"].values()):
        raise Degenerate("the cold pilot reports zero tokens: the usage was not read, so no cost can be stated")
    done = [r for r in records if r.get("status") == "completed"]
    out["records"] = {
        "ids": len(records),
        "completed": len(done),
        "failed": len(records) - len(done),
        "unique_texts": sum("cache_source_id" not in r for r in done),
        "cache_hits": sum("cache_source_id" in r for r in done),
    }
    return out


def projection_inputs(inputs):
    """The editable assumptions as arguments for `project`."""
    a = {r["item"]: r["value"] for r in inputs["assumptions"]}
    return {
        "rows": int(a["rows"]),
        "nonempty": int(a["nonempty"]),
        "distinct": int(a["distinct"]),
        "verify": int(a["verify"]),
        "issues": int(a["issues"]),
        "text_volume": inputs["text_volume"],
        "retry_rate": Decimal(a["retry_rate_base"]),
        "conservative_retry_rate": Decimal(a["retry_rate_conservative"]),
        "text_copies": Decimal(a["text_copies"]),
        "max_rps": Decimal(a["max_requests_per_second"]),
        "cap": Decimal(a["spending_limit_usd"]),
        "rates": inputs["rates"],
        "local": inputs["local"],
    }


def project(
    measured, *, rows, nonempty, distinct, verify, issues, text_volume, retry_rate, conservative_retry_rate=Decimal("0.05"),
    text_copies=Decimal(2), max_rps=Decimal(75), cap=Decimal(25), rates=(), local=(),
):  # fmt: skip
    """Full-run estimates. Each stage from its own work count; the memo once. Every figure here is an estimate."""
    cold = measured["cold"]["stages"]
    classify = cold["classify"]
    n = Decimal(classify["requests"])
    rate_in, rate_out = _rate(rates, "jev_input_tokens"), _rate(rates, "jev_output_tokens")
    local_rates = {r["item"]: Decimal(r["value"]) for r in local}
    usd_per_second = local_rates["power_draw_watts"] / 3_600_000 * local_rates["electricity_usd_per_kwh"] if local_rates else Decimal(0)

    tokens_per_byte = Decimal(classify["input_tokens"]) / Decimal(classify["request_bytes"])
    pilot_text = Decimal(text_volume["pilot_text_bytes"]) / Decimal(text_volume["pilot_rows"])
    measured_retry = Decimal(classify["attempts"] - classify["requests"]) / n
    out_per_request = Decimal(classify["output_tokens"]) / n

    def classify_case(requests, text_bytes_total, text_count, retries, bill_output_at_input_rate):
        avg_text = Decimal(text_bytes_total) / Decimal(text_count) if text_count else pilot_text
        request_bytes = Decimal(classify["request_bytes"]) / n + (avg_text - pilot_text) * text_copies
        tokens = request_bytes * tokens_per_byte
        attempts = Decimal(requests) * (1 + max(retries, measured_retry))
        api = attempts * tokens * rate_in if rate_in is not None else Decimal(0)
        unknown = []
        out_tokens = attempts * out_per_request
        if rate_out is not None:
            api += out_tokens * rate_out
        elif bill_output_at_input_rate and rate_in is not None:
            api += out_tokens * rate_in
        elif out_tokens:
            unknown.append({"what": "Jev output tokens at an unknown rate", "units": out_tokens, "unit": "token"})
        return {
            "requests": requests,
            "attempts": attempts,
            "input_tokens_per_request": tokens,
            "output_tokens_per_request": out_per_request,
            "api_usd": api,
            "local_usd_estimate": Decimal(0),
            "seconds_one_worker": Decimal(requests) * classify["seconds"] / n,
            "seconds": Decimal(requests) / max_rps,
            "unknown": unknown,
        }

    def local_case(name, requests):
        stage = cold[name]
        seconds = stage["seconds"] * Decimal(requests) / Decimal(stage["requests"]) if stage["requests"] else Decimal(0)
        return {"requests": requests, "api_usd": Decimal(0), "local_usd_estimate": seconds * usd_per_second, "seconds": seconds, "unknown": []}

    def case(requests, text_bytes, text_count, retries, bill_output):
        stages = {
            "classify": classify_case(requests, text_bytes, text_count, retries, bill_output),
            "verify": local_case("verify", min(verify, nonempty)),
            "group": local_case("group", min(issues, cold["group"]["requests"] or issues)),
            "memo": {**local_case("memo", cold["memo"]["requests"] or 1), "requests": 1},  # one memo, added once
        }
        return {
            "stages": stages,
            "api_usd": sum((s["api_usd"] for s in stages.values()), Decimal(0)),
            "local_usd_estimate": sum((s["local_usd_estimate"] for s in stages.values()), Decimal(0)),
            "unknown": [u for s in stages.values() for u in s["unknown"]],
            "seconds": sum((s["seconds"] for s in stages.values()), Decimal(0)),
        }

    distinct_bytes, nonempty_bytes = text_volume["full_distinct_text_bytes"], text_volume["full_nonempty_text_bytes"]
    full = rows >= text_volume.get("full_rows", rows)  # another row count has no measured text volume: use the pilot's
    cases = {
        "base": case(distinct, distinct_bytes if full else 0, text_volume["full_distinct_texts"] if full else 0, retry_rate, False),
        "no_reuse": case(nonempty, nonempty_bytes if full else 0, text_volume["full_nonempty_rows"] if full else 0, retry_rate, False),
        "conservative": case(distinct, distinct_bytes if full else 0, text_volume["full_distinct_texts"] if full else 0, conservative_retry_rate, True),
    }
    warnings = [
        f"the {name} case passes the cap: ${c['api_usd']:.2f} against ${cap}" for name, c in cases.items() if c["api_usd"] > cap
    ]
    return {**cases, "warnings": warnings, "rows": rows, "nonempty": nonempty, "distinct": distinct, "cap": cap}


def _usd(value, places=4):
    return f"${value:.{places}f}"


def _seconds(value):
    value = Decimal(value)
    return f"{value:.2f} s" if value < 600 else f"{value / 3600:.2f} h"


def report(inputs, measured_, projection):
    """The report as markdown. The same files always give the same bytes."""
    lines = ["# Cost and runtime calculator", ""]
    lines += [
        "Replayed offline from the saved pilot files: `pilot_calls.jsonl`, `pilot_records.jsonl`, `usage.csv`, `rates.csv`, "
        "`local_compute.csv`, `assumptions.csv` and `text_volume.json`. No key, no model call, no state file.",
        "",
        "## Measured on the 100-review pilot",
        "",
    ]
    rec = measured_["records"]
    lines += [
        f"- Input: {measured_['cold']['note']}",
        f"- IDs: {rec['ids']}; completed {rec['completed']}, failed {rec['failed']}; unique texts {rec['unique_texts']}, result-cache hits {rec['cache_hits']}",
        "",
    ]
    rates = {r["item"]: r for r in inputs["rates"]}
    for which, title in (("cold", "Cold"), ("warm", "Warm")):
        m = measured_[which]
        lines += [
            f"### {title} run",
            "",
            "| Stage | Provider | Model | Setup | Batch | Workers | Requests | Attempts | Failed | Input tokens | Output tokens | API cost | Local estimate | Time |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name in STAGES:
            s = m["stages"][name]
            lines.append(
                f"| {name} | {s['provider'] or 'none'} | {s['model'] or 'none'} | {s['config'] or 'none'} | {s['batch_size']} | {s['workers']} | "
                f"{s['requests']} | {s['attempts']} | {s['failed']} | {s['input_tokens']} | {s['output_tokens']} | {_usd(s['api_usd'], 6)} | "
                f"{_usd(s['local_usd_estimate'], 6)} | {_seconds(s['seconds'])} |"
            )
        completed = rec["completed"] or 1
        lines += [
            "",
            f"- API spend: {_usd(m['api_usd'], 6)}. Local compute (estimate): {_usd(m['local_usd_estimate'], 6)}.",
            f"- API cost per 1,000 rows: {_usd(m['api_usd'] * 1000 / (rec['ids'] or 1), 6)}; per completed record: {_usd(m['api_usd'] / completed, 8)}.",
            f"- End to end: {_seconds(m['seconds'])}; throughput {Decimal(rec['ids']) / m['seconds']:.2f} rows a second." if m["seconds"] else "- End to end: no time recorded.",
        ]
        if m["unknown"]:
            lines += ["- Costs that are unknown, and are not counted as zero:"] + [
                f"  - {u['what']}: {u['units']} {u['unit']}s" for u in m["unknown"]
            ]
        lines.append("")
    lines += ["### Rates", "", "| Item | Unit | Price per unit | Source | Checked |", "|---|---|---|---|---|"]
    for item, r in rates.items():
        price = f"{r['usd_per_unit']} {r['currency']}" if r["usd_per_unit"].strip() else "unknown"
        lines.append(f"| {item} | {r['unit']} | {price} | {r['source']} | {r['checked']} |")
    local = {r["item"]: r for r in inputs["local"]}
    lines += [
        "",
        f"Local compute is an estimate: measured seconds times {local['power_draw_watts']['value']} W times "
        f"${local['electricity_usd_per_kwh']['value']} per kWh. Both are assumptions in `local_compute.csv`.",
        "",
        "## Estimated before the full run",
        "",
        f"All {projection['rows']:,} rows accounted for; {projection['nonempty']:,} nonempty outputs; "
        f"{projection['rows'] - projection['nonempty']:,} empty-text quarantines. Every figure in this section is an estimate.",
        "",
        "| Case | Jev requests | Attempts | Input tokens per request | API cost | Local estimate | Jev time at the rate cap | Jev time with one worker |",
        "|---|---|---|---|---|---|---|---|",
    ]
    names = {"base": "Base: exact-text reuse", "no_reuse": "No reuse, for comparison", "conservative": "Conservative: more retries, output tokens billed at the input rate"}
    for name, title in names.items():
        c = projection[name]
        s = c["stages"]["classify"]
        lines.append(
            f"| {title} | {s['requests']:,} | {s['attempts']:,.0f} | {s['input_tokens_per_request']:.0f} | {_usd(c['api_usd'], 2)} | "
            f"{_usd(c['local_usd_estimate'], 2)} | {_seconds(s['seconds'])} | {_seconds(s['seconds_one_worker'])} |"
        )
    base = projection["base"]
    lines += [
        "",
        f"- Verify: {base['stages']['verify']['requests']:,} reviews, about {_seconds(base['stages']['verify']['seconds'])} on this machine. "
        f"Naming: {base['stages']['group']['requests']} calls. Memo: 1 call, added once.",
        "- Input tokens per request are scaled from the pilot by the full file's average text length (`text_volume.json`), "
        "because pilot reviews are not the average text.",
    ]
    for u in base["unknown"]:
        lines.append(f"- Unknown and not counted: {u['what']}, about {u['units']:,.0f} {u['unit']}s in the base case.")
    lines += [f"- Spending limit: ${projection['cap']}."] + [f"- **Warning:** {w}." for w in projection["warnings"]]
    lines += ["", "### Controls and assumptions", "", "| Item | Value | Note |", "|---|---|---|"]
    lines += [f"| {r['item']} | {r['value']} | {r['note']} |" for r in inputs["assumptions"]]
    lines += [
        "",
        "### Formulas",
        "",
        "- `item_cost = billed_units x price_per_unit`; `total_cost = sum(item_cost)`. A price per million tokens is divided by 1,000,000 first.",
        "- A stage's time is its session clock, not the sum of its request times. A run's time is the sum of its sessions; idle time between a stop and a resume is left out.",
        "- Projected Jev cost = attempts x input tokens per request x input rate, where attempts = requests x (1 + retry rate).",
        "",
    ]
    return "\n".join(lines)
