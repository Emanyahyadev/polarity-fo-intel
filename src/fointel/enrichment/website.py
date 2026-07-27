"""
Website enrichment — the authoritative corroboration a firm's own site provides.

For directory-discovered firms (Wikipedia/Wikidata are discovery-only and cannot
verify, per the release gate), the firm's **official website** is the authoritative
source that confirms family-office status, resolves SFO/MFO, and supplies a
description and AUM. Official URLs come from Wikidata P856; Wikipedia's intro text
is used only as cited *background* (never as FO-verification).

Every fetch is snapshotted (content hash) for reproducible provenance.
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup
from pydantic import BaseModel

from ..evidence import EvidenceRef
from ..http import HttpClient
from ..observability import get_logger

log = get_logger("enrichment")

_FO = re.compile(r"family office", re.IGNORECASE)
_SFO = re.compile(r"single[- ]?family office", re.IGNORECASE)
_MFO = re.compile(r"multi[- ]?family office", re.IGNORECASE)
_AUM = re.compile(
    r"(?:aum|assets under management|manages?|oversees?)[^.$]{0,40}"
    r"(\$[\d.,]+\s*(?:billion|million|bn|mn|b|m)\b)", re.IGNORECASE)
_AUM2 = re.compile(r"(\$[\d.,]+\s*(?:billion|million|bn|mn)\b)[^.]{0,30}"
                   r"(?:assets|aum|under management)", re.IGNORECASE)


class WebsiteFacts(BaseModel):
    url: Optional[str] = None
    resolved: bool = False
    fo_language: bool = False           # site describes itself as a family office
    fo_type_hint: Optional[str] = None  # "SFO" / "MFO" / None
    description: Optional[str] = None
    aum_text: Optional[str] = None
    text_excerpt: str = ""


def analyze_text(text: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Pure text analysis: (family-office language, SFO/MFO hint, AUM text). Testable, no I/O."""
    type_hint = "SFO" if _SFO.search(text) else ("MFO" if _MFO.search(text) else None)
    aum = None
    for pat in (_AUM, _AUM2):
        m = pat.search(text)
        if m:
            aum = m.group(1)
            break
    return bool(_FO.search(text)), type_hint, aum


class WebsiteEnricher:
    WD_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    WIKI_API = "https://en.wikipedia.org/w/api.php"

    def __init__(self):
        self.http = HttpClient()
        # a browser-ish UA for firm sites (many reject unknown agents)
        self.web = HttpClient(user_agent="Mozilla/5.0 (compatible; PolarityFOIntel/0.1)",
                              accept="text/html,application/xhtml+xml")

    # -- URL discovery ------------------------------------------------- #
    def wikipedia_title_to_qid(self, title: str) -> Optional[str]:
        data = self.http.get_json(self.WIKI_API, params={
            "action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
            "titles": title, "format": "json"})
        for page in (data.get("query", {}).get("pages", {}) or {}).values():
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                return qid
        return None

    def wikidata_official_site(self, qid: str) -> Optional[str]:
        data = self.http.get_json(self.WD_ENTITY.format(qid=qid))
        claims = (data.get("entities", {}).get(qid, {}) or {}).get("claims", {})
        p856 = claims.get("P856")
        if p856:
            try:
                return p856[0]["mainsnak"]["datavalue"]["value"]
            except (KeyError, IndexError, TypeError):
                return None
        return None

    def wikipedia_intro(self, title: str) -> Optional[str]:
        data = self.http.get_json(self.WIKI_API, params={
            "action": "query", "prop": "extracts", "exintro": "1", "explaintext": "1",
            "titles": title, "format": "json"})
        for page in (data.get("query", {}).get("pages", {}) or {}).values():
            extract = page.get("extract")
            if extract:
                return extract.strip()
        return None

    # -- site fetch ---------------------------------------------------- #
    def fetch_site(self, url: str) -> tuple[WebsiteFacts, Optional[EvidenceRef]]:
        try:
            resp, ref = self.web.get_with_evidence(url, ext="html")
        except Exception as exc:
            log.warning("site fetch failed", extra={"event": "enrich_warn",
                        "source": "website", "url": url, "error": str(exc)})
            return WebsiteFacts(url=url, resolved=False), None

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()

        desc = None
        meta = (soup.find("meta", attrs={"name": "description"})
                or soup.find("meta", attrs={"property": "og:description"}))
        if meta and meta.get("content"):
            desc = meta["content"].strip()[:400]

        fo_language, type_hint, aum = analyze_text(text)
        return WebsiteFacts(
            url=resp.url, resolved=True, fo_language=fo_language,
            fo_type_hint=type_hint, description=desc, aum_text=aum,
            text_excerpt=text[:1500]), ref
