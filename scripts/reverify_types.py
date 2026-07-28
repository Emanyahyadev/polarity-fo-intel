"""
Classification re-verification (Phase 4). For every SFO whose single-vs-multi status is
not already established by strong evidence, re-read the firm's OWN website and decide the
type ONLY on an explicit quote. A registered adviser reporting regulatory (client) AUM
cannot be a pure single-family office.

Decision rule (evidence-first, never guess):
  - Multi-Family Office  : site says it serves multiple families / clients (plural), OR the
                           record already carries ADV Item 5.F *regulatory* AUM (= a
                           registered adviser managing external client assets).
  - Single-Family Office : site explicitly serves ONE named family and shows no external
                           clients.
  - Undetermined         : neither is explicitly established.

Writes data/adv/type_reverify.json for review + downstream apply. No dataset is touched.
    FIRECRAWL_API_KEY=... LLM_API_KEY=... py -3.12 scripts/reverify_types.py
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.rag.load import load_records_from_csv                # noqa: E402

FC = os.environ.get("FIRECRAWL_API_KEY") or os.environ.get("FC", "")
LLM = os.environ.get("LLM_API_KEY", "")

# SFOs to re-verify (the directory 4 — Financière Agache/KIRKBI/Korys/Builders Vision —
# already carry explicit single-family quotes and are kept).
TARGETS = {"JFG FAMILY OFFICE", "WE FAMILY OFFICES", "818 FAMILY OFFICE, LLC",
           "FIVE ELEVEN PARTNERS", "LONG FAMILY OFFICE", "GRIT FAMILY OFFICE, LLC",
           "HOLDUN FAMILY OFFICE LLC", "PRIME OPPORTUNITIES INVESTMENT GROUP"}


def scrape(url: str) -> str:
    try:
        r = requests.post("https://api.firecrawl.dev/v1/scrape",
                          headers={"Authorization": f"Bearer {FC}"},
                          json={"url": url, "formats": ["markdown"], "onlyMainContent": True}, timeout=60)
        d = r.json()
        return (d.get("data") or {}).get("markdown", "") if d.get("success") else ""
    except Exception:
        return ""


def deep(url: str) -> str:
    md = scrape(url)
    for p in ("about", "about-us", "who-we-are", "services"):
        if len(md) > 7000:
            break
        m = scrape(url.rstrip("/") + "/" + p)
        if m:
            md += "\n\n" + m
    return md[:9000]


SCHEMA = ('{"serves":"one family|multiple families or clients|unclear",'
          '"type":"Single-Family Office|Multi-Family Office|Undetermined",'
          '"evidence":"exact quote from the site proving single vs multi, or null",'
          '"is_family_office":true/false}')


def extract(name, md, has_reg_aum):
    from groq import Groq
    sysp = ("Decide whether this family-office website describes a SINGLE-family office (serves "
            "ONE family, no external clients) or a MULTI-family office (serves multiple families "
            "or clients). Use ONLY explicit statements on the page; never infer. If it is not "
            "explicitly clear, type=Undetermined and evidence=null. A firm that mentions serving "
            "'families' (plural), 'clients', or 'high-net-worth individuals' is Multi-Family. "
            "Return strict JSON: " + SCHEMA)
    try:
        r = Groq(api_key=LLM).chat.completions.create(
            model=os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
            temperature=0, max_tokens=400, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": sysp},
                      {"role": "user", "content": f"Firm: {name}\nRegistered adviser with regulatory AUM: "
                       f"{has_reg_aum}\nSITE:\n{md}"}])
        return json.loads(r.choices[0].message.content or "{}")
    except Exception as e:
        return {"error": str(e)[:80]}


def main():
    if not FC or not LLM:
        sys.exit("set FIRECRAWL_API_KEY and LLM_API_KEY")
    recs = {r.name.upper().strip(): r for r in load_records_from_csv()}
    out = []
    for key in TARGETS:
        r = recs.get(key)
        if not r:
            print("  MISSING:", key); continue
        has_reg = bool(r.estimated_aum and "regulatory AUM" in (r.estimated_aum or ""))
        md = deep(r.website) if r.website else ""
        f = extract(r.name, md, has_reg) if md else {"error": "no scrape"}
        # decision
        site_type = f.get("type"); ev = f.get("evidence")
        if has_reg and site_type != "Single-Family Office":
            final, reason = "Multi-Family Office", "ADV Item 5.F regulatory AUM => registered adviser serving clients"
        elif site_type == "Single-Family Office" and ev:
            final, reason = "Single-Family Office", "explicit single-family quote"
        elif site_type == "Multi-Family Office" and ev:
            final, reason = "Multi-Family Office", "explicit multi-family/client quote"
        else:
            final, reason = "Undetermined", "single vs multi not explicitly established"
        out.append({"name": r.name, "website": r.website, "current": r.fo_type.value,
                    "has_reg_aum": has_reg, "site_type": site_type, "serves": f.get("serves"),
                    "evidence": ev, "final_type": final, "reason": reason,
                    "scraped_chars": len(md)})
        print(f"[{r.fo_type.value[:3]}->{final[:3]}] {r.name[:30]:30} serves={str(f.get('serves'))[:26]:26} :: {reason}")
        if ev:
            print(f"        quote: \"{str(ev)[:120]}\"")
        time.sleep(0.3)
    Path("data/adv/type_reverify.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    from collections import Counter
    print("\nfinal types:", dict(Counter(o["final_type"] for o in out)))


if __name__ == "__main__":
    main()
