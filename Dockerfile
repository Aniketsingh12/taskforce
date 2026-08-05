# Single-service production image: builds the frontend, then serves it from
# the SAME FastAPI process that serves the API (see the static-files mount in
# backend/app/main.py). One Railway service, one URL, same-origin — no CORS
# and no VITE_API_URL split needed.
#
# This is separate from backend/Dockerfile, which builds a backend-ONLY image
# for local Docker Compose (Option C in the README) and stays untouched.
# Build context for THIS file must be the repo root (it needs both frontend/
# and backend/) — on Railway that means setting the service's Root Directory
# to "." (repo root), not "backend".

# ---- Stage 1: build the frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend, with the built frontend copied in ----
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# Lands at /app/static — a sibling of the `app` package, picked up by
# STATIC_DIR in backend/app/main.py. Nothing breaks if this stage is skipped
# (e.g. local non-Docker dev): main.py checks STATIC_DIR.exists() and simply
# doesn't mount it when absent, so the API-only local workflow is unaffected.
COPY --from=frontend-build /fe/dist ./static

EXPOSE 8000

# Railway/Render assign the port at runtime via $PORT; default to 8000 for
# `docker run` with nothing set. Shell form so the shell expands the variable.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
