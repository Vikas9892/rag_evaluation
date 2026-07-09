# --------------------------------------------------------------------------
# Stage 1 — build: install Python dependencies into an isolated prefix
# --------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed at install time only (not at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --------------------------------------------------------------------------
# Stage 2 — runtime: lean image with just what the app needs
# --------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Suppress Python bytecode writes and buffer stdout/stderr for CloudWatch
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source (model weights cached at runtime via HF_HOME)
COPY config/       config/
COPY chunking/     chunking/
COPY embeddings/   embeddings/
COPY generation/   generation/
COPY retrieval/    retrieval/
COPY services/     services/
COPY api/          api/
COPY aws/          aws/

# Index artefacts are mounted at runtime via a bind mount or volume
# (see docker-compose.yml) — they are NOT baked into the image
RUN mkdir -p index logs

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
