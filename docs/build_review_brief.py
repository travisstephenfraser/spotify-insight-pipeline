"""Rebuild Part B of docs/independent-review-brief.md from the current design spec.

Part B is the spec with earlier reviews' summaries and the authors' own lists of known
weaknesses taken out, so a fresh reviewer's findings are its own. Part A (the
instructions) is kept as it stands. Run this whenever the spec changes:

    python3 docs/build_review_brief.py
"""

import hashlib
from pathlib import Path

DOCS = Path(__file__).parent
SPEC = DOCS / "superpowers/specs/2026-10-04-spotify-insight-pipeline-design.md"
BRIEF = DOCS / "independent-review-brief.md"
PART_B = "## Part B. The design under review"

# Words that must not survive in the copy: each one would point at an earlier review.
BANNED = (
    "section 13",
    "spec-review",
    "validation-log",
    "red team",
    "CLAUDE.md",
    "independent review",
    "second review",
    "readers",
    "Known weaknesses",
    "does and does not show",
)


def swap(text, old, new):
    assert text.count(old) == 1, f"expected exactly one: {old[:60]}"
    return text.replace(old, new)


def line_starting(text, prefix):
    hits = [line for line in text.split("\n") if line.startswith(prefix)]
    assert len(hits) == 1, f"expected exactly one line starting: {prefix[:60]}"
    return hits[0]


def review_copy(spec):
    s = spec
    # The final section summarizes earlier reviews.
    s = s[: s.index("## 13. Independent review")].rstrip("\n") + "\n"
    # Status note and the pointer to the authors' decision log.
    s = swap(
        s,
        line_starting(s, "Date: 2026-10-04. Status:"),
        "Date: 2026-10-04. Status: draft. Nothing here is built.",
    )
    s = swap(
        s,
        "- **Decided**: Travis ruled on it. The full trail is in `CLAUDE.md`.",
        "- **Decided**: Travis ruled on it.",
    )
    # Places where the authors state weaknesses they already know.
    s = swap(
        s, line_starting(s, "**What agreement does and does not show:**") + "\n\n", ""
    )
    a = s.index("**Known weaknesses of the labels")
    b = s.index("**Guards against a measure that reads itself")
    s = s[:a] + s[b:]
    # Attributions and pointers to earlier reviews.
    s = swap(s, "(red team)", "(a full-file count)")
    s = swap(
        s,
        line_starting(s, "Items 1 to 16 are from the first draft."),
        "Rows marked Decided or Done carry Travis's ruling. Rows marked Delegated were ruled by the assistant on his instruction.",
    )
    s = swap(
        s,
        "The raters also confirmed the planted cases' answer key (24 and 25 of 25)",
        "The raters matched the planted cases' answer key on 24 and 25 of 25",
    )
    s = swap(
        s,
        " Results are in `docs/validation-log.md`",
        " Saved outputs are in `experiments/2026-10-04/outside-raters/`",
    )

    # Fit under the brief's headings: the title becomes bold text, other headings drop a level.
    out, fenced = [], False
    for line in s.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("# "):
            line = f"**{line[2:]}**"
        elif not fenced and line.startswith("#"):
            line = "#" + line
        out.append(line)
    s = "\n".join(out).strip("\n")
    for word in BANNED:
        assert word.lower() not in s.lower(), f"left in the copy: {word}"
    return s


def main():
    spec = SPEC.read_text(encoding="utf-8")
    sha = hashlib.sha256(spec.encode("utf-8")).hexdigest()
    brief = BRIEF.read_text(encoding="utf-8")
    assert brief.count(PART_B) == 1
    head = brief[: brief.index(PART_B) + len(PART_B)]
    note = (
        f"*This copy was made from the design file whose SHA-256 begins `{sha[:16]}`. "
        "Taken out: a status note about earlier reviews, a pointer to the authors' decision log, one paragraph and one list "
        "in which the authors state weaknesses they already know, pointers to earlier review files, and the final section, "
        "which summarized earlier reviews. One source note was reworded to name the measurement, not the review that made it. "
        "Section numbers are unchanged, and the design text is otherwise word for word.*"
    )
    copy = review_copy(spec)
    BRIEF.write_text(f"{head}\n\n{note}\n\n{copy}\n", encoding="utf-8")
    print(f"Part B rebuilt from spec {sha[:16]}: {copy.count(chr(10)) + 1} lines")


if __name__ == "__main__":
    main()
