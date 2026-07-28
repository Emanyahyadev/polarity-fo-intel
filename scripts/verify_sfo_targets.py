"""
SFO expansion, phase 1 — VERIFY notable single-family-office candidates against their
OWN websites before any record is written (the D24 standard: the site must clearly
belong to the named firm AND explicitly self-identify its single-family nature, with an
exact quote). Candidates come from the curated/notable-reference lens (Wikipedia
Category:Family_offices and the project's existing candidate pool); Wikipedia remains
discovery-only — the firm's own site is the verification.

Writes data/adv/sfo_targets_verified.json for human review. No dataset is touched here.
    FIRECRAWL_API_KEY=... LLM_API_KEY=... py -3.12 scripts/verify_sfo_targets.py
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

# name -> official-site candidate URL. The identity guard rejects any wrong site.
TARGETS = {
    "MSD Capital, L.P.": "https://www.msdcapital.com/",
    "Willett Advisors LLC": "https://www.willettadvisors.com/",
    "Bezos Expeditions": "https://www.bezosexpeditions.com/",
    "Ballmer Group": "https://www.ballmergroup.org/",
    "Mousse Partners": "https://www.moussepartners.com/",
    "Declaration Partners": "https://www.declarationpartners.com/",
    "Pontegadea": "https://www.pontegadea.com/",
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


def deep(url: str) -> str:
    md = scrape(url)
    for p in ("about", "about-us", "who-we-are", "en"):
        if len(md) > 6000:
            break
        more = scrape(url.rstrip("/") + "/" + p)
        if more:
            md += "\n\n" + more
    return md[:9000]


SCHEMA = ('{"site_owner_name":"the name the site presents itself as",'
          '"site_is_about_firm":true/false,'
          '"is_single_family_office":true/false (does the site EXPLICITLY state it manages the '
          'assets/capital of ONE named person or family, with no external clients?),'
          '"family_name":"the named person/family, or null",'
          '"evidence":"exact quote from the site proving the single-family nature, or null",'
          '"hq_city":"or null","hq_country":"or null",'
          '"principal_name":"or null","principal_title":"or null",'
          '"description":"one factual sentence from the site, or null",'
          '"investment_thesis":"one sentence stated on the site, or null"}')


def extract(name: str, md: str) -> dict:
    from groq import Groq
    sysp = ("You verify whether a scraped website belongs to a named firm and whether the site "
            "EXPLICITLY identifies it as a single-family investment office (managing one named "
            "person's or family's capital, no external clients). Use ONLY facts stated on the "
            "page; never infer. If the site is a different company, site_is_about_firm=false. "
            "Only set is_single_family_office=true with an exact supporting quote. Strict JSON: "
            + SCHEMA)
    try:
        r = Groq(api_key=LLM).chat.completions.create(
            model=os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
            temperature=0, max_tokens=500, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": sysp},
                      {"role": "user", "content": f"Named firm: {name}\nSITE:\n{md}"}])
        return json.loads(r.choices[0].message.content or "{}")
    except Exception as exc:
        return {"error": str(exc)[:100]}


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
        print(f"[{rec['verdict']}] {name[:26]:26} | owner={str(f.get('site_owner_name'))[:24]:24}"
              f" | SFO={f.get('is_single_family_office')} | family={str(f.get('family_name'))[:20]}")
        if f.get("evidence"):
            print(f"      quote: \"{str(f.get('evidence'))[:120]}\"")
        if f.get("error"):
            print(f"      error: {f['error']}")
        time.sleep(0.3)
    Path("data/adv/sfo_targets_verified.json").write_text(json.dumps(out, indent=1),
                                                          encoding="utf-8")
    adds = [r["name"] for r in out if r["verdict"] == "ADD"]
    print(f"\n==> {len(adds)}/{len(out)} verified as genuine SFOs on their own sites: {adds}")


if __name__ == "__main__":
    main()
