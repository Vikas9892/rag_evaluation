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

# Hugging Face Spaces runs the container as uid 1000, and container hosts
# generally drop root. The user is created before anything is copied so each
# layer can be owned as it lands: a recursive chown afterwards duplicates every
# file it touches into a new layer, which on an image carrying torch and a set
# of model weights is an expensive way to change one metadata field.
# /app is chowned as a single directory, not recursively: the app writes
# index/, logs/ and the model cache into it at build and at runtime.
RUN useradd --create-home --uid 1000 app && \
    mkdir -p /app && \
    chown app:app /app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Every package `api.app` imports, which is checkable rather than remembered:
#   python -c "import api.app" and compare against this list.
# The five after `services` were missing until 2026-08 — the image had not been
# rebuilt since the workspace programme added them, so it would have started
# with ModuleNotFoundError on the first import.
COPY --chown=app:app config/       config/
COPY --chown=app:app chunking/     chunking/
COPY --chown=app:app embeddings/   embeddings/
COPY --chown=app:app generation/   generation/
COPY --chown=app:app retrieval/    retrieval/
COPY --chown=app:app services/     services/
COPY --chown=app:app corpora/      corpora/
COPY --chown=app:app documents/    documents/
COPY --chown=app:app ingestion/    ingestion/
COPY --chown=app:app jobs/         jobs/
COPY --chown=app:app evaluation/   evaluation/
COPY --chown=app:app api/          api/
COPY --chown=app:app aws/          aws/

# Needed only to build the benchmark index below, but they are small and
# keeping them makes the corpus rebuildable inside a running container.
COPY --chown=app:app data/         data/
COPY --chown=app:app scripts/      scripts/

# Bake the benchmark corpus and the model weights into the image.
#
# Both are otherwise downloaded or computed on first request, which on a
# scale-to-zero host means the first visitor waits through a 130 MB model
# download and a full re-index. Doing it here costs image size and buys a cold
# start that only has to load from local disk.
#
# This is also what makes the Evaluation Lab work on a host with an ephemeral
# filesystem: the labelled corpus is part of the image, not part of the volume.
USER app
RUN mkdir -p index logs && \
    python scripts/build_embeddings.py && \
    python scripts/build_index.py

EXPOSE 8000

# Shell form so $PORT is expanded: Spaces and most PaaS hosts inject their own.
CMD uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
