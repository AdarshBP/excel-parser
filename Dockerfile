# Excel Parser — single image (monolithic), PostgreSQL is external.
#
# This bundles both frontend and backend into one container. For the
# split-service setup (recommended), use docker-compose.yml instead which
# builds from app/backend/Dockerfile and app/frontend/Dockerfile separately.
#
#   docker build -t excel-parser .
#   docker run -p 8000:8000 --env-file .env excel-parser
#
# The built Angular frontend is served by FastAPI as static files.
# PostgreSQL must be reachable at PGHOST/PGPORT from inside the container.
#
# Layout mirrors the repo so state.py's PROJECT_ROOT resolves correctly:
#   /excel_parser/app/backend/  ← WORKDIR
#   /excel_parser/tools/        ← parser
#   /excel_parser/template/     ← config template
#   /excel_parser/static/       ← built Angular app

# ── stage 1: build the Angular frontend ──
FROM node:22-alpine AS frontend
WORKDIR /build
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY app/frontend/ ./
RUN npx ng build --configuration production

# ── stage 2: Python backend + built frontend ──
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /excel_parser

# Python deps
COPY app/backend/requirements.txt /excel_parser/app/backend/
RUN pip install --no-cache-dir -r /excel_parser/app/backend/requirements.txt

# Backend code
COPY tools/ /excel_parser/tools/
COPY app/backend/ /excel_parser/app/backend/

# Built frontend
COPY --from=frontend /build/dist/frontend/browser /excel_parser/static

# Utility scripts and template
COPY util/ /excel_parser/util/
COPY template/ /excel_parser/template/

ENV APP_ENV=production \
    APP_ALLOWED_ORIGINS=* \
    PYTHONUNBUFFERED=1

EXPOSE 8000

WORKDIR /excel_parser/app/backend
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
