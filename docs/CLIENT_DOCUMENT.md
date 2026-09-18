# Excel Parser — Product Document

**Config-driven Excel-to-Database Loading Platform**

Version 1.0 | September 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Solution Overview](#3-solution-overview)
4. [Architecture & Design](#4-architecture--design)
5. [End-to-End Workflow](#5-end-to-end-workflow)
6. [Feature Coverage](#6-feature-coverage)
7. [Security](#7-security)
8. [Deployment](#8-deployment)
9. [API Surface](#9-api-surface)
10. [Technology Stack](#10-technology-stack)
11. [Appendix — Configuration Reference](#appendix--configuration-reference)

---

## 1. Executive Summary

Excel Parser is a **declarative, configuration-driven platform** that loads
structured data from Excel (`.xlsx`) and CSV workbooks into PostgreSQL (or
SQLite) databases. Instead of writing one-off scripts for each file layout, a
non-technical user authors a **configuration workbook** that describes where
each block of data sits and how each column should be typed — the platform
handles validation, type casting, schema generation, data insertion, lineage
tracking, and deduplication automatically.

The platform ships as:

- **CLI tools** — Python scripts for command-line validation and loading.
- **Web application** — Angular 22 frontend + FastAPI backend for interactive
  design, batch processing, and data browsing.
- **Docker images** — production-ready containerised deployment with
  nginx reverse proxy and PostgreSQL.

---

## 2. Problem Statement

Spreadsheets from vendors, partners, and internal teams arrive in every shape:
merged headers, summary rows, multi-block sheets, key-value metadata, currency
symbols (`₹`, `$`), inconsistent date formats (DD/MM vs MM/DD), and bracketed
negatives. Getting this data into a database usually means a one-off Python or
SQL script per file layout.

These scripts are fragile — a new column, a renamed sheet, or a different date
format breaks them. They lack validation, produce no audit trail, and cannot be
handed to non-developers.

---

## 3. Solution Overview

Excel Parser replaces per-file scripts with a **two-workbook model**:

```
Configuration workbook  ─┐
                         ├──►  Validator  ──►  "Is this loadable?" + CREATE TABLE DDL
Source workbook  ────────┘
         │
         └──────────────────►  Executor   ──►  PostgreSQL  or  SQLite
```

- The **configuration workbook** is a standard `.xlsx` with three sheets
  (`target_config`, `sheet_config`, `column_config`) that declare the target
  database, which blocks to read, and how each column maps to a typed database
  column.
- The **source workbook** is the raw data file received from the vendor or
  partner — it is never modified.
- No sheet name, column letter, or row number is hardcoded in the code.
  Everything lives in the configuration workbook.

### Two stages, deliberately separated

| Stage | Purpose | Writes to DB? |
|---|---|---|
| **Validate** (`validator.py`) | Checks config + source, dry-runs every cell, generates DDL | No |
| **Execute** (`executor.py`) | Reads configured cells, casts values, inserts rows with full lineage | Yes |

Both stages are importable Python functions. The web application calls them
directly — the browser and the CLI can never disagree on the outcome.

---

## 4. Architecture & Design

### 4.1 System Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                         Browser                               │
│   Angular 22 + Optimus UI (@openng/optimus-ui)                │
│   Design Mode | Batch Mode | Data Viewer | Settings           │
└──────────────────────────┬────────────────────────────────────┘
                           │ HTTP / REST (38 endpoints)
                           ▼
┌───────────────────────────────────────────────────────────────┐
│                   nginx (reverse proxy)                        │
│   :4200 (or :80 in Docker)                                    │
│   /*       → Angular SPA (static files)                       │
│   /api/*   → proxy to backend:8000                            │
└──────────────────────────┬────────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│               FastAPI Backend (:8000)                          │
│                                                               │
│   main.py      38 REST endpoints                              │
│   auth.py      Session management, Argon2id passwords         │
│   state.py     PostgreSQL app state (users, projects, runs)   │
│   service.py   Calls parser tools (validator, executor,       │
│                preview) — never re-implements parsing          │
│   batch.py     Multi-file validation and push                 │
│   sources.py   Workbook resolution (upload, Sheets, Drive)    │
│   drive.py     Google OAuth + Drive API + Picker              │
│                                                               │
│   Imports:  tools/validator.py                                │
│             tools/executor.py                                 │
│             tools/preview.py                                  │
│             tools/values.py, rows.py, db.py                   │
└──────────────────────────┬────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐
│  PostgreSQL          │  │  Google Drive API     │
│                      │  │  (optional)           │
│  APP_SCHEMA          │  │  - OAuth 2.0          │
│   (excelparser_      │  │  - Picker API         │
│    config)           │  │  - File download      │
│   ├─ users           │  └──────────────────────┘
│   ├─ sessions        │
│   ├─ projects        │
│   ├─ runs            │
│   ├─ batches         │
│   └─ drive_tokens    │
│                      │
│  USER_SCHEMA         │
│   (from config)      │
│   ├─ source_file     │
│   ├─ load_config_    │
│   │  audit           │
│   ├─ <table_1>       │
│   ├─ <table_2>       │
│   └─ ...             │
└──────────────────────┘
```

### 4.2 Key Design Principles

1. **One active row in `sheet_config` = one independent flat table.** Blocks are
   read exactly as they sit in the sheet. Nothing is merged, joined, normalised,
   or derived. Two blocks on one worksheet produce two separate tables.

2. **Configuration is data, not code.** Adding a new file layout means creating
   a new configuration workbook — no Python or SQL changes.

3. **Validation before execution.** The validator answers "is this pair
   loadable?" without writing to any database. Errors are caught before any
   row is inserted.

4. **Full lineage on every row.** Every staged row carries `file_id`,
   `sheet_name`, and `source_row_num` (unique together), so any database value
   traces back to one exact cell in the source workbook.

5. **Schema evolution.** New columns are added automatically via
   `ALTER TABLE ADD COLUMN`. Removed columns keep their data and receive
   defaults on new rows. No manual migration needed.

6. **Deduplication.** Re-loading a byte-identical file (same SHA-256) is
   refused, preventing accidental double-loads.

### 4.3 Data Flow

```
Source workbook (.xlsx / .csv)
       │
       ├──► Validator reads every configured cell, dry-casts to target type
       │    ├── Errors (config problems, type mismatches) → block the push
       │    └── Warnings (empty sections, skipped rows) → informational
       │
       ├──► DDL Generator writes CREATE TABLE statements
       │    └── One table per active sheet_config row + 2 control tables
       │
       └──► Executor reads cells, casts, inserts via parameterised SQL
            ├── source_file record (file name, SHA-256, row count, timestamp)
            ├── load_config_audit records (table name, ranges, column count)
            └── Data rows with lineage columns (file_id, sheet_name, source_row_num)
```

### 4.4 Database Schema Design

Every generated table includes automatic lineage columns:

```sql
<table_name>_id    -- Surrogate key (integer or UUID)
file_id            -- Which load this row came from
file_name          -- Source file name
file_sha256        -- Content hash (for dedup)
source_ref         -- Original reference (Drive link, upload ref, etc.)
sheet_name         -- Worksheet the row came from
source_row_num     -- 1-based Excel row number
```

Plus a unique constraint: `UNIQUE (file_id, sheet_name, source_row_num)` —
so a row can always be traced back to one exact cell and the same row
cannot be loaded twice under one file.

Two control tables are always generated:

| Table | Purpose |
|---|---|
| `source_file` | File name, SHA-256, source reference, row count, load timestamp |
| `load_config_audit` | Per-table: sheet name, row range, column count, config reference |

---

## 5. End-to-End Workflow

### 5.1 Design Mode (Interactive)

This is the primary workflow for setting up a new data source:

```
Step 1: Create Configuration
  User creates a configuration workbook defining:
  - target_config: where data goes (database, schema, prefix)
  - sheet_config: which blocks to read (one row = one table)
  - column_config: which cells to read (one row = one column)
       │
       ▼
Step 2: Upload & Render
  User uploads source + config workbooks via the web UI
  (browser file pick, Google Sheets link, or Google Drive)
  System renders:
  - ER diagram (draggable tables, zoom, FK edges)
  - Data preview (first 20 rows per table with source cell links)
  - Validation issues (errors and warnings)
  - Data quality report (type mismatches, skipped rows)
       │
       ▼
Step 3: Review & Fix
  User reviews issues, adjusts configuration if needed,
  re-renders until clean
       │
       ▼
Step 4: Push
  Two options:
  a) Schema Only — CREATE TABLE without inserting data
  b) Schema + Data — validate, create tables, insert all rows
  Push is disabled when config errors or data quality issues exist
       │
       ▼
Step 5: Verify
  Data Viewer shows all pushed files with per-table audit metadata.
  Push History shows a unified timeline of all loads.
```

### 5.2 Batch Mode (Multi-file Processing)

For recurring data loads (e.g., monthly vendor reports):

```
Step 1: Select one configuration workbook
Step 2: Add multiple source files (upload, link, or Drive) — up to 20 files
Step 3: Validate All — each file checked independently
         Duplicates (same SHA-256) rejected
Step 4: Push All — only available when every file passes validation
         Each file gets its own file_id
         Batch stops on first failure
         All results recorded in Push History
```

### 5.3 CLI Workflow

For automated or scripted environments:

```bash
# Step 1: Validate configuration + source
python3 tools/validator.py config.xlsx source.xlsx --ddl schema.sql

# Step 2: Push rows to PostgreSQL
python3 tools/executor.py config.xlsx source.xlsx --env .env --trace 3

# Step 3: Inspect loaded data
python3 tools/show_tables.py --config config.xlsx --env .env
```

### 5.4 Library Usage

Both stages are importable Python functions for embedding in custom scripts:

```python
import validator, executor

# Validate
issues = validator.validate(config=Path("config.xlsx"), source=Path("source.xlsx"))

# Generate DDL
validator.write_ddl(config, output=Path("schema.sql"), dialect="postgres")

# Push
result = executor.execute(config, source, target="postgres",
                          database="excel_parser",
                          schema_sql=Path("schema.sql").read_text())
print(f"{result.total} rows loaded, file_id={result.file_id}")
```

---

## 6. Feature Coverage

### 6.1 Parser Features

| Feature | Description |
|---|---|
| **Six data types** | `text`, `numeric`, `integer`, `date`, `timestamp`, `boolean` with automatic cleaning (currency symbols, commas, brackets for negatives, `%`, date formats) |
| **Five source_ref types** | `col:A` (cell), `const:value` (fixed), `fn:now` (computed), `expr:{A}+{B}` (expression), `map:v1\|\|v2` (positional) |
| **Row filtering** | `col:D > 0`, `col:B = "Delivered"`, `col:A is_not_empty` — combine with `AND` / `OR` |
| **28 cell scripts** | Post-cast transformations: `trim\|uppercase`, `round_2`, `pct_to_fraction`, `year_month`, etc. Chain with `\|` |
| **Null defaults** | Fill empty cells with a fallback (`0` for numeric, `N/A` for text) instead of NULL |
| **Date format pinning** | `%d/%m/%Y` or `%m/%d/%Y` to eliminate DD/MM vs MM/DD ambiguity |
| **Schema evolution** | New columns added via `ALTER TABLE`; removed columns keep data, get defaults |
| **Deduplication** | Re-loading a byte-identical file (same SHA-256) is refused |
| **Full lineage** | Every row carries `file_id`, `sheet_name`, `source_row_num` — traces back to one cell |
| **Integer or UUID keys** | Configurable per workbook via `id_type` |
| **CSV support** | CSV files work natively; filename stem becomes the sheet name |
| **Expressions** | `expr:({A} + {B}) * {C}`, string concat with `&`, column-name references, SQL-style NULL propagation |
| **Multi-block sheets** | Two or more data blocks on one worksheet become separate tables |
| **Key-value layout** | Label/value pairs (e.g., report headers) loaded as rows |
| **Strict mode** | Type mismatches block the push; skipped rows logged as warnings |

### 6.2 Type Cleaning Examples

| Data Type | Input (raw cell) | Output (database value) |
|---|---|---|
| `text` | `" VISA "` | `VISA` |
| `numeric` | `₹1,234.50` | `1234.5` |
| `numeric` | `(₹120.00)` | `-120.0` |
| `numeric` | `18%` | `18.0` |
| `integer` | `"42.7"` | `42` |
| `date` | `02-Aug-2026` | `2026-08-02` |
| `boolean` | `Yes` | `true` |

### 6.3 Web Application Features

| Feature | Description |
|---|---|
| **Design Mode** | Upload source + config, ER diagram (draggable, zoomable, FK edges), data preview, validation + data quality, push (schema only or schema + data) |
| **Batch Mode** | One config, many source files. Drag-and-drop, Google Drive, or Sheets links. Validate all, push all. Up to 20 files, 20 MB each |
| **Data Viewer** | Browse all pushed files (project + batch), search by name/database, per-table audit metadata |
| **Push History** | Unified timeline of all pushes across project and batch modes |
| **Google Drive** | OAuth + native Google Picker UI for file selection. Metadata cached to minimise API calls |
| **Browser File Pick** | Chrome/Edge: OS file picker with persistent handles for re-reading on render/push |
| **Sync Status** | Toolbar indicator: green (synced), amber (changed — re-render), red (sync failed) |
| **Dark/Light Theme** | Toggle in sidebar, persisted in localStorage |
| **Settings** | Poll interval (5s–60s), Drive connection, Data Viewer toggle, app/backend version |
| **CSV Export** | Export any rendered preview table as a CSV download |
| **DDL Viewer** | View the generated SQL schema as plain text |
| **Auto-Config (CSV)** | Generate a configuration workbook from a CSV file's headers |
| **Project Management** | CRUD, duplicate projects, per-project target overrides |

### 6.4 Tested Scenarios (17 Examples)

The platform ships with 17 worked examples covering every feature, each with
expected row counts verified by an automated regression suite:

| # | Scenario | Tables | Rows |
|---|---|---|---|
| 01 | One sheet, one table | 1 | 3 |
| 02 | Multi-block sheet, key-value, fences, active=N | 4 | 12 |
| 03 | UUID primary keys | 1 | 4 |
| 04 | PostgreSQL schema + prefix | 1 | 4 |
| 05 | All 6 data types with messy values | 1 | 4 |
| 06 | Foreign-key references | 2 | 9 |
| 07 | Validation errors (must fail) | — | — |
| 08 | Source mismatch (must fail) | — | — |
| 09 | Real Swiggy annexure | 14 | 222 |
| 12 | Petpooja daily growth (84 columns) | 1 | 31 |
| 13 | SmartQ payment report (3 blocks) | 3 | 33 |
| 14 | Zomato business (CSV, 36 columns) | 1 | 470 |
| 15 | Magicpin ledger (10 tables, 5 sheets) | 10 | 1,141 |
| 16 | All source_ref types | 1 | 3 |
| 17 | Kitchen sink (every feature) | 3 | 18 |

Real-world client files tested: Swiggy (14 tables, 222 rows), Zomato (470
rows), GrowthFalcons (5 tables, 109 rows), Petpooja (84 columns), SmartQ
(3 blocks on one sheet), Magicpin (10 tables across 5 sheets, 1,141 rows).

---

## 7. Security

| Area | Implementation |
|---|---|
| **Credentials** | Live only in `.env` / environment variables — never in a workbook, in code, in logs, or in API responses. `.env` is gitignored |
| **Password storage** | Argon2id hashes in PostgreSQL. Minimum 8 characters. 5 failed attempts lock the account for 5 minutes |
| **CSRF protection** | All mutating endpoints (POST/PATCH/DELETE) require `X-CSRF-Token` header matching the session cookie |
| **SQL injection prevention** | Every value goes to the database as a parameterised query parameter. Table/schema names from the workbook are validated against a strict allowlist (letters, digits, underscores only) before use |
| **Error handling** | Client-facing errors carry no stack traces, internal paths, or database schema details. Global exception handlers return safe messages; details logged server-side only |
| **Google OAuth** | Tokens stored server-side per user, never returned by the API |
| **Session management** | HTTP-only session cookies. `APP_ENV=production` enables secure cookies |
| **Input validation** | All configuration values validated at the boundary — invalid names, types, and references rejected before any database operation |

---

## 8. Deployment

### 8.1 Architecture

Split-container deployment: separate frontend (nginx) and backend (FastAPI)
containers, with PostgreSQL as an external dependency.

```
Browser → :4200 (nginx) → /api/*  proxied to backend:8000 (internal)
                        → /*      serves Angular SPA (static files)
```

### 8.2 Docker Compose (Production)

```yaml
services:
  backend:
    image: adarshbp/excel-parser-backend:latest
    env_file: .env
    environment:
      APP_ENV: production
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8000/api/health"]
      interval: 15s

  frontend:
    image: adarshbp/excel-parser-frontend:latest
    ports:
      - "4200:80"
    depends_on:
      backend:
        condition: service_healthy
```

### 8.3 Deployment Steps

```
Step 1: Provision PostgreSQL 14+ instance

Step 2: Create .env file with credentials
        (copy from .env.example, fill in PGHOST, PGUSER, PGPASSWORD, etc.)

Step 3: Pull and start containers
        $ docker compose up -d

Step 4: Create the initial user
        $ docker compose exec backend python3 users.py add admin

Step 5: Open http://<host>:4200 and sign in

Step 6: (Optional) Configure Google Drive
        Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_API_KEY in .env
        Restart the backend container
```

### 8.4 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PGHOST` | Yes | PostgreSQL host |
| `PGPORT` | No | PostgreSQL port (default 5432) |
| `PGUSER` | Yes | PostgreSQL user |
| `PGPASSWORD` | Yes | PostgreSQL password |
| `PGDATABASE` | No | Default database (overridden by config workbook) |
| `APP_SCHEMA` | No | App state schema (default `excelparser_config`) |
| `APP_ENV` | No | Set to `production` for secure cookies |
| `APP_ALLOWED_ORIGINS` | No | CORS allowed origins |
| `GOOGLE_CLIENT_ID` | No | For Google Drive integration |
| `GOOGLE_CLIENT_SECRET` | No | For Google Drive integration |
| `GOOGLE_API_KEY` | No | For Google Picker UI (Drive file selection) |

### 8.5 Build and Publish

```bash
# Build and push to Docker Hub
./util/docker-publish.sh             # pushes :latest tag
./util/docker-publish.sh v1.2.0      # pushes :v1.2.0 tag
```

### 8.6 Local Development

```bash
# Install dependencies
pip install -r app/backend/requirements.txt
(cd app/frontend && npm ci)            # requires Node 22+

# Start both services
cd app && ./run.sh                     # backend :8000, frontend :4200

# Or build locally with Docker
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build
```

### 8.7 Operational Commands

| Command | Purpose |
|---|---|
| `./util/seed.sh` | Create default user (admin / password) |
| `./util/clear_all.sh` | Wipe app state (PG schema) + cache, then re-seed |
| `./util/test-examples.sh` | Validate + push all 17 examples (regression test) |
| `./util/env-switch.sh <env>` | Switch `.env` between local / docker / prod |
| `GET /api/health` | Health check: `{"status": "ok", "version": "1.0.0"}` |

---

## 9. API Surface

The backend exposes **38 REST endpoints** grouped into 7 categories:

| Category | Endpoints | Description |
|---|---|---|
| **Health & Utilities** | 2 | Health check, configuration template download |
| **Authentication** | 4 | Login, logout, current user, password change |
| **Projects** | 6 | CRUD, duplicate, per-project settings |
| **Render & Push** | 7 | Validate + preview, poll for changes, push schema, push data, DDL viewer, CSV export |
| **Push History** | 2 | List all pushes (project + batch), run details |
| **Batch** | 6 | Validate + push multiple files (by ref or upload) |
| **Data Viewer** | 2 | Browse pushed files, file detail with audit metadata |
| **Google Drive** | 6 | OAuth flow, Picker, file browser, status, disconnect |
| **Uploads & Refs** | 3 | Upload workbook, test reference, auto-config from CSV |

All endpoints except health, login, template download, and OAuth callback
require session authentication. Mutating requests require CSRF token.

Errors return `{"detail": "..."}` with appropriate HTTP status codes:
- 400 — Validation error
- 401 — Not authenticated
- 404 — Not found
- 503 — Database error
- 500 — Unhandled error (safe message, details logged server-side)

---

## 10. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Parser** | Python 3.10+, openpyxl | Workbook reading, validation, type casting, row insertion |
| **Backend** | FastAPI, Pydantic, psycopg 3 | REST API, request validation, PostgreSQL driver |
| **Authentication** | Argon2id (argon2-cffi) | Password hashing |
| **Frontend** | Angular 22, Optimus UI | Single-page application, ER diagrams, data grids |
| **Database** | PostgreSQL 14+ | Application state + loaded data |
| **Reverse Proxy** | nginx | SPA serving, `/api` proxy, gzip, upload limits |
| **Deployment** | Docker, docker-compose | Containerised backend + frontend |
| **Integrations** | Google Drive API, Google Picker API | Cloud file selection and download |

---

## Appendix — Configuration Reference

### The Configuration Workbook

Three sheets define everything the parser needs:

#### `target_config` — Where the data goes

| Setting | Default | Description |
|---|---|---|
| `target` | `sqlite` | Database engine: `sqlite` or `postgres` |
| `database` | — | SQLite: file path. PostgreSQL: database name |
| `db_schema` | `public` | PostgreSQL schema (created if absent) |
| `table_prefix` | *(blank)* | Prefix for every generated table name |
| `id_type` | `integer` | `integer` (auto-increment) or `uuid` |

#### `sheet_config` — Which blocks to read (one row = one table)

| Column | Required | Description |
|---|---|---|
| `table_name` | Yes | Logical table name (lowercase snake_case) |
| `sheet_name` | Yes | Worksheet name in the source file (exact match) |
| `layout` | Yes | `table` (header + data rows) or `key_value` (label/value pairs) |
| `header_row` | No | Row holding the headers (for audit/readability) |
| `data_start_row` | Yes | First row of real data (1-based) |
| `data_end_row` | No | Last row of data (blank = read to end) |
| `active` | Yes | `Y` to load, `N` to skip |
| `row_filter` | No | Skip rows by condition (e.g., `col:D > 0`) |
| `description` | No | Written as `COMMENT ON TABLE` in PostgreSQL |
| `domain` | No | Business domain (e.g., `finance`, `sales`) |

#### `column_config` — Which cells to read (one row = one column)

| Column | Required | Description |
|---|---|---|
| `table_name` | Yes | Must match a `sheet_config.table_name` |
| `source_ref` | Yes | Where to get the value: `col:A`, `const:INR`, `fn:now`, `expr:{A}+{B}`, `map:v1\|\|v2` |
| `column_name` | Yes | Database column name (lowercase snake_case) |
| `data_type` | Yes | `text`, `numeric`, `integer`, `date`, `timestamp`, `boolean` |
| `nullable` | Yes | `Y` (allow NULL) or `N` (reject row if empty) |
| `is_key` | Yes | `Y` creates a non-unique index |
| `column_order` | Yes | Controls column order in the generated table |
| `references` | No | FK declaration: `table_name.column_name` (for ER diagram) |
| `null_default` | No | Value to store when cell is empty (e.g., `0`, `N/A`) |
| `script` | No | Post-cast transformation (e.g., `trim\|uppercase`, `round_2`) |
| `date_format` | No | Pin date parsing: `%d/%m/%Y` or `%m/%d/%Y` |
| `description` | No | Written as `COMMENT ON COLUMN` in PostgreSQL |

### Available Scripts (28)

**Text:** `uppercase`, `lowercase`, `titlecase`, `trim`, `strip_spaces`,
`collapse_spaces`, `replace_newlines`, `digits_only`, `letters_only`,
`alphanum_only`, `remove_punctuation`, `first_word`, `last_word`, `left_10`,
`right_10`, `slug`

**Numeric:** `abs`, `negate`, `round_2`, `round_1`, `round_0`, `floor`,
`ceil`, `pct_to_fraction`, `fraction_to_pct`, `clamp_0`

**Date:** `date_only`, `year_month`, `year_only`

**Guard:** `not_null`, `not_empty`

---

*This document describes the Excel Parser platform as of September 2026.*
