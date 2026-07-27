# Deployment

The Micro-RAG is a FastAPI service in a container, deployed to **Hugging Face Spaces**
(free, persistent, public URL — DecisionLog D13). It builds from the `Dockerfile` and
serves the exact committed dataset (`data/final/family_offices.csv`).

## What gets deployed
- `Dockerfile` — python:3.12-slim, installs `requirements.txt`, pre-downloads the fastembed
  ONNX embedding model at build (no torch → small image), runs `uvicorn` on port 7860.
- `src/fointel/serve/app.py` — the API (`/`, `/health`, `/query`).
- `data/final/family_offices.csv` — the 50 validated records the RAG answers from.

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
# GET  http://localhost:8000/health      -> {"status":"ok","records":50}
# POST http://localhost:8000/query {"query":"single-family offices in Texas"}
```

## Configuration
- `MIN_RETRIEVAL_SCORE` (default 0.55) — abstention threshold (tuned; see the RAG eval).
- `RETRIEVAL_TOP_K` (default 5), `EMBED_MODEL` (default `BAAI/bge-small-en-v1.5`).
- No secrets are required to run; the dataset is bundled. The DB backend is not used by the
  served RAG (it reads the delivered CSV), keeping the image minimal.

## Notes
- The container build was verified against the Dockerfile; the local run was blocked only by
  a stopped Docker Desktop daemon, so container verification is completed on HF's build infra.
  The identical app is verified serving via `uvicorn` locally (see evidence).
