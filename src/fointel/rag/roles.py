"""
Principal role labels — bounded by evidence, never by guess (Stage-2 Correction 10).

The product shows a "principal" for records that carry a named person. The review
finding was that a "principal" label can be larger than the evidence: for a firm
that files SEC Form 13F the name is the filing *signatory*, which may be legal,
compliance, operations, or external — not necessarily a decision-maker.

This module derives an HONEST role label from which verification source actually
proved the person, so the prover a record names:

  * SEC EDGAR 13F / SC filing  -> "filing signatory (13F)"   (proved by signature block)
  * SEC IAPD / Form ADV        -> "registered control person (ADV)"
  * Firm website / directory   -> "listed representative (website)"
  * otherwise                  -> "named person (source not recorded)"

A label never asserts "owner", "CEO", "decision-maker", or any role the source
path did not establish.
"""

from __future__ import annotations

from ..schema import SourceClass

_ROLE_BY_SOURCE = [
    # SEC EDGAR 13F / SC filing: the person is the signatory on the filing.
    (SourceClass.SEC_EDGAR, "filing signatory (13F)"),
    # SEC IAPD / Form ADV registration: the person is named on the ADV.
    (SourceClass.SEC_IAPD, "registered person (Form ADV)"),
    # Firm website / directory: the person is listed by the firm itself.
    (SourceClass.FIRM_SITE, "listed person (website)"),
    (SourceClass.NEWS, "mentioned in news"),
    (SourceClass.DIRECTORY, "listed in directory"),
    (SourceClass.IRS_990PF, "listed on IRS 990-PF"),
]


def principal_role(sources: list) -> str:
    """Return an evidence-bounded role label for a record's named principal.

    `sources` is the record's ``verification_sources`` (an iterable of
    SourceRef-like objects exposing ``source_class``). The most authoritative
    source class that could prove the person wins. A principal with no sources
    is labeled candidly rather than guessed.
    """
    SK_EDGAR = SourceClass.SEC_EDGAR.value
    SK_IAPD = SourceClass.SEC_IAPD.value
    priority = {SK_EDGAR: 0, SK_IAPD: 1, SourceClass.FIRM_SITE.value: 2,
                SourceClass.NEWS.value: 3, SourceClass.DIRECTORY.value: 4,
                SourceClass.IRS_990PF.value: 5}
    best = None
    best_rank = 99
    for s in sources or []:
        cls = getattr(s, "source_class", None)
        if cls is None:
            continue
        key = cls.value if hasattr(cls, "value") else str(cls)
        rank = priority.get(key)
        if rank is not None and rank < best_rank:
            best_rank = rank
            best = key
    if best is None:
        return "named person (source not recorded)"
    for (cls, label) in _ROLE_BY_SOURCE:
        if (cls.value if hasattr(cls, "value") else str(cls)) == best:
            return label
    return "named person"