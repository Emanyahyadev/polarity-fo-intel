"""
SEC 13F deep enrichment — principal, AUM, and recent-investment signals.

A family office that files Form 13F-HR discloses, in the filing itself:
  * signatureBlock -> the signing principal's NAME, TITLE, and phone (a real
    decision-maker, on an official SEC filing);
  * summaryPage.tableValueTotal -> the aggregate value of its 13(f) securities
    (an authoritative, dated AUM figure) and the number of positions;
  * the information table -> its equity HOLDINGS. Diffing the latest filing
    against the prior quarter yields genuinely NEW positions = recent investments.

Everything here is parsed from the primary filing on EDGAR, content-hashed for
provenance, and dated by the filing's reporting period. Nothing is inferred: a
firm that does not file 13F simply yields no facts (its principal/AUM stay
`could_not_verify`).
"""

from __future__ import annotations

import html
import re
from typing import Optional

from pydantic import BaseModel

from ..evidence import EvidenceRef
from ..http import HttpClient
from ..observability import get_logger
from .sec import _format_phone

log = get_logger("enrichment")

_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"


class ThirteenFFacts(BaseModel):
    cik: str
    period: Optional[str] = None          # reporting quarter, e.g. "03-31-2026"
    filing_date: Optional[str] = None
    accession: Optional[str] = None
    report_url: Optional[str] = None      # EDGAR filing index (human-viewable)
    principal_name: Optional[str] = None
    principal_title: Optional[str] = None
    principal_phone: Optional[str] = None
    principal_city: Optional[str] = None
    principal_state: Optional[str] = None
    portfolio_value_usd: Optional[int] = None
    position_count: Optional[int] = None
    top_holdings: list[str] = []
    new_holdings: list[str] = []          # issuers present in latest but not prior filing
    content_hash: Optional[str] = None

    @property
    def aum_text(self) -> Optional[str]:
        if not self.portfolio_value_usd:
            return None
        v = self.portfolio_value_usd
        human = (f"${v/1e9:.2f}B" if v >= 1e9 else f"${v/1e6:.1f}M" if v >= 1e6 else f"${v:,}")
        q = f" as of {self.period}" if self.period else ""
        return f"{human} in 13(f) securities{q} (SEC Form 13F, {self.position_count or '?'} positions)"

    @property
    def recent_investments_text(self) -> Optional[str]:
        names = self.new_holdings or self.top_holdings
        if not names:
            return None
        label = "New 13F positions" if self.new_holdings else "Largest 13F holdings"
        q = f" ({self.period})" if self.period else ""
        return f"{label}{q}: " + ", ".join(_titlecase(n) for n in names[:6])


def _titlecase(s: str) -> str:
    return " ".join(w.capitalize() if w.isupper() else w for w in s.split())


def _tag(tag: str, s: str) -> Optional[str]:
    m = re.search(rf"<(?:\w+:)?{tag}\b[^>]*>([^<]+)</(?:\w+:)?{tag}>", s, re.I)
    return html.unescape(m.group(1).strip()) if m else None


def _section(tag: str, s: str) -> str:
    m = re.search(rf"<(?:\w+:)?{tag}\b[^>]*>(.*?)</(?:\w+:)?{tag}>", s, re.I | re.S)
    return m.group(1) if m else ""


def _holdings(info_table_xml: str) -> list[tuple[str, int]]:
    """(issuer, value) per position, from an information table. Value units are as
    filed (whole USD in current EDGAR schema)."""
    out: list[tuple[str, int]] = []
    for block in re.findall(r"<(?:\w+:)?infoTable\b[^>]*>(.*?)</(?:\w+:)?infoTable>",
                            info_table_xml, re.I | re.S):
        issuer = _tag("nameOfIssuer", block)
        val = _tag("value", block)
        if issuer:
            try:
                out.append((issuer.strip(), int(re.sub(r"\D", "", val or "0") or 0)))
            except ValueError:
                out.append((issuer.strip(), 0))
    return out


class ThirteenFEnricher:
    def __init__(self):
        # SEC archives serve XML; a descriptive UA is required by SEC fair-access rules.
        self.http = HttpClient(accept="*/*")

    def _acc_list(self, cik: str) -> list[tuple[str, str]]:
        cik10 = str(cik).lstrip("0").zfill(10)
        d = self.http.get_json(_SUBMISSIONS.format(cik=cik10))
        rec = (d.get("filings") or {}).get("recent") or {}
        forms, accs, dates = rec.get("form", []), rec.get("accessionNumber", []), rec.get("filingDate", [])
        return [(accs[i], dates[i]) for i, f in enumerate(forms) if str(f).startswith("13F-HR")]

    def _info_table_url(self, base: str) -> Optional[str]:
        try:
            items = (self.http.get_json(base + "/index.json").get("directory") or {}).get("item") or []
        except Exception:
            return None
        for it in items:
            name = it.get("name", "")
            if name.lower().endswith(".xml") and name.lower() != "primary_doc.xml" \
                    and not name.lower().startswith("xsl"):
                return base + "/" + name
        return None

    def _issuers(self, base: str) -> set[str]:
        url = self._info_table_url(base)
        if not url:
            return set()
        try:
            return {i for i, _ in _holdings(self.http.get_text(url))}
        except Exception:
            return set()

    def fetch(self, cik: str) -> Optional[tuple[ThirteenFFacts, Optional[EvidenceRef]]]:
        try:
            accs = self._acc_list(cik)
        except Exception as exc:
            log.warning("13f submissions failed", extra={"event": "enrich_warn",
                        "source": "13f", "cik": str(cik), "error": str(exc)})
            return None
        if not accs:
            return None

        cik_int = str(int(str(cik).lstrip("0") or "0"))
        (acc, fdate) = accs[0]
        base = _ARCHIVE.format(cik=cik_int, acc=acc.replace("-", ""))
        try:
            resp, ref = self.http.get_with_evidence(base + "/primary_doc.xml", ext="xml")
            prim = resp.text
        except Exception as exc:
            log.warning("13f primary_doc failed", extra={"event": "enrich_warn",
                        "source": "13f", "cik": str(cik), "error": str(exc)})
            return None

        sig, summ, cover = _section("signatureBlock", prim), _section("summaryPage", prim), _section("coverPage", prim)
        facts = ThirteenFFacts(
            cik=str(cik), accession=acc, filing_date=fdate,
            report_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_int}&type=13F",
            period=_tag("reportCalendarOrQuarter", cover),
            principal_name=_titlecase(_tag("name", sig)) if _tag("name", sig) else None,
            principal_title=_tag("title", sig),
            principal_phone=_format_phone(_tag("phone", sig)),
            principal_city=_tag("city", sig),
            principal_state=_tag("stateOrCountry", sig),
            content_hash=ref.content_hash if ref else None,
        )
        pv, pc = _tag("tableValueTotal", summ), _tag("tableEntryTotal", summ)
        if pv:
            try:
                facts.portfolio_value_usd = int(re.sub(r"\D", "", pv))
            except ValueError:
                pass
        if pc:
            try:
                facts.position_count = int(re.sub(r"\D", "", pc))
            except ValueError:
                pass

        holdings = sorted(_holdings(self.http.get_text(self._info_table_url(base) or base)),
                          key=lambda x: -x[1]) if self._info_table_url(base) else []
        facts.top_holdings = [h for h, _ in holdings[:8]]
        if len(accs) > 1:
            prior_base = _ARCHIVE.format(cik=cik_int, acc=accs[1][0].replace("-", ""))
            prior = self._issuers(prior_base)
            if prior:
                latest = {h for h, _ in holdings}
                facts.new_holdings = sorted(latest - prior)[:8]
        return facts, ref
