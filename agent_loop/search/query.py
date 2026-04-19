"""FTS5 query sanitization — adapted from Hermes Agent.

FTS5's default tokenizer is strict about special characters. This module
sanitizes natural-language queries into safe FTS5 MATCH expressions.
"""

from __future__ import annotations

import re

# Special FTS5 chars that need handling
_SPECIAL = set("+{}()\"^")

# Boolean operators FTS5 understands (must be uppercase in MATCH)
_OPERATORS = {"AND", "OR", "NOT", "NEAR"}


def sanitize_fts5_query(query: str) -> str:
    """Convert a natural-language query into a safe FTS5 MATCH expression.

    Handles:
    - Preserves balanced "quoted phrases"
    - Strips unpaired special chars
    - Collapses *** -> *
    - Removes dangling AND/OR/NOT at boundaries
    - Quotes dotted/hyphenated tokens (else FTS5 splits them: "chat-send" -> "chat" AND "send")
    - CJK detection falls back to LIKE-style (caller should detect and branch)

    Returns an empty string for queries that sanitize to nothing.
    """
    if not query:
        return ""

    # Preserve balanced quoted phrases
    quoted_phrases = []

    def _capture_quote(m):
        quoted_phrases.append(m.group(0))
        return f"\x00Q{len(quoted_phrases) - 1}\x00"

    # Only match balanced pairs
    query = re.sub(r'"[^"]*"', _capture_quote, query)

    # Strip remaining unbalanced quotes and other special chars
    for ch in _SPECIAL:
        query = query.replace(ch, " ")

    # Collapse runs of * to single *
    query = re.sub(r"\*+", "*", query)

    # Tokenize on whitespace
    tokens = query.split()

    cleaned: list[str] = []
    for tok in tokens:
        # Restore quoted phrases
        if tok.startswith("\x00Q"):
            idx = int(tok[2:-1])
            cleaned.append(quoted_phrases[idx])
            continue

        # Upper-case operators stay as-is (treated as FTS5 operators)
        upper = tok.upper()
        if upper in _OPERATORS:
            cleaned.append(upper)
            continue

        # Tokens with dots/hyphens need quoting (FTS5 tokenizer would split them)
        if re.search(r"[.\-]", tok):
            # Escape internal quotes and wrap
            safe = tok.replace('"', "")
            cleaned.append(f'"{safe}"')
            continue

        # Strip any remaining weird chars
        safe = re.sub(r"[^\w*]", "", tok, flags=re.UNICODE)
        if safe:
            cleaned.append(safe)

    # Remove dangling operators at start/end
    while cleaned and cleaned[0].upper() in _OPERATORS:
        cleaned.pop(0)
    while cleaned and cleaned[-1].upper() in _OPERATORS:
        cleaned.pop()

    return " ".join(cleaned)


def has_cjk(text: str) -> bool:
    """Detect CJK characters (FTS5 tokenizer splits these into single chars)."""
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF  # CJK Unified
            or 0x3040 <= code <= 0x309F  # Hiragana
            or 0x30A0 <= code <= 0x30FF  # Katakana
            or 0xAC00 <= code <= 0xD7AF  # Hangul
        ):
            return True
    return False
