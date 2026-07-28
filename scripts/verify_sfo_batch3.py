"""
SFO expansion, batch 3 (final pre-deadline batch) — same gate as every prior addition.
Adds a plain-HTTP fallback for sites Firecrawl fails on (several batch-2 candidates were
never actually read), and retries those alongside seven newly researched candidates.
    FIRECRAWL_API_KEY=... LLM_API_KEY=... py -3.12 scripts/verify_sfo_batch3.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

FC = os.environ.get("FIRECRAWL_API_KEY") or os.environ.get("FC", "")
LLM = os.environ.get("LLM_API_KEY", "")

TARGETS = {
    # retries: batch-2 scrape failures with known-plausible self-descriptions
    "Declaration Partners": "https://www.declarationpartners.com/",
    "Ceniarth": "https://ceniarth.co/",
    "Tsao Family Office": "https://www.tsaofamilyoffice.com/",
    "TY Danjuma Family Office": "https://www.tydanjumafo.com/",
    "Tethys Invest": "https://www.tethysinvest.com/",
    "Famille C": "https://www.famillec.com/",
    "S-Cubed Capital": "https://www.scubedcapital.com/",
    "Alta Advisers": "https://www.altaadvisers.com/",
    # new researched candidates
    "Ferd": "https://www.ferd.no/en/",
    "Horizons Ventures": "https://www.horizonsventures.com/",
    "Catamaran": "https://www.catamaran.in/",
    "Premji Invest": "https://www.premjiinvest.com/",
    "MacAndrews & Forbes": "https://www.macandrewsandforbes.com/",
    "NNS Group": "https://www.nnsgroup.com/",
    "AQTON": "https://www.aqton.de/",
}

CACHE = Path("data/adv/sfo_batch3_scrape_cache.json")
_TAGS = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.S | re.I)


def plain_fetch(url: str) -> str:
    """Fallback for sites Firecrawl fails on: direct fetch + tag strip (static sites)."""
    try:
        r = requests.get(url, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
        if r.status_code != 200:
            return ""
        text = _TAGS.sub(" ", r.text)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""


def firecrawl(url: str) -> str:
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
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if cache.get(url):
        return cache[url]
    md = firecrawl(url) or plain_fetch(url)
    if md and len(md) < 5000:
        for p in ("about", "about-us", "who-we-are"):
            more = firecrawl(url.rstrip("/") + "/" + p)
            if more:
                md += "\n\n" + more
                break
    md = md[:9000]
    if md:
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
                model=model, temperature=0, max_tokens=500,
                response_format={"type": "json_object"},
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
        print(f"[{rec['verdict']}] {name[:26]:26} | SFO={str(f.get('is_single_family_office')):5}"
              f" | {('Q: ' + str(f.get('evidence'))[:75]) if f.get('evidence') else (f.get('error') or 'no self-ID')}",
              flush=True)
        time.sleep(0.3)
    Path("data/adv/sfo_batch3_verified.json").write_text(json.dumps(out, indent=1),
                                                         encoding="utf-8")
    adds = [r["name"] for r in out if r["verdict"] == "ADD"]
    print(f"\n==> {len(adds)}/{len(out)} verified: {adds}")


if __name__ == "__main__":
    main()
