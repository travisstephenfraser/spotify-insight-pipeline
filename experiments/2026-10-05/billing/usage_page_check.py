"""Are Jev's output tokens billed? The TypeSafe usage page against our own token counts.

Travis read the usage page on 2026-10-05, after the wording trial: $0.056, 1,640,194 tokens,
1,451 requests, for everything this project has sent to Jev. This script asks which reading
of those three numbers fits what the responses themselves reported. It makes no call.

    python3 experiments/2026-10-05/billing/usage_page_check.py
"""

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RATE_IN = Decimal("0.042") / 1_000_000  # dollars per input token, docs.typesafe.ai/models, checked 2026-10-04

# Read from the usage page by Travis, 2026-10-05. The dollar figure has three decimals.
PAGE_USD, PAGE_TOKENS, PAGE_REQUESTS = Decimal("0.056"), 1_640_194, 1_451
PAGE_USD_LOW, PAGE_USD_HIGH = PAGE_USD - Decimal("0.0005"), PAGE_USD + Decimal("0.0005")

# The wording trial, from the state file's call log (validation log entry 23).
TRIAL = {"requests": 68, "input": 64_710, "output": 14_535}


def saved_probe():
    """Token counts the 2026-10-04 probe saved with each response: the only earlier calls that kept them."""
    requests = tin = tout = 0
    for name in ("simple.jsonl", "sentence.jsonl"):
        for line in (ROOT / "experiments/2026-10-04/tool-choice" / name).read_text(encoding="utf-8").splitlines():
            usage = json.loads(line)["response"]["usage"]
            requests, tin, tout = requests + 1, tin + usage["input_tokens"], tout + usage["output_tokens"]
    return {"requests": requests, "input": tin, "output": tout}


def readings():
    probe = saved_probe()
    logged_requests = probe["requests"] + TRIAL["requests"]
    out_per_response = Decimal(probe["output"] + TRIAL["output"]) / logged_requests
    result = {
        "logged_requests": logged_requests,
        "output_tokens_per_response_measured": out_per_response,
        "probe_output_per_response": Decimal(probe["output"]) / probe["requests"],
        "trial_output_per_response": Decimal(TRIAL["output"]) / TRIAL["requests"],
        # Reading A: the page's tokens are input plus output, and only input is billed.
        "a_input_tokens": PAGE_USD / RATE_IN,
        "a_output_per_request": (PAGE_TOKENS - PAGE_USD / RATE_IN) / PAGE_REQUESTS,
        "a_output_per_request_low": (PAGE_TOKENS - PAGE_USD_HIGH / RATE_IN) / PAGE_REQUESTS,
        "a_output_per_request_high": (PAGE_TOKENS - PAGE_USD_LOW / RATE_IN) / PAGE_REQUESTS,
        # Reading B: every token on the page is billed at the input rate.
        "b_usd": PAGE_TOKENS * RATE_IN,
    }
    result["a_fits"] = result["a_output_per_request_low"] <= out_per_response <= result["a_output_per_request_high"]
    result["b_fits"] = PAGE_USD_LOW <= result["b_usd"] < PAGE_USD_HIGH
    return result


def main():
    r = readings()
    print(f"usage page: ${PAGE_USD}, {PAGE_TOKENS:,} tokens, {PAGE_REQUESTS:,} requests ({Decimal(PAGE_TOKENS) / PAGE_REQUESTS:.1f} tokens a request)")
    print(f"responses that saved their usage: {r['logged_requests']} of {PAGE_REQUESTS:,}; output tokens per response {r['output_tokens_per_response_measured']:.1f} "
          f"(probe {r['probe_output_per_response']:.1f}, trial {r['trial_output_per_response']:.1f})")
    print("reading A, tokens are input plus output and only input is billed:")
    print(f"  ${PAGE_USD} buys {r['a_input_tokens']:,.0f} input tokens, which leaves {r['a_output_per_request']:.1f} output tokens a request "
          f"({r['a_output_per_request_low']:.1f} to {r['a_output_per_request_high']:.1f} for the page's rounding)")
    print(f"  the measured figure is inside that range: {r['a_fits']}")
    print("reading B, every token is billed at the input rate:")
    print(f"  the page would show ${r['b_usd']:.4f}; it shows ${PAGE_USD}: fits {r['b_fits']}")
    print(f"this trial alone: ${TRIAL['input'] * RATE_IN:.6f} for input, ${TRIAL['output'] * RATE_IN:.6f} more if output were billed at the input rate")


if __name__ == "__main__":
    main()
