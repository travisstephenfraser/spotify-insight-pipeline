"""The table Travis picks the needs_review cut-off from (spec items 4 and 24). No model call.

For each candidate cut-off: how many reviews the flag marks, and against every reference
side by side, how many of Jev's differences it catches and how many agreeing answers it
marks. Rows the two outside raters dispute are a group of their own: a row two raters
dispute is a row a reviewer should see.

  python3 evals/cutoff_table.py [--answers PATH.jsonl] [--all]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "evals")]
import common  # noqa: E402

from pipeline import labels  # noqa: E402

PROBE = ROOT / "experiments/2026-10-04/tool-choice/simple.jsonl"
CUTOFFS = (0.5, 0.6, 0.7, 0.8, 0.9)


def answers_from_exchanges(path):
    """Jev's labels and its lowest top probability, from saved exchanges (the probe's file format)."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        a = row["response"]["answers"]
        out[row["review_id"]] = {
            "topic": a["topic"]["choice"],
            "intent": a["intent"]["choice"],
            "severity": labels.SEVERITY[a["severity"]["choice"]],
            "min_top": min(max(a[f]["probabilities"].values()) for f in common.FIELDS),
        }
    return out


def answers_from_files(paths):
    """Answers from several files: saved exchanges, or the flat rows cutoff_rows.py writes. A later file wins."""
    out = {}
    for path in paths:
        lines = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines and "response" in lines[0]:
            out.update(answers_from_exchanges(path))
        else:
            out.update({r["review_id"]: {k: r[k] for k in ("topic", "intent", "severity", "min_top")} for r in lines if "invalid" not in r})
    return out


def by_rule(reference):
    """A reference with the contract's fixed severity rule applied (spec item 32)."""
    return {k: {**v, "severity": labels.by_rule(v["intent"], v["severity"])} for k, v in reference.items()}


def table(answers, references, *, cutoffs=CUTOFFS, disputed=()):
    values = [a["min_top"] for a in answers.values()]
    assert len(values) < 20 or len(set(values)) > 5, "degenerate: the top probabilities are nearly all the same"
    rows = []
    for cutoff in cutoffs:
        flagged = {k for k, a in answers.items() if a["min_top"] < cutoff}
        row = {"cutoff": cutoff, "flagged": len(flagged), "of": len(answers)}
        for name, reference in references.items():
            both = [k for k in reference if k in answers]
            differ = {k for k in both if any(str(answers[k][f]) != str(reference[k][f]) for f in common.FIELDS)}
            row[name] = {
                "rows": len(both),
                "differences": len(differ),
                "caught": len(differ & flagged),
                "agreeing": len(both) - len(differ),
                "agreeing_flagged": len((set(both) - differ) & flagged),
            }
        mine = [k for k in disputed if k in answers]
        row["disputed"] = {"rows": len(mine), "flagged": len(set(mine) & flagged)}
        rows.append(row)
    return rows


def render(rows):
    lines = []
    for row in rows:
        lines.append(f"cut-off {row['cutoff']:.2f}: flags {row['flagged']} of {row['of']}")
        for name, r in row.items():
            if name in ("cutoff", "flagged", "of"):
                continue
            if name == "disputed":
                lines.append(f"    rows the raters dispute: flags {r['flagged']} of {r['rows']}")
            else:
                lines.append(
                    f"    against {name}: {r['rows']} rows; catches {r['caught']} of {r['differences']} differences; "
                    f"flags {r['agreeing_flagged']} of {r['agreeing']} agreeing answers"
                )
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--answers", action="append", help="saved Jev answers to read; may be given more than once (default: the probe's file)")
    ap.add_argument("--all", action="store_true", help="every row with a reference, not only the cut-off half")
    a = ap.parse_args(argv)
    files = a.answers or [str(PROBE)]
    answers = answers_from_files(files)
    _, cutoff_half = common.halves()
    keep = set(answers) if a.all else set(cutoff_half)
    hand = {**common.dev_labels(), **common.adjudication_labels()}
    hand = {k: v for k, v in hand.items() if k in keep}
    references = {
        "the raters' shared label": {k: v for k, v in common.shared_rater_labels().items() if k in keep},
        "Travis's label as written": hand,
        "Travis's label with the fixed severity rule": by_rule(hand),
    }
    covered = {k: v for k, v in answers.items() if k in keep}
    print(f"{len(covered)} of the {len(keep)} {'rows' if a.all else 'cut-off-half rows'} have a saved Jev answer in {', '.join(Path(f).name for f in files)}")
    if not covered:
        print("Nothing to tabulate yet: Jev has not labeled these rows.")
        return 1
    print(render(table(covered, references, disputed=common.disputed_by_raters() & keep)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
