"""Small text-normalisation utilities shared across layers (no I/O, pure functions)."""

from __future__ import annotations

import re

_SUFFIXES = re.compile(
    r"\b(llc|lp|llp|inc|ltd|co|corp|group|management|mgmt|capital|partners|"
    r"family office|office|advisors|advisers|holdings|trust|foundation)\b"
)


def norm_name(name: str) -> str:
    """Normalise a firm name for de-duplication across sources.

    'The Smith Family Office, LLC' and 'Smith Family Office' collapse to the same key.
    """
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = _SUFFIXES.sub(" ", n)
    n = re.sub(r"\bthe\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()
