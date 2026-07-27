"""Small text-normalisation utilities shared across layers (no I/O, pure functions)."""

from __future__ import annotations

import re

# Only LEGAL-ENTITY suffixes are stripped. Descriptive words that distinguish
# firms (capital, partners, group, management, holdings, family office, ...) are
# DELIBERATELY kept: stripping them silently merged distinct firms
# ("Blue Capital" vs "Blue Partners"). See gate-review finding A4 / DecisionLog D14.
_LEGAL_SUFFIX = re.compile(
    r"\b(llc|lp|llp|inc|incorporated|ltd|limited|co|corp|corporation|company|"
    r"plc|pllc|gmbh|ag|sa|nv|bv|spa|pte|pty)\b"
)


def norm_name(name: str) -> str:
    """Conservative firm-name key for candidate comparison.

    'The Smith Family Office, LLC' -> 'smith family office'
    'Smith Family Office'          -> 'smith family office'   (same firm)
    'Duquesne Family Office'       != 'Duquesne'               (distinct)
    'Blue Capital'                 != 'Blue Partners'          (distinct)

    Never used alone to MERGE records — entity resolution requires identifiers or
    name+geography agreement (see fointel.entity_resolution).
    """
    n = name.lower().strip()
    n = re.sub(r"[.,]", "", n)          # "L.L.C." -> "llc"
    n = re.sub(r"[^a-z0-9 ]+", " ", n)  # other punctuation -> space
    n = re.sub(r"\bthe\b", " ", n)
    n = _LEGAL_SUFFIX.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()
