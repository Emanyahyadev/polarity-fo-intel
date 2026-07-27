# Micro-RAG service — deployable image (Hugging Face Spaces / any container host).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    MIN_RETRIEVAL_SCORE=0.68 \
    HF_HOME=/app/.cache/hf \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

WORKDIR /app

# Serving-only deps (lean image -> fast, reliable free-tier build). The full
# dataset-building deps in requirements.txt are NOT needed to serve the RAG.
COPY requirements-serve.txt pyproject.toml ./
COPY src ./src
COPY data/final/family_offices.csv ./data/final/family_offices.csv

RUN pip install --no-cache-dir -r requirements-serve.txt \
    && pip install --no-cache-dir --no-deps -e .

# Precompute the 50 document embeddings AT BUILD TIME (memory is plentiful here). The
# runtime then loads these vectors instead of running the model at startup, so it fits the
# 512 MB free instance. Also pre-downloads/caches the ONNX model for fast first query.
RUN python -c "from fointel.rag.load import load_records_from_csv; from fointel.rag.index import precompute_and_save; print('precomputed doc embeddings:', precompute_and_save(load_records_from_csv()))"

EXPOSE 7860
# Binds to $PORT when the host sets one (Render, Cloud Run), else 7860 (HF Spaces).
# No LLM key -> grounded extractive answers; set LLM_API_KEY (Groq free tier) for LLM answers.
CMD ["sh", "-c", "uvicorn fointel.serve.app:app --host 0.0.0.0 --port ${PORT:-7860}"]
