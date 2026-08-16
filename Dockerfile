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
    HF_HOME=/app/.cache/huggingface \
    PORT=8000

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Every package `api.app` imports, which is checkable rather than remembered:
#   python -c "import api.app" and compare against this list.
# The five after `services` were missing until 2026-08 — the image had not been
# rebuilt since the workspace programme added them, so it would have started
# with ModuleNotFoundError on the first import.
COPY config/       config/
COPY chunking/     chunking/
COPY embeddings/   embeddings/
COPY generation/   generation/
COPY retrieval/    retrieval/
COPY services/     services/
COPY corpora/      corpora/
COPY documents/    documents/
COPY ingestion/    ingestion/
COPY jobs/         jobs/
COPY evaluation/   evaluation/
COPY api/          api/
COPY aws/          aws/

# Needed only to build the benchmark index below, but they are small and
# keeping them makes the corpus rebuildable inside a running container.
COPY data/         data/
COPY scripts/      scripts/

# Bake the benchmark corpus and the model weights into the image.
#
# Both are otherwise downloaded or computed on first request, which on a
# scale-to-zero host means the first visitor waits through a 130 MB model
# download and a full re-index. Doing it here costs image size and buys a cold
# start that only has to load from local disk.
#
# This is also what makes the Evaluation Lab work on a host with an ephemeral
# filesystem: the labelled corpus is part of the image, not part of the volume.
RUN mkdir -p index logs && \
    python scripts/build_embeddings.py && \
    python scripts/build_index.py

# Hugging Face Spaces runs the container as uid 1000 and Fargate-style hosts
# often drop root too. Everything the app writes at runtime — uploads, the
# document database, rebuilt indexes, logs, the model cache — lives under /app,
# so the whole tree is handed to that user.
RUN useradd --uid 1000 --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

EXPOSE 8000

# Shell form so $PORT is expanded: Spaces and most PaaS hosts inject their own.
CMD uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
