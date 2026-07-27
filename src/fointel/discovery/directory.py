"""
Discovery source 4 — curated directory / reference via Wikipedia (curated lens).

The candidate's priority list (Campden Wealth, Family Wealth Report) is paywalled
and its terms restrict programmatic reuse, so for a free-tier, ToS-clean directory
lens we use Wikipedia's Category:Family_offices plus Wikidata. These list *notable*
family offices — heavily single-family (Walton Enterprises, Bezos Expeditions,
Kirkbi, Mousse Partners) — each with an article the enrichment layer can read.

Documented limitation: notability bias (only well-known offices appear).
"""

from __future__ import annotations

from datetime import date
from typing import Iterator

from ..http import HttpClient
from ..observability import get_logger
from ..schema import Candidate, SourceClass
from ..text import norm_name
from .base import DiscoverySource

log = get_logger("pipeline")

# Non-firm pages that appear in the category but are concepts, not family offices.
_SKIP_TITLES = {"family office", "list of family offices", "multi-family office",
                "single-family office"}


class DirectorySource(DiscoverySource):
    source_class = SourceClass.DIRECTORY
    API = "https://en.wikipedia.org/w/api.php"
    CATEGORIES = ("Category:Family_offices", "Category:American_family_offices")
    WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
    FO_QID = "Q751314"  # Wikidata: "family office"

    def __init__(self):
        self.http = HttpClient(user_agent=None, accept="application/json")

    def _wikidata_members(self) -> Iterator[dict]:
        """Instances (incl. subclasses) of 'family office' on Wikidata."""
        query = (
            "SELECT ?item ?itemLabel ?countryLabel WHERE { "
            f"?item wdt:P31/wdt:P279* wd:{self.FO_QID} . "
            "OPTIONAL { ?item wdt:P17 ?country. } "
            'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } } LIMIT 400'
        )
        data = self.http.get_json(self.WIKIDATA_SPARQL, params={"query": query, "format": "json"})
        for row in data.get("results", {}).get("bindings", []):
            label = row.get("itemLabel", {}).get("value", "").strip()
            uri = row.get("item", {}).get("value", "")
            if not label or label.startswith("Q") and label[1:].isdigit():
                continue
            yield {
                "name": label,
                "qid": uri.rsplit("/", 1)[-1] if uri else None,
                "country": row.get("countryLabel", {}).get("value"),
                "uri": uri,
            }

    def _members(self, category: str) -> Iterator[dict]:
        cmcontinue = None
        while True:
            params = {
                "action": "query", "list": "categorymembers", "cmtitle": category,
                "cmlimit": "100", "cmtype": "page", "format": "json",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue
            data = self.http.get_json(self.API, params=params)
            yield from data.get("query", {}).get("categorymembers", [])
            cmcontinue = data.get("continue", {}).get("cmcontinue")
            if not cmcontinue:
                break

    def discover(self, limit: int) -> Iterator[Candidate]:
        seen: set[str] = set()
        yielded = 0

        # Pass 1: Wikipedia categories
        for category in self.CATEGORIES:
            try:
                members = list(self._members(category))
            except Exception as exc:  # a missing category must not kill the whole source
                log.warning("directory category failed", extra={
                    "event": "discover_warn", "source": "directory",
                    "category": category, "error": str(exc)})
                continue
            for member in members:
                title = (member.get("title") or "").strip()
                if not title or title.lower() in _SKIP_TITLES:
                    continue
                key = norm_name(title)
                if not key or key in seen:
                    continue
                seen.add(key)
                yield Candidate(
                    name=title, source_class=self.source_class,
                    source_url="https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                    discovered_at=date.today(), dedup_key=key,
                    raw={"pageid": member.get("pageid"), "category": category,
                         "via": "wikipedia"},
                    hints={"wikipedia_title": title},
                )
                yielded += 1
                if yielded >= limit:
                    return self._done(yielded)

        # Pass 2: Wikidata instances of "family office"
        try:
            wd_members = list(self._wikidata_members())
        except Exception as exc:
            log.warning("directory wikidata failed", extra={
                "event": "discover_warn", "source": "directory", "error": str(exc)})
            wd_members = []
        for member in wd_members:
            name = member["name"]
            key = norm_name(name)
            if not key or key in seen or name.lower() in _SKIP_TITLES:
                continue
            seen.add(key)
            yield Candidate(
                name=name, source_class=self.source_class,
                source_url=member.get("uri"), discovered_at=date.today(), dedup_key=key,
                raw={"qid": member.get("qid"), "via": "wikidata"},
                hints={"country": member.get("country")},
            )
            yielded += 1
            if yielded >= limit:
                return self._done(yielded)
        self._done(yielded)

    @staticmethod
    def _done(count: int) -> None:
        log.info("directory done", extra={"event": "discover_done", "source": "directory",
                                          "count": count})
