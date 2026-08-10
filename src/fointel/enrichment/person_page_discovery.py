"""
PROTOTYPE — page-driven person discovery. NOT wired into production yet.

Existing PersonContactEnricher requires a principal_name_hint sourced from
SEC 13F/ADV before it will look at a team page at all — so a non-SEC family
office with a public, real team page never enters person discovery, no
matter how clearly it names its founder. This module tests the opposite
direction: given only a website, find candidate decision-makers directly
from the site's own team/leadership pages, with no name supplied in advance.

Deliberately conservative. A "verified_decision_maker" requires ALL of:
  - a name-shaped token sequence (2-3 capitalized words)
  - a decision-maker-relevant title within the same block
  - a contact signal (mailto: email or a personal /in/ LinkedIn link)
    anchored in the SAME block as the name — not merely present anywhere
    on the page, which would risk attributing another employee's contact
    to this person.
Anything with a name+title but no block-local contact is
"possible_decision_maker", never silently upgraded. No email pattern is
ever generated; only a mailto: link actually present in the HTML counts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

_TITLE_KW = re.compile(
    r"\b(founder|co-?founder|chairman|chief investment officer|\bcio\b|"
    r"managing partner|managing director|general partner|principal|"
    r"chief executive|\bceo\b|president|trustee|investment director|"
    r"head of investments?|partner|director of investments?)\b", re.I)

_NAV_JUNK = re.compile(
    r"\b(cookie|privacy|copyright|all rights|menu|navigation|subscribe|"
    r"newsletter|terms of|log ?in|sign ?in|404|not found)\b", re.I)

_GENERIC_LOCALPART = re.compile(
    r"^(info|contact|office|hello|admin|mail|invest|connect|enquir|"
    r"family[- ]?office|reception|manage|team|welcome|general|hr|media|"
    r"support|sales)@", re.I)

_TEAM_PATHS = ("team", "our-team", "about", "about-us", "leadership",
              "people", "investment-team", "management", "who-we-are")


@dataclass
class CandidatePerson:
    name: str
    title: str
    email: str | None = None
    linkedin: str | None = None
    block_text: str = ""
    source_url: str = ""
    verdict: str = "insufficient_evidence"  # verified_decision_maker | possible_decision_maker


_NAME_ONLY_RE = re.compile(r"^[A-Z][a-zà-ÿ'\-]{1,20}(?:\s+[A-Z][a-zà-ÿ'\-]{1,20}){1,2}\.?$")


def _is_name_shaped(text: str) -> bool:
    """Strict: the ENTIRE string (a heading's own text, nothing appended) must
    look like a name — 2-3 capitalized words, nothing else. This is the fix for
    the free-text version, which matched 'Compliance Officer Mr' and similar
    title/boilerplate fragments as if they were names because it searched
    anywhere in a paragraph instead of requiring a dedicated name element."""
    t = text.strip()
    if not (4 <= len(t) <= 40):
        return False
    if _TITLE_KW.search(t) or _NAV_JUNK.search(t):
        return False
    return bool(_NAME_ONLY_RE.match(t))


def _name_headings(soup: BeautifulSoup):
    """Elements whose OWN text (heading tags, or short bold/strong/span name
    labels) is name-shaped — the structural anchor a real team-card uses,
    instead of scanning loose paragraph text for any capitalized phrase."""
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b"]):
        text = tag.get_text(" ", strip=True)
        if _is_name_shaped(text):
            yield tag, text


def _card_container(name_tag, soup: BeautifulSoup):
    """The smallest ancestor that plausibly bounds ONE person's card. Walk up
    from the name element, but stop the INSTANT the growing container would
    also contain another person's name-heading — that means we have crossed
    from "this person's card" into "the whole team grid", and a mailto/title
    search from there would misattribute a sibling's contact. This was the
    real bug: bounding by character count alone let two adjacent cards merge
    into one container whenever their combined bio text was still short."""
    all_name_tags = {t for t, _ in _name_headings(soup)}
    node = name_tag
    best = name_tag.parent
    for _ in range(5):
        if node.parent is None:
            break
        node = node.parent
        other_names_here = sum(1 for t in all_name_tags
                               if t is not name_tag and t in node.descendants)
        if other_names_here > 0:
            break  # this ancestor now spans >=2 people — stop, keep the last safe one
        best = node
    return best


def extract_candidates(html: str, page_url: str) -> list[CandidatePerson]:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        t.decompose()

    seen_names: set[str] = set()
    results: list[CandidatePerson] = []

    for name_tag, name in _name_headings(soup):
        if name in seen_names:
            continue
        container = _card_container(name_tag, soup)
        # title/contact must be found WITHIN this one card, never borrowed
        # from a sibling card or the page at large.
        card_text = container.get_text(" ", strip=True)
        title_m = _TITLE_KW.search(card_text.replace(name, "", 1))
        if not title_m:
            continue  # no decision-maker-relevant title anchored to THIS card -> skip
        title = title_m.group(0)

        # Card-local contact only — a mailto: or /in/ link inside THIS SAME
        # bounded card, never borrowed from a sibling card or page footer.
        # This is the exact fix for the Cervin false-attribution: emails now
        # can only bind to the card whose own name-heading anchors them.
        email = None
        for a in container.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("mailto:"):
                candidate_email = href[7:].split("?")[0].strip()
                # A generic role inbox (info@, contact@, ...) is never a route to
                # THIS specific named person, even when it is the only mailto
                # link correctly scoped to their own card — the standard is about
                # who the mailbox belongs to, not merely where the link sits.
                if _GENERIC_LOCALPART.match(candidate_email):
                    continue
                email = candidate_email
                break
        linkedin = None
        for a in container.find_all("a", href=True):
            m = re.search(r"linkedin\.com/in/([A-Za-z0-9_\-]+)", a["href"])
            if m:
                linkedin = f"https://www.linkedin.com/in/{m.group(1)}"
                break

        verdict = "verified_decision_maker" if (email or linkedin) else "possible_decision_maker"
        seen_names.add(name)
        results.append(CandidatePerson(name=name, title=title, email=email,
                                       linkedin=linkedin, block_text=card_text[:300],
                                       source_url=page_url, verdict=verdict))
    return results


def discover_people(website_enricher, base_url: str) -> tuple[list[CandidatePerson], list[str]]:
    """Fetch a bounded set of team/about pages from `base_url` and extract
    candidates. Returns (people, pages_checked). No name is supplied — this
    is the entire point of the prototype."""
    base = base_url.rstrip("/")
    pages_checked: list[str] = []
    all_people: list[CandidatePerson] = []
    for path in _TEAM_PATHS:
        url = f"{base}/{path}"
        try:
            resp = website_enricher.web.get(url)
        except Exception:
            continue
        pages_checked.append(url)
        people = extract_candidates(resp.text, str(resp.url) or url)
        all_people.extend(people)
        if len(pages_checked) >= 4 and all_people:
            break  # bounded — stop once we have signal, don't crawl the whole site
    return all_people, pages_checked
