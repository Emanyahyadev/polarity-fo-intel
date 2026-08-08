# Deployment

The Micro-RAG is a FastAPI service in a container. It builds from the `Dockerfile`
and serves the exact committed dataset (`data/final/family_offices.csv`).

## Live (verified)

- **URL:** https://family-office-intelligence.onrender.com
- **Host:** Render free web service (Docker), deployed from this repo via `render.yaml` (Blueprint).
- **Health:** `GET /health` → `{"status":"ok","records":80}`
- **Verified queries:** see [`docs/evidence/live-url-query-transcript.md`](evidence/live-url-query-transcript.md)
  — on-topic queries answer with grounded records; off-topic ("best pizza in Chicago")
  and empty-hard-filter ("multi-family offices in New York") queries correctly abstain.
- **Kept warm:** Render free services sleep after ~15 min idle. A scheduled GitHub Action
  (`.github/workflows/keepalive.yml`) pings `/health` every 10 minutes so the demo stays
  responsive throughout the review window with no cold-start wait. Disable it after review
  from the repo's Actions tab if desired.

> **Why Render (not HF / Vercel / shared hosting), DecisionLog D13.** HF now requires a
> **PRO** plan for *both* Docker *and* Gradio Spaces (only static Spaces are free — a live
> 402 confirmed this for each). Vercel's serverless size/duration limits do not fit the
> onnxruntime embedding model + in-memory index. Shared hosting (e.g. Hostinger) cannot run
> a long-lived ASGI process with a native ML dependency. Render's free container web service
> runs the existing `Dockerfile` unchanged.

> **Host note (DecisionLog D13, revised).** Hugging Face changed its policy: free
> accounts now get only *Static* Spaces — Docker Spaces require a **PRO** subscription
> (a live 402 confirmed this during deploy). To stay strictly free-tier, the primary
> target is **Render** (free web service, no credit card). The `scripts/deploy_hf.py`
> path still works for anyone with HF PRO. The Dockerfile binds to `$PORT` so it runs
> unchanged on Render, HF, or Cloud Run.

## Deploy on Render (free, primary)
1. Sign in at https://render.com with GitHub (free, no card).
2. **New → Blueprint** → select this repository → **Apply** (Render reads `render.yaml`
   + the `Dockerfile`).  *(Or: New → Web Service → pick the repo → Render auto-detects Docker.)*
3. Render builds the image (~5–8 min) and serves at `https://family-office-intelligence.onrender.com`
   (exact subdomain shown in the dashboard).
4. Free web services sleep after ~15 min idle → the first request after idle cold-starts
   in ~30–60 s, then is fast. `GET /health` wakes it.

## What gets deployed
- `Dockerfile` — python:3.12-slim, installs `requirements.txt`, pre-downloads the fastembed
  ONNX embedding model at build (no torch → small image), runs `uvicorn` on port 7860.
- `src/fointel/serve/app.py` — the API (`/`, `/health`, `/query`).
- `data/final/family_offices.csv` — the 80 validated records the RAG answers from.

## One-command deploy
Create a write token at https://huggingface.co/settings/tokens, then:

```bash
HF_TOKEN=hf_xxx python scripts/deploy_hf.py
```

This creates/updates a Docker Space and uploads the deployable set. HF builds the image
(~2–4 min) and serves it at:

```
https://<your-hf-username>-family-office-intelligence.hf.space
```

## LLM answers (optional)
Without an LLM key the service returns **grounded extractive answers** (deterministic,
hallucination-proof). To enable LLM-generated answers (Groq free tier), add a Space secret
`LLM_API_KEY` (and optionally `LLM_MODEL`, default `llama-3.3-70b-versatile`). The grounding
control still bounds the LLM: any answer naming a firm not in the retrieved set is rejected
and replaced by the extractive answer.

## Run locally (verification)
```bash
uvicorn fointel.serve.app:app --host 0.0.0.0 --port 8000
# GET  http://localhost:8000/           -> UI
# GET  http://localhost:8000/health      -> {"status":"ok","records":80}
# POST http://localhost:8000/query {"query":"single-family offices in Texas"}
```

## Configuration
- `MIN_RETRIEVAL_SCORE` (default 0.68) — abstention threshold, tuned against adversarial
  in-vocabulary probes (genuine queries ≥0.719, off-topic ≤0.643); see the RAG eval.
- `RETRIEVAL_TOP_K` (default 5), `EMBED_MODEL` (default `BAAI/bge-small-en-v1.5`).
- No secrets are required to run; the dataset is bundled. The DB backend is not used by the
  served RAG (it reads the delivered CSV), keeping the image minimal.

## Notes
- The container build was verified against the Dockerfile; the local run was blocked only by
  a stopped Docker Desktop daemon, so container verification is completed on HF's build infra.
  The identical app is verified serving via `uvicorn` locally (see evidence).
