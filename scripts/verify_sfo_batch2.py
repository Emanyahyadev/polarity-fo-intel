"""
SFO expansion, batch 2 — verify ~24 researched single-family-office candidates against
their OWN websites (same D24/D26 gate: identity match + an explicit single-family
self-identification quote, else SKIP). Candidate pond: European family investment
holdings and US family/impact offices known to run public sites; guessed URLs are safe
because the identity guard rejects any wrong site.

Writes data/adv/sfo_batch2_verified.json for review. No dataset is touched here.
    FIRECRAWL_API_KEY=... LLM_API_KEY=... py -3.12 scripts/verify_sfo_batch2.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

FC = os.environ.get("FIRECRAWL_API_KEY") or os.environ.get("FC", "")
LLM = os.environ.get("LLM_API_KEY", "")

TARGETS = {
    # --- US ---
    "Gates Ventures": "https://www.gatesventures.com/",
    "Lawrence Investments": "https://www.lawrenceinvestments.com/",
    "The Pritzker Organization": "https://www.tpo.com/",
    "Emerson Collective": "https://www.emersoncollective.com/",
    "Ceniarth": "https://ceniarth.co/",
    "Blue Haven Initiative": "https://www.bluehaveninitiative.com/",
    "S-Cubed Capital": "https://www.scubedcapital.com/",
    "Zoma Capital": "https://www.zomacapital.com/",
    "Cherng Family Trust": "https://www.cherngfamilytrust.com/",
    "The Sobrato Organization": "https://www.sobrato.com/",
    "Gurnet Point Capital": "https://www.gurnetpointcapital.com/",
    "Waycrosse": "https://www.waycrosse.com/",
    "Huizenga Group": "https://www.huizengagroup.com/",
    "Meritage Group": "https://www.meritagegroup.com/",
    # --- Europe ---
    "Artémis": "https://www.groupeartemis.com/",
    "Tethys Invest": "https://www.tethysinvest.com/",
    "Dentressangle": "https://www.dentressangle.com/",
    "Famille C": "https://www.famillec.com/",
    "Alta Advisers": "https://www.altaadvisers.com/",
    "Anthos Fund & Asset Management": "https://www.anthosam.com/",
    "Bregal Investments": "https://www.bregal.com/",
    "JAB Holding Company": "https://www.jabholco.com/",
    "Grosvenor": "https://www.grosvenor.com/",
    # --- Asia / other ---
    "Tsao Family Office": "https://www.tsaofamilyoffice.com/",
    "TY Danjuma Family Office": "https://www.tydanjumafo.com/",
}


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


CACHE = Path("data/adv/sfo_batch2_scrape_cache.json")


def deep(url: str) -> str:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if cache.get(url):                    # reuse successful scrapes; retry empty/failed ones
        return cache[url]
    md = scrape(url)
    for p in ("about", "about-us", "who-we-are"):
        if len(md) > 5000:
            break
        more = scrape(url.rstrip("/") + "/" + p)
        if more:
            md += "\n\n" + more
    md = md[:9000]
    cache[url] = md
    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return md


SCHEMA = ('{"site_owner_name":"the name the site presents itself as",'
          '"site_is_about_firm":true/false,'
          '"is_single_family_office":true/false (does the site EXPLICITLY state it invests/manages '
          'the capital or assets of ONE named person or family, with no external clients?),'
          '"family_name":"the named person/family, or null",'
          '"evidence":"exact quote from the site proving the single-family nature, or null",'
          '"hq_city":"or null","hq_country":"or null",'
          '"description":"one factual sentence from the site, or null",'
          '"investment_thesis":"one sentence stated on the site, or null"}')


def extract(name: str, md: str) -> dict:
    from groq import Groq
    sysp = ("You verify whether a scraped website belongs to a named firm and whether the site "
            "EXPLICITLY identifies it as a single-family investment office/holding (managing one "
            "named person's or family's capital; no external clients). Use ONLY facts stated on "
            "the page; never infer. A firm managing several families' or clients' money is NOT "
            "single-family. Only set is_single_family_office=true with an exact supporting quote. "
            "Strict JSON: " + SCHEMA)
    last = None
    for model in ("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant"):
        try:
            r = Groq(api_key=LLM).chat.completions.create(
                model=model,
                temperature=0, max_tokens=500, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": sysp},
                          {"role": "user", "content": f"Named firm: {name}\nSITE:\n{md}"}])
            return json.loads(r.choices[0].message.content or "{}")
        except Exception as exc:
            last = exc
    return {"error": str(last)[:100]}


def main():
    if not FC or not LLM:
        sys.exit("set FIRECRAWL_API_KEY and LLM_API_KEY")
    out = []
    for name, url in TARGETS.items():
        md = deep(url)
        f = extract(name, md) if md else {"error": "no content scraped"}
        ok = bool(md) and f.get("site_is_about_firm") and f.get("is_single_family_office") \
            and f.get("evidence")
        rec = {"name": name, "website": url, "scraped_chars": len(md),
               "verdict": "ADD" if ok else "SKIP", **f}
        out.append(rec)
        print(f"[{rec['verdict']}] {name[:28]:28} | SFO={str(f.get('is_single_family_office')):5}"
              f" | family={str(f.get('family_name'))[:18]:18}"
              f" | {('Q: ' + str(f.get('evidence'))[:70]) if f.get('evidence') else (f.get('error') or 'no self-ID')}",
              flush=True)
        time.sleep(0.3)
    Path("data/adv/sfo_batch2_verified.json").write_text(json.dumps(out, indent=1),
                                                         encoding="utf-8")
    adds = [r["name"] for r in out if r["verdict"] == "ADD"]
    print(f"\n==> {len(adds)}/{len(out)} verified: {adds}")


if __name__ == "__main__":
    main()
