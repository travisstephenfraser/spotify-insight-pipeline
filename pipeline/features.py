"""Feature words: the fixed list `entities` is drawn from, and the one way a text is matched against it.

An entry matches itself, or itself plus `s`, as a whole word or phrase in the lowercased
text. Where a phrase and a word inside it both match, the phrase wins.
"""

import re
from functools import lru_cache
from pathlib import Path


def load(path):
    """Entries, one per line. Blank lines and lines starting with # are skipped."""
    lines = (line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines())
    return tuple(line for line in lines if line and not line.startswith("#"))


@lru_cache(maxsize=8)
def _pattern(entries):
    longest_first = sorted(entries, key=lambda e: (-len(e), e))
    body = "|".join(re.escape(e) for e in longest_first)
    return re.compile(rf"(?<![a-z0-9])({body})s?(?![a-z0-9])")


def find(text, entries):
    """The entries found in `text`, once each, in the order they first appear."""
    entries = tuple(entries)
    if not entries:
        return []
    found = []
    for match in _pattern(entries).finditer(text.lower()):
        if match.group(1) not in found:
            found.append(match.group(1))
    return found
