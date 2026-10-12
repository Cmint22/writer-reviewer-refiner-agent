"""
Small, deterministic text-hygiene helpers shared by the agents and the checklist.

LLM output (and text copied from a terminal) can carry characters that are
invisible to a human reader but break copy-paste: zero-width spaces, a
byte-order mark, a non-breaking space, stray control characters. They are
removed/normalised in plain Python — never left to an LLM to notice.
"""
from __future__ import annotations

import unicodedata

_KEEP_CONTROL = {"\n", "\r", "\t"}


def _is_invisible(ch: str) -> bool:
    """True for characters that look like nothing (or like a plain space) but are not."""
    if ch == " ":
        return False
    cat = unicodedata.category(ch)
    if cat in ("Cf", "Zs", "Zl", "Zp"):  # format chars (U+200B, U+FEFF...), exotic spaces (NBSP...)
        return True
    return cat == "Cc" and ch not in _KEEP_CONTROL


def find_invisible_chars(text: str) -> list[tuple[int, str]]:
    """Return [(line_number, 'U+200B ZERO WIDTH SPACE'), ...] for every invisible character."""
    found: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines() or [text], start=1):
        for ch in line:
            if _is_invisible(ch):
                found.append((line_no, f"U+{ord(ch):04X} {unicodedata.name(ch, 'CONTROL')}"))
    return found


def sanitize_text(text: str) -> str:
    """
    Normalise LLM output:
      * Unicode NFC (so a decomposed 'ẩ' equals a composed one);
      * drop zero-width / format / control characters;
      * turn non-breaking and other exotic spaces into a normal space.
    """
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", text):
        if not _is_invisible(ch):
            out.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat == "Zs":
            out.append(" ")
        elif cat in ("Zl", "Zp"):
            out.append("\n")
        # Cf / Cc: dropped
    return "".join(out)
