#!/usr/bin/env python3
"""
Enrich family office candidates with principal/contact info using the
Browser Use Cloud API (https://api.browser-use.com, v4 "runs" endpoint).

Reads:  family_office_discovery/output/master_candidates.jsonl
Writes: family_office_discovery/output/contacts_enriched.jsonl (append, resumable)

Usage:
    python enrich_contacts.py --limit 5                 # small test batch
    python enrich_contacts.py --limit 500 --concurrency 5
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
OUT_FILE = BASE / "output" / "contacts_enriched.jsonl"
ENV_FILE = BASE / ".env"

MAX_COST_USD = 0.35  # per-task safety cap
POLL_INTERVAL = 5
POLL_TIMEOUT = 480  # 8 min per task

OUTPUT_SCHEMA_HINT = {
    "principal_first_name": "string or null",
    "principal_last_name": "string or null",
    "principal_full_name": "string or null",
    "principal_job_title": "string or null",
    "principal_linkedin_url": "string or null",
    "contact_email": "string or null",
    "contact_phone": "string or null",
    "family_office_linkedin_url": "string or null",
    "short_description": "string or null",
    "confidence": "one of: high, medium, low",
    "sources": "array of URLs actually visited/used",
}


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


def build_task_prompt(candidate: dict) -> str:
    name = candidate.get("candidate_name", "")
    website = candidate.get("website", "")
    city = candidate.get("city", "")
    country = candidate.get("country", "")
    return f"""Research the family office "{name}" (website: {website or "unknown"}, \
location: {city}, {country}).

Using ONLY public web sources you can view without logging in (their official \
website, press coverage, public LinkedIn profile pages visible via Google search \
results, Crunchbase, Bloomberg, SEC filings) find:
- The principal / founder / CEO / managing partner's full name and job title
- Their public LinkedIn profile URL, if discoverable via search (do not log into LinkedIn)
- A publicly listed contact email (e.g. info@ or a named contact) if published anywhere
- A publicly listed phone number if published anywhere
- The family office's own LinkedIn company page URL
- A 1-2 sentence description of what the family office does

Do not guess or fabricate any value. If a field cannot be verified from a public \
source, set it to null. List the URLs you actually used as evidence.

Respond with ONLY a single JSON object (no markdown fences, no commentary) with \
exactly these keys: {json.dumps(OUTPUT_SCHEMA_HINT)}"""


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def run_one(candidate: dict) -> dict:
    name = candidate.get("candidate_name", "unknown")
    task = build_task_prompt(candidate)
    created = api_request("POST", "/runs", {
        "task": task,
        "maxCostUsd": MAX_COST_USD,
    })
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
    parsed = extract_json(result_text) if isinstance(result_text, str) else None

    return {
        "candidate_name": name,
        "possible_type": candidate.get("possible_type"),
        "country": candidate.get("country"),
        "city": candidate.get("city"),
        "website": candidate.get("website"),
        "run_id": run_id,
        "run_status": info.get("status"),
        "run_error": info.get("error"),
        "enrichment": parsed,
        "raw_result": None if parsed else result_text,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    candidates = []
    with open(MASTER_FILE, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))

    done_names = set()
    if OUT_FILE.exists():
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done_names.add(json.loads(line)["candidate_name"])
                    except (json.JSONDecodeError, KeyError):
                        pass

    todo = [c for c in candidates[args.offset:] if c.get("candidate_name") not in done_names]
    todo = todo[: args.limit]

    if not todo:
        print("Nothing to do (all candidates in requested range already enriched).")
        return

    print(f"Enriching {len(todo)} candidates (concurrency={args.concurrency}), "
          f"cap ${MAX_COST_USD}/task -> up to ${MAX_COST_USD * len(todo):.2f} worst case")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, 0
    with open(OUT_FILE, "a", encoding="utf-8") as out, \
         ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_one, c): c for c in todo}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                record = fut.result()
            except Exception as e:
                record = {
                    "candidate_name": c.get("candidate_name"),
                    "website": c.get("website"),
                    "run_status": "error",
                    "run_error": str(e),
                    "enrichment": None,
                }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            if record.get("run_status") == "completed" and record.get("enrichment"):
                ok += 1
                principal = record["enrichment"].get("principal_full_name")
                print(f"  [ok] {record['candidate_name']} -> {principal}")
            else:
                failed += 1
                print(f"  [--] {record['candidate_name']} -> {record.get('run_status')} "
                      f"{record.get('run_error') or ''}")

    print(f"\nDone. ok={ok} failed/no-data={failed}. Results appended to {OUT_FILE}")


if __name__ == "__main__":
    main()
