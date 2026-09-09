# Excel Parser — single image, PostgreSQL is external.
#
#   docker build -t excel-parser .
#   docker run -p 8000:8000 --env-file .env excel-parser
#
# The built Angular frontend is served by FastAPI as static files.
# PostgreSQL must be reachable at PGHOST/PGPORT from inside the container.

# ── stage 1: build the Angular frontend ──
FROM node:22-alpine AS frontend
WORKDIR /build
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY app/frontend/ ./
RUN npx ng build --configuration production

# ── stage 2: Python backend + built frontend ──
FROM python:3.13-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY app/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend code
COPY tools/ /app/tools/
COPY app/backend/ /app/backend/

# Built frontend
COPY --from=frontend /build/dist/frontend/browser /app/static

# Utility scripts
COPY util/ /app/util/

# Default env
ENV APP_ENV=production
ENV APP_ALLOWED_ORIGINS=*
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

WORKDIR /app/backend
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
