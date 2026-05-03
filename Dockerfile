# Single image: Vite frontend (build) + FastAPI backend (uvicorn).
# Suitable for Render, Fly.io, Railway, etc. Set env vars in the host dashboard.

# ── Stage 1: build React SPA ───────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python API + static frontend ───────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Optional: curl for Render health checks or debugging
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (package `app` lives at /app/app)
COPY backend/ .

# Built SPA → served by FastAPI when static/frontend/index.html exists
COPY --from=frontend-builder /src/frontend/dist ./static/frontend

EXPOSE 8000

# Render and others inject PORT; default 8000 for local `docker run`.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
