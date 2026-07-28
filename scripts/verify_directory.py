"""
Phase 1 of discovery-diversity: VERIFY non-SEC (Wikipedia/Wikidata-discovered) family
offices against their OWN website before any record is written.

Wikipedia/Wikidata is discovery-only under our gates (community-edited). The official
website comes from Wikidata P856 (a curated, sourced pointer); the firm's own site is
the authoritative verification + Rule-2 evidence. To avoid the generic-name / wrong-site
failure we just corrected, a record is only proposed when the site (a) clearly belongs
to the firm and (b) explicitly self-describes as a family office WITH an exact quote.

Writes data/adv/directory_verified.json for review. No dataset is touched here.
    FIRECRAWL_API_KEY=... LLM_API_KEY=... py -3.12 scripts/verify_directory.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

FC = os.environ.get("FIRECRAWL_API_KEY") or os.environ.get("FC", "")
LLM = os.environ.get("LLM_API_KEY", "")


def scrape(url: str) -> str:
    try:
        r = requests.post("https://api.firecrawl.dev/v1/scrape",
                          headers={"Authorization": f"Bearer {FC}"},
                          json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
                          timeout=60)
        d = r.json()
        return (d.get("data") or {}).get("markdown", "") if d.get("success") else ""
    except Exception:
        return ""


def deep_scrape(url: str) -> str:
    md = scrape(url)
    for p in ("about", "about-us", "who-we-are"):
        if len(md) > 6000:
            break
        more = scrape(url.rstrip("/") + "/" + p)
        if more:
            md += "\n\n" + more
    return md[:9000]


_SCHEMA = ('{"site_owner_name":"the name the site presents itself as",'
           '"site_is_about_firm":true/false (does the site clearly belong to the named firm '
           'or its stated alias?),"is_family_office":true/false,'
           '"fo_evidence":"exact quote from the site proving family-office status, or null",'
           '"fo_type":"Single-Family Office|Multi-Family Office|Undetermined",'
           '"principal_name":"or null","principal_title":"or null",'
           '"hq_city":"or null","hq_country":"or null",'
           '"description":"one factual sentence from the site, or null",'
           '"investment_thesis":"one sentence stated on the site, or null",'
           '"sectors":["only if explicitly listed"]}')


def extract(name: str, md: str) -> dict:
    from groq import Groq
    sysp = ("You verify whether a scraped website belongs to a named family office and "
            "states so. Use ONLY facts explicitly on the page; never infer or invent. If the "
            "site is clearly a DIFFERENT company than the named firm, set site_is_about_firm "
            "false. Only set is_family_office true if the page explicitly describes a family "
            "office (single or multi), and then give the exact fo_evidence quote. Strict JSON: "
            + _SCHEMA)
    try:
        r = Groq(api_key=LLM).chat.completions.create(
            model=os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
            temperature=0, max_tokens=500, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": sysp},
                      {"role": "user", "content": f"Named firm: {name}\nSITE:\n{md}"}])
        return json.loads(r.choices[0].message.content or "{}")
    except Exception as exc:
        return {"error": str(exc)[:80]}


def edgar_check(name: str) -> dict:
    """Independent authoritative cross-check: does the firm appear in SEC EDGAR full-text?"""
    try:
        q = name.split(",")[0]
        r = requests.get("https://efts.sec.gov/LATEST/search-index",
                         params={"q": f'"{q}"'},
                         headers={"User-Agent": "FO-Intel-research emanyahyadev@gmail.com"},
                         timeout=20)
        hits = r.json().get("hits", {}).get("total", {}).get("value", 0)
        return {"edgar_hits": hits}
    except Exception:
        return {"edgar_hits": None}


def main() -> None:
    if not FC or not LLM:
        sys.exit("set FIRECRAWL_API_KEY (or FC) and LLM_API_KEY")
    resolved = json.loads(Path("data/adv/directory_resolve.json").read_text())
    todo = [c for c in resolved if c.get("website")]
    print(f"verifying {len(todo)} directory candidates with official websites\n")
    out = []
    for c in todo:
        name, site = c["name"], c["website"]
        md = deep_scrape(site)
        facts = extract(name, md) if md else {"error": "no content scraped"}
        edg = edgar_check(name)
        ok = bool(md) and facts.get("site_is_about_firm") and facts.get("is_family_office") \
            and facts.get("fo_evidence")
        rec = {"name": name, "qid": c.get("qid"), "website": site,
               "wd_country": c.get("country"), "scraped_chars": len(md),
               "edgar_hits": edg.get("edgar_hits"), "verdict": "ADD" if ok else "SKIP",
               **facts}
        out.append(rec)
        print(f"[{rec['verdict']}] {name[:30]:30} | owner={str(facts.get('site_owner_name'))[:28]:28}"
              f" | FO={facts.get('is_family_office')} type={facts.get('fo_type')}"
              f" | edgar={edg.get('edgar_hits')}")
        if facts.get("fo_evidence"):
            print(f"        quote: \"{str(facts.get('fo_evidence'))[:110]}\"")
        time.sleep(0.3)
    Path("data/adv/directory_verified.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    adds = [r for r in out if r["verdict"] == "ADD"]
    print(f"\n==> {len(adds)}/{len(out)} verify as family offices from their own site")
    print("    ADD:", [r["name"] for r in adds])


if __name__ == "__main__":
    main()
