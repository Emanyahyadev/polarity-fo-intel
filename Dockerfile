# Micro-RAG service — deployable image (Hugging Face Spaces / any container host).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    MIN_RETRIEVAL_SCORE=0.55 \
    HF_HOME=/app/.cache/hf \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY data/final/family_offices.csv ./data/final/family_offices.csv

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps -e .

# Pre-download the embedding model so the first query is fast (and the image is self-contained).
RUN python -c "from fointel.rag.index import embed_texts; embed_texts(['warm up'])"

EXPOSE 7860
# Binds to $PORT when the host sets one (Render, Cloud Run), else 7860 (HF Spaces).
# No LLM key -> grounded extractive answers; set LLM_API_KEY (Groq free tier) for LLM answers.
CMD ["sh", "-c", "uvicorn fointel.serve.app:app --host 0.0.0.0 --port ${PORT:-7860}"]
