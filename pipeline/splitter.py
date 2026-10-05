"""Sentence pieces. Each piece is an exact substring of the text, so it can be quoted as evidence."""

import re

# After sentence punctuation, at line breaks, and after sentence marks of scripts that use no space.
SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+|(?<=[।。！？؟۔])\s*")


def pieces(text):
    """Pieces that hold a letter or digit, in order. Text with none is one piece: itself, trimmed."""
    parts = [p.strip() for p in SPLIT.split(text)]
    parts = [p for p in parts if p]
    assert all(p in text for p in parts), "a piece is not an exact substring"
    content = [p for p in parts if any(c.isalnum() for c in p)]
    return content or [text.strip()]
