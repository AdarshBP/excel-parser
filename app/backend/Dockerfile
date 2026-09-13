# Excel Parser — Backend (FastAPI)
#
# Build context must be the repo root so tools/ and template/ are available:
#   docker build -f app/backend/Dockerfile -t excel-parser-backend .
#
# The directory layout inside the container mirrors the repo structure so that
# state.py's PROJECT_ROOT (two parents up from backend/) resolves correctly:
#
#   /excel_parser/              ← PROJECT_ROOT
#   ├── app/
#   │   └── backend/            ← WORKDIR, uvicorn runs here
#   ├── tools/                  ← parser (imported via engine.py)
#   ├── util/                   ← seed.sh, clear_all.sh
#   └── template/               ← config_template.xlsx

FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /excel_parser

# Python deps (cached layer — only rebuilds when requirements change)
COPY app/backend/requirements.txt /excel_parser/app/backend/
RUN pip install --no-cache-dir -r /excel_parser/app/backend/requirements.txt

# Parser tools (shared between CLI and backend)
COPY tools/ /excel_parser/tools/

# Backend code
COPY app/backend/ /excel_parser/app/backend/

# Utility scripts (seed.sh, clear_all.sh)
COPY util/ /excel_parser/util/

# Template workbook
COPY template/ /excel_parser/template/

ENV APP_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 8000

WORKDIR /excel_parser/app/backend
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
