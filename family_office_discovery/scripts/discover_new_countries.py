#!/usr/bin/env python3
"""
Family Office Discovery Agent -- new country discovery.

For each non-excluded country, dispatches one Browser Use cloud-agent task
that thoroughly searches (multiple cities, keyword variants, associations,
conferences, portfolio/family graphs) and returns a JSON array of candidate
family offices matching the discovery-only schema. Results are hard-filtered
against the excluded-country list, deduped against existing candidates, and
appended to output/new_countries_candidates.jsonl.

Usage:
    python discover_new_countries.py --countries "Japan,Finland" --concurrency 3   # test batch
    python discover_new_countries.py --concurrency 6                                # full run
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
API_ROOT = "https://api.browser-use.com/api/v4"
MASTER_FILE = BASE / "output" / "master_candidates.jsonl"
OUT_FILE = BASE / "output" / "new_countries_candidates.jsonl"
ENV_FILE = BASE / ".env"

MAX_COST_USD = 0.80
POLL_INTERVAL = 6
POLL_TIMEOUT = 720  # 12 min per task -- these are broad research tasks

EXCLUDED_COUNTRIES = {
    "united states", "usa", "u.s.", "u.s.a.", "canada", "switzerland", "australia",
    "netherlands", "germany", "brazil", "united kingdom", "uk", "singapore", "austria",
    "india", "france", "sweden", "norway", "thailand", "denmark",
    "united arab emirates", "uae", "hong kong", "spain", "luxembourg", "israel",
    "malaysia", "chile", "monaco", "belgium", "italy", "qatar", "kuwait", "turkey",
    "hungary", "kenya", "argentina", "colombia",
}

# country -> hint cities (for prompt guidance; agent may go beyond these)
PRIORITY_COUNTRIES = {
    "Japan": ["Tokyo", "Osaka", "Kyoto", "Nagoya", "Yokohama"],
    "South Korea": ["Seoul", "Busan", "Incheon"],
    "China": ["Shanghai", "Beijing", "Shenzhen", "Hong Kong (exclude)", "Guangzhou"],
    "Taiwan": ["Taipei", "Kaohsiung"],
    "Indonesia": ["Jakarta", "Surabaya"],
    "Philippines": ["Manila", "Cebu"],
    "Vietnam": ["Ho Chi Minh City", "Hanoi"],
    "Pakistan": ["Karachi", "Lahore", "Islamabad"],
    "Bangladesh": ["Dhaka", "Chittagong"],
    "Sri Lanka": ["Colombo"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Dhahran"],
    "Bahrain": ["Manama"],
    "Oman": ["Muscat"],
    "Jordan": ["Amman"],
    "Finland": ["Helsinki", "Espoo", "Tampere"],
    "Ireland": ["Dublin", "Cork"],
    "Portugal": ["Lisbon", "Porto", "Braga"],
    "Poland": ["Warsaw", "Krakow"],
    "Czech Republic": ["Prague", "Brno"],
    "Greece": ["Athens", "Thessaloniki"],
    "Romania": ["Bucharest"],
    "Slovakia": ["Bratislava"],
    "Slovenia": ["Ljubljana"],
    "Croatia": ["Zagreb"],
    "Serbia": ["Belgrade"],
    "Iceland": ["Reykjavik"],
    "Cyprus": ["Nicosia", "Limassol"],
    "Malta": ["Valletta"],
    "Estonia": ["Tallinn"],
    "Latvia": ["Riga"],
    "Lithuania": ["Vilnius"],
    "South Africa": ["Johannesburg", "Cape Town", "Durban", "Pretoria"],
    "Nigeria": ["Lagos", "Abuja"],
    "Ghana": ["Accra"],
    "Tanzania": ["Dar es Salaam"],
    "Botswana": ["Gaborone"],
    "Namibia": ["Windhoek"],
    "Mauritius": ["Port Louis"],
    "Morocco": ["Casablanca", "Rabat"],
    "Egypt": ["Cairo", "Alexandria"],
    "Mexico": ["Mexico City", "Monterrey", "Guadalajara"],
    "Costa Rica": ["San Jose"],
    "Panama": ["Panama City"],
    "Peru": ["Lima"],
    "Uruguay": ["Montevideo"],
    "Ecuador": ["Quito", "Guayaquil"],
    "Dominican Republic": ["Santo Domingo"],
    "New Zealand": ["Auckland", "Wellington"],
}

KEYWORDS = [
    "single family office", "multi family office", "family investment office",
    "family wealth office", "private family office", "family capital",
    "family investment group", "family holdings", "family office association",
    "family office conference",
]


def load_api_key() -> str:
    key = os.environ.get("BROWSER_USE_API_KEY")
    if key:
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("BROWSER_USE_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("BROWSER_USE_API_KEY not set (checked env and .env)")


API_KEY = load_api_key()


def api_request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{API_ROOT}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Browser-Use-API-Key", API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {e.code}: {detail}") from None


def norm_name(name: str) -> str:
    n = (name or "").lower().strip()
    n = re.sub(r"[.,]", "", n)
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\bthe\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def build_task_prompt(country: str, cities: list[str]) -> str:
    city_str = ", ".join(cities)
    kw_str = "; ".join(f'"{k}"' for k in KEYWORDS)
    return f"""You are doing FAMILY OFFICE DISCOVERY (not verification) for {country} only.

Thoroughly search for organizations that are family offices (single-family or \
multi-family) headquartered in {country}. Cover these major cities as a starting \
point but also search the country broadly: {city_str}.

Rotate through these search terms (and local-language equivalents for {country}): \
{kw_str}. Also search for "{country} family office association", "{country} family \
office conference", and mine any conference/association pages you find for member \
organizations, sponsors and speakers -- then check whether each is itself a family \
office headquartered in {country}.

DO NOT include: private banks, wealth managers, asset managers, financial advisors, \
accounting firms, law firms, consulting firms, family-office software/service \
vendors, PE firms, or VC firms. Those are allowed as discovery sources (to find \
family offices mentioned on their client/member/sponsor lists) but must not be \
returned themselves.

ONLY include organizations you have real evidence are headquartered in {country}. \
If you find a promising organization but cannot confirm it is headquartered in \
{country} (not merely operating there, not founded by someone who now lives \
elsewhere), skip it.

Try to find as many genuine, distinct candidates as you reasonably can (aim for \
15-25 if the country supports it; fewer is fine for small countries -- do not \
fabricate to hit a number).

Respond with ONLY a JSON array (no markdown fences, no commentary), where each \
element has exactly these keys:
{{"candidate_name": "", "possible_type": "SFO | MFO | UNKNOWN", "country": "{country}", \
"city": "", "website": "", "discovery_source": "", "discovery_reason": ""}}

If you find zero qualifying candidates, respond with an empty JSON array: []"""


def extract_json_array(text: str):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        val = json.loads(text)
        return val if isinstance(val, list) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if m:
        try:
            val = json.loads(m.group(0))
            return val if isinstance(val, list) else None
        except json.JSONDecodeError:
            return None
    return None


def run_country(country: str, cities: list[str]) -> dict:
    task = build_task_prompt(country, cities)
    created = api_request("POST", "/runs", {"task": task, "maxCostUsd": MAX_COST_USD})
    run_id = created["id"]

    elapsed = 0
    status = created.get("status", "queued")
    while status not in ("completed", "failed", "cancelled") and elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        info = api_request("GET", f"/runs/{run_id}")
        status = info.get("status")

    info = api_request("GET", f"/runs/{run_id}")
    result_text = info.get("result")
    parsed = extract_json_array(result_text) if isinstance(result_text, str) else None

    return {
        "country": country,
        "run_id": run_id,
        "run_status": info.get("status"),
        "run_error": info.get("error"),
        "candidates": parsed or [],
        "raw_result": None if parsed is not None else result_text,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", type=str, default="",
                     help="comma-separated subset to run; default = all PRIORITY_COUNTRIES")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()

    countries = (
        [c.strip() for c in args.countries.split(",") if c.strip()]
        if args.countries else list(PRIORITY_COUNTRIES.keys())
    )

    # existing dedup set: master file + anything already in the new-countries output
    seen_names = set()
    seen_sites = set()
    for path in (MASTER_FILE, OUT_FILE):
        if path.exists():
            with open(path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    seen_names.add(norm_name(d.get("candidate_name", "")))
                    w = (d.get("website") or "").lower().strip()
                    w = re.sub(r"^https?://(www\.)?", "", w).rstrip("/")
                    if w:
                        seen_sites.add(w)

    already_run = set()
    if OUT_FILE.exists():
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        already_run.add(json.loads(line).get("_source_country"))
                    except json.JSONDecodeError:
                        pass

    todo = [c for c in countries if c not in already_run]
    if not todo:
        print("All requested countries already have a discovery run recorded in the output file.")
        return

    print(f"Discovering across {len(todo)} countries (concurrency={args.concurrency}), "
          f"cap ${MAX_COST_USD}/task -> up to ${MAX_COST_USD * len(todo):.2f} worst case")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    total_added = 0
    total_rejected_dupe = 0
    total_rejected_excluded = 0
    type_counts = {"SFO": 0, "MFO": 0, "UNKNOWN": 0}
    country_counts = {}

    with open(OUT_FILE, "a", encoding="utf-8") as out, \
         ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(run_country, c, PRIORITY_COUNTRIES.get(c, [])): c for c in todo
        }
        for fut in as_completed(futures):
            country = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                print(f"  [ERR] {country}: {e}")
                continue

            added_here = 0
            for cand in res["candidates"]:
                cname = cand.get("candidate_name", "")
                ccountry = (cand.get("country") or country).strip()
                if norm_name(ccountry) in EXCLUDED_COUNTRIES or ccountry.lower() in EXCLUDED_COUNTRIES:
                    total_rejected_excluded += 1
                    continue
                nn = norm_name(cname)
                w = (cand.get("website") or "").lower().strip()
                w = re.sub(r"^https?://(www\.)?", "", w).rstrip("/")
                if not nn or nn in seen_names or (w and w in seen_sites):
                    total_rejected_dupe += 1
                    continue
                seen_names.add(nn)
                if w:
                    seen_sites.add(w)

                ptype = cand.get("possible_type", "UNKNOWN")
                if ptype not in ("SFO", "MFO", "UNKNOWN"):
                    ptype = "UNKNOWN"
                type_counts[ptype] += 1
                country_counts[ccountry] = country_counts.get(ccountry, 0) + 1

                record = {
                    "candidate_name": cname,
                    "possible_type": ptype,
                    "country": ccountry,
                    "city": cand.get("city", ""),
                    "website": cand.get("website", ""),
                    "discovery_source": cand.get("discovery_source", ""),
                    "discovery_reason": cand.get("discovery_reason", ""),
                    "discovery_cycle": "global_expansion_1",
                    "_source_country": country,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                added_here += 1

            total_added += added_here
            status_note = "" if res["run_status"] == "completed" else f" [{res['run_status']}: {res.get('run_error')}]"
            print(f"  [{country}] +{added_here} candidates (raw returned: {len(res['candidates'])}){status_note}")

            if added_here == 0 and res["run_status"] == "completed" and not res["candidates"]:
                # record a zero-result marker so re-runs skip this country
                out.write(json.dumps({"candidate_name": None, "_source_country": country,
                                       "_zero_result": True}) + "\n")
            out.flush()

    print("\n=== DISCOVERY CYCLE REPORT ===")
    print(f"Candidates added this run: {total_added}")
    print(f"SFO: {type_counts['SFO']}  MFO: {type_counts['MFO']}  UNKNOWN: {type_counts['UNKNOWN']}")
    print(f"Duplicate candidates rejected: {total_rejected_dupe}")
    print(f"Excluded-country candidates rejected: {total_rejected_excluded}")
    print("Countries this run:")
    for c, n in sorted(country_counts.items(), key=lambda x: -x[1]):
        print(f"  - {c}: {n}")


if __name__ == "__main__":
    main()
