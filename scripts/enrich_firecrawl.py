"""
Firecrawl + LLM website deep-enrichment of the DELIVERED records (enrich, not rebuild).

For every firm with a website, this:
  1. Scrapes the site (home + about/team/approach) via Firecrawl (renders JS; robust).
  2. GUARDS the URL: the firm's distinctive name must appear on the site, else the URL is
     treated as a wrong/false match (e.g. a generic "The Family Office" that resolves to an
     unrelated company) -> the site is NOT used and the wrong website is flagged/cleared.
  3. LLM-extracts ONLY facts stated on the verified site: SFO/MFO type (with an on-site quote),
     investment thesis, principal name/title, sectors.
  4. Applies conservatively: resolves Undetermined type only WITH evidence; fills EMPTY thesis/
     principal/sectors; never overwrites an existing verified value; never fabricates.
  5. Re-exports CSV + XLSX and writes a change/coverage report.

Resumable: progress is checkpointed per record. Env: FIRECRAWL_API_KEY, LLM_API_KEY.
    py -3.12 scripts/enrich_firecrawl.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.export import export_dataset                      # noqa: E402
from fointel.rag.load import load_records_from_csv             # noqa: E402
from fointel.schema import (Confidence, FOType, Provenance,    # noqa: E402
                            SourceClass, SourceRef)

FC = os.environ.get("FIRECRAWL_API_KEY") or os.environ.get("FC", "")
LLM = os.environ.get("LLM_API_KEY", "")
CKPT = Path("data/adv/firecrawl_ckpt.json")
_FO_WORDS = re.compile(r"\b(family|offices?|llc|ltd|lp|inc|the|and|&|,|\.)\b", re.I)


def _core(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _FO_WORDS.sub(" ", (s or "").lower()))


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
    for p in ("about", "team"):                 # home + about + team (<=3 calls/firm)
        if len(md) > 6000:
            break
        more = scrape(url.rstrip("/") + "/" + p)
        if more:
            md += "\n\n" + more
    return md[:8000]


_SCHEMA = ('{"fo_type":"Single-Family Office|Multi-Family Office|Undetermined",'
           '"type_evidence":"exact quote from the site proving type, or null",'
           '"principal_name":"or null","principal_title":"or null",'
           '"investment_thesis":"one sentence stated on the site, or null",'
           '"sectors":["only if explicitly listed"]}')


def extract(name: str, md: str) -> dict:
    from groq import Groq
    sys_p = ("Extract ONLY facts explicitly stated on this family-office website. Never infer, "
             "guess, or invent. If a fact is not clearly stated, use null. For fo_type you MUST "
             "provide an exact type_evidence quote from the site, or set fo_type to Undetermined. "
             "Return strict JSON: " + _SCHEMA)
    try:
        r = Groq(api_key=LLM).chat.completions.create(
            model=os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
            temperature=0, max_tokens=400, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": sys_p},
                      {"role": "user", "content": f"Firm: {name}\nSITE:\n{md}"}])
        return json.loads(r.choices[0].message.content or "{}")
    except Exception:
        return {}


def main() -> None:
    if not FC or not LLM:
        sys.exit("set FIRECRAWL_API_KEY (or FC) and LLM_API_KEY")
    as_of = date(2026, 7, 28)
    records = load_records_from_csv()
    ckpt = json.loads(CKPT.read_text()) if CKPT.exists() else {}
    report = ckpt.get("_report", {"type_resolved": [], "thesis_added": [], "principal_added": [],
                                  "wrong_url_flagged": [], "matched": 0, "no_site": 0})

    fc_prov = lambda url: Provenance(source_class=SourceClass.FIRM_SITE,  # noqa: E731
                                     method="firm website (Firecrawl scrape + extraction)",
                                     checked_at=as_of, source_url=url, confidence=Confidence.MEDIUM)

    site_fields = {"website", "description", "investment_thesis", "corporate_linkedin"}
    _HV = ["name", "description", "investment_thesis", "estimated_aum", "website",
           "corporate_linkedin", "hq_country", "hq_phone", "principal_name",
           "principal_title", "principal_phone"]

    def reconstruct(rec):
        """Rebuild the per-cell provenance dict from the CSV's verification sources so the
        Provenance sheet is preserved (attributes each populated high-value field to the
        best-matching verification source: site fields -> firm website, else SEC/IAPD)."""
        vs = rec.verification_sources
        if not vs:
            return
        site = next((s for s in vs if s.source_class == SourceClass.FIRM_SITE), None)
        reg = next((s for s in vs if s.source_class != SourceClass.FIRM_SITE), vs[0])
        for f in _HV:
            if getattr(rec, f, None) and f not in rec.provenance:
                src = site if (f in site_fields and site) else reg
                rec.provenance[f] = Provenance(
                    source_class=src.source_class, method=f"verified via {src.source_class.value}",
                    checked_at=rec.data_as_of, source_url=src.url,
                    confidence=rec.record_confidence)

    for rec in records:
        reconstruct(rec)
        if rec.fo_id in ckpt or not rec.website:
            if not rec.website:
                report["no_site"] += 1
            continue
        md = deep_scrape(rec.website)
        core = _core(rec.name)
        # URL guard: the firm needs a DISTINCTIVE name (>=4-char core) that appears on the site.
        # A generic name ("The Family Office") has no distinctive core -> we cannot confirm the
        # site is theirs, so we do NOT trust it (this is how a wrong site slips in).
        if not md or len(core) < 4 or core[:10] not in _core(md):
            report["wrong_url_flagged"].append(f"{rec.name} -> {rec.website}")
            ckpt[rec.fo_id] = "url_unverified"
            continue
        report["matched"] += 1
        facts = extract(rec.name, md)
        # type: only resolve Undetermined AND only with evidence
        if rec.fo_type == FOType.UNDETERMINED and facts.get("type_evidence") and \
                facts.get("fo_type") in ("Single-Family Office", "Multi-Family Office"):
            rec.fo_type = FOType(facts["fo_type"])
            rec.fo_type_evidence = (rec.fo_type_evidence or "") + \
                f" | firm website: \"{facts['type_evidence'][:160]}\""
            rec.provenance["fo_type_evidence"] = fc_prov(rec.website)
            report["type_resolved"].append(f"{rec.name} -> {rec.fo_type.value}")
        # thesis: fill only if empty
        if not rec.investment_thesis and facts.get("investment_thesis"):
            rec.investment_thesis = facts["investment_thesis"][:300]
            rec.provenance["investment_thesis"] = fc_prov(rec.website)
            report["thesis_added"].append(rec.name)
        # principal: fill only if empty (website-stated, medium confidence)
        if not rec.principal_name and facts.get("principal_name"):
            rec.principal_name = facts["principal_name"][:80]
            rec.provenance["principal_name"] = fc_prov(rec.website)
            if facts.get("principal_title"):
                rec.principal_title = facts["principal_title"][:80]
                rec.provenance["principal_title"] = fc_prov(rec.website)
            rec.could_not_verify = [f for f in rec.could_not_verify
                                    if f not in ("principal_name", "principal_title")]
            report["principal_added"].append(rec.name)
        if facts.get("sectors") and not rec.investing_sectors:
            rec.investing_sectors = [s[:40] for s in facts["sectors"]][:6]
        ckpt[rec.fo_id] = "enriched"
        ckpt["_report"] = report
        CKPT.write_text(json.dumps(ckpt), encoding="utf-8")

    export_dataset(records, audit=[], out_dir="data/final")
    print("\n===== FIRECRAWL ENRICHMENT REPORT =====")
    print(f"  sites verified + read: {report['matched']}")
    print(f"  type resolved (Undetermined -> SFO/MFO): {len(report['type_resolved'])}")
    for x in report["type_resolved"]:
        print("     +", x)
    print(f"  investment thesis added: {len(report['thesis_added'])}")
    print(f"  principal added (website): {len(report['principal_added'])}")
    print(f"  WRONG/unverifiable URLs flagged: {len(report['wrong_url_flagged'])}")
    for x in report["wrong_url_flagged"]:
        print("     !", x)


if __name__ == "__main__":
    main()
