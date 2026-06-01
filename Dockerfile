# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────
# Treadwell AI News Feed — multi-stage image (SPEC §6).
#   Stage 1 (node:20-slim): build the Vite/React SPA -> frontend/dist
#   Stage 2 (python:3.11-slim): FastAPI runtime + Node + the `claude` CLI baked in,
#                               serving the API on :8890 and the built SPA via StaticFiles.
# ─────────────────────────────────────────────────────────────────────────

# ── Stage 1: build the frontend ───────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend

# Install deps first (better layer caching). Use npm ci when a lockfile exists,
# otherwise fall back to npm install.
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Build the SPA -> dist/
COPY frontend/ ./
RUN npm run build


# ── Stage 2: python runtime (+ Node + claude CLI) ─────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_MAJOR=20

# System deps: tini (PID 1 / signal handling), curl (healthcheck + node setup),
# ca-certificates, then Node 20 (for the `claude` CLI) from NodeSource.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tini \
        curl \
        ca-certificates \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Python deps first for caching.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Backend source.
COPY backend/ ./

# Built SPA from stage 1 -> ../frontend/dist (FastAPI StaticFiles mounts this).
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

EXPOSE 8890

# tini handles signals / zombie reaping; uvicorn serves API + SPA.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8890"]
