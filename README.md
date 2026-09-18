# Excel Parser

**Config-driven Excel-to-database loading.** Two workbooks in (a configuration
workbook and a source workbook), structured tables out, in PostgreSQL or SQLite.

```
configuration workbook  ─┐
                         ├─►  validator  ──►  Is this loadable?  +  CREATE TABLE DDL
source workbook  ────────┘
         │
         └──────────────────►  executor  ──►  PostgreSQL  or  SQLite
                                         (target_config says which;
                                          .env has the credentials)
```

No sheet name, column letter, or row number is hardcoded in the code.
Everything lives in the configuration workbook.

---

## Table of Contents

- [Why](#why)
- [Features](#features)
- [Quick Start](#quick-start)
- [Using as a Python Library](#using-as-a-python-library)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Examples](#examples)
- [Configuration Reference](#configuration-reference)
- [Docker Deployment](#docker-deployment)
- [Environment Variables](#environment-variables)
- [API](#api)
- [Documentation](#documentation)
- [Development](#development)
- [Tech Stack](#tech-stack)

---

## Why

Spreadsheets from vendors, partners, and internal teams arrive in every shape:
merged headers, summary rows, multi-block sheets, key-value metadata, currency
symbols, inconsistent dates. Getting this data into a database usually means a
one-off script per file layout.

Excel Parser replaces those scripts with a **declarative configuration
workbook** that maps blocks of cells to typed database columns. Change the
configuration, not the code.

---

## Features

### Parser

- **Six data types** — `text`, `numeric`, `integer`, `date`, `timestamp`,
  `boolean`, with automatic cleaning (currency symbols, commas, brackets for
  negatives, `%`, date formats).
- **Five `source_ref` types** — `col:A` (read a cell), `const:value` (fixed
  value), `fn:now` (computed at load time), `expr:{A} + {B}` (expressions
  across columns), `map:v1||v2||v3` (positional labels for key-value blocks).
- **`row_filter`** — skip rows by condition: `col:D > 0`,
  `col:B = "Delivered"`, `col:A is_not_empty`. Combine with `AND` / `OR`.
- **28 cell scripts** — post-cast transformations (`trim|uppercase`,
  `round_2`, `pct_to_fraction`, `year_month`, `not_null`, and more). Chain
  with `|`.
- **`null_default`** — fill empty cells with a fallback (`0` for numeric,
  `N/A` for text) instead of NULL.
- **`date_format`** — pin date parsing to eliminate DD/MM vs MM/DD ambiguity.
- **Schema evolution** — new columns are added automatically via
  `ALTER TABLE`; removed columns keep their data and get defaults on new rows.
- **Dedup** — re-loading a byte-identical file (same SHA-256) is refused.
- **Full lineage** — every row carries `file_id`, `sheet_name`, and
  `source_row_num`, unique together, so any value traces back to one cell.
- **Integer or UUID keys** — `id_type` in `target_config` switches between
  auto-incrementing counters and UUIDs, with no database extension needed.
- **CSV support** — CSV files work natively; the filename stem becomes the
  sheet name.
- **Expressions** — `expr:({A} + {B}) * {C}`, string concatenation with `&`,
  column-name references `{column_name}`, unary minus, fn/const inside
  expressions, SQL-style NULL propagation.

### Web Application

- **Design mode** — upload source + config, see the schema as a draggable ER
  diagram, preview data rows (each cell linked to its source), review
  validation issues and data quality, then push (schema only or schema + data).
- **Batch mode** — one config, many source files. Drag-and-drop upload, Google
  Drive, or Sheets links. Validate all, push all. Each file gets its own
  `file_id`.
- **Data Viewer** — browse every pushed file, search by name or database, see
  per-table audit metadata.
- **Google Drive integration** — OAuth + native Google Picker UI for file
  selection. Drive metadata is cached to minimize API calls.
- **Browser file pick** — Chrome/Edge users can select local files via the OS
  file picker with persistent handles for re-reading on render/push.
- **Sync status** — toolbar indicator (green/amber/red) shows whether
  workbooks have changed since the last render.
- **Dark/light theme** — toggle in the sidebar, persisted in localStorage.
- **Settings** — poll interval, Drive connection, Data Viewer toggle, app
  version.

### Security

- Credentials only in `.env` / environment — never in a workbook, in the code,
  in a log line, or in an API response.
- Argon2id password hashing. CSRF protection on all mutating endpoints.
- Every value goes to the database as a query parameter; identifiers are
  validated before use.
- Client-facing errors carry no stack traces or internal paths.
- Google OAuth tokens stored server-side, never returned by the API.

---

## Quick start

### Prerequisites

- **Python 3.10+** and `openpyxl`
- **PostgreSQL 14+** (or SQLite for local testing)
- **Node 22+** (only if running the frontend locally)

### Command-line tools

```bash
pip install openpyxl "psycopg[binary]"

cd examples/01_simple
python3 ../../tools/validator.py sales_config.xlsx sales_source.xlsx \
        --ddl schema.postgres.sql
python3 ../../tools/executor.py  sales_config.xlsx sales_source.xlsx \
        --env ../../.env --trace 3
```

The target, database, schema, and prefix come from the workbook's
`target_config` sheet. Credentials come from `.env` (copy `.env.example`
and fill it in).

### Web application (Docker)

```bash
# Production: pull from Docker Hub
docker compose up -d
./util/seed.sh                     # create default user (admin / password)
```

Open <http://localhost:4200> and sign in.

```bash
# Local dev: build from source
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build
```

### Web application (local)

```bash
pip install -r app/backend/requirements.txt
(cd app/frontend && npm ci)        # Node 22+

./util/seed.sh                     # create default user
cd app && ./run.sh                 # backend :8000, frontend :4200
```

---

## Using as a Python library

Both stages are plain importable functions — no CLI required. You can call them
from any Python script, notebook, or application.

### Install

```bash
pip install openpyxl                       # required
pip install "psycopg[binary]"              # only for PostgreSQL target
```

### Step 1 — Validate

```python
import sys
sys.path.insert(0, "tools")                # add the tools/ directory to the path

from pathlib import Path
import validator

issues = validator.validate(
    config=Path("sales_config.xlsx"),
    source=Path("sales_source.xlsx"),
)

errors   = [i for i in issues if i.severity == "error"]
warnings = [i for i in issues if i.severity == "warning"]

for issue in issues:
    print(f"{issue.severity:<8} {issue.where}: {issue.message}")

if errors:
    print(f"NOT loadable — {len(errors)} error(s)")
else:
    print(f"OK to load — {len(warnings)} warning(s)")
```

### Step 2 — Generate the DDL

```python
# Only when validation passed (no errors)
tables = validator.write_ddl(
    config=Path("sales_config.xlsx"),
    output=Path("schema.postgres.sql"),
    dialect="postgres",                    # or "sqlite"
    prefix="",                             # table prefix (blank = none)
    id_type="integer",                     # or "uuid"
)
print(f"Wrote DDL for {tables} tables")
```

### Step 3 — Execute (push rows)

```python
import executor

result = executor.execute(
    config=Path("sales_config.xlsx"),
    source=Path("sales_source.xlsx"),
    target="postgres",                     # or "sqlite"
    database="excel_parser",               # PG database name or SQLite file path
    schema_sql=Path("schema.postgres.sql").read_text(),
    trace=0,                               # set > 0 to see per-row detail
    log=print,                             # or lambda line: None for silence
    id_type="integer",                     # or "uuid"
    strict=True,                           # block push on type mismatches
)

print(f"file_id:  {result.file_id}")
print(f"total:    {result.total} rows")
print(f"tables:   {result.per_table}")
print(f"skipped:  {result.skipped_rows}")
print(f"bad:      {result.bad_cells}")
print(f"target:   {result.target}")
```

### Step 4 — Preview (without writing)

```python
import preview

# Schema model (what the ER diagram shows)
tables = preview.model(config=Path("sales_config.xlsx"))
for t in tables:
    print(f"{t['table_name']}: {len(t['columns'])} columns")

# Data preview (first 20 rows per table)
previews = preview.previews(
    config=Path("sales_config.xlsx"),
    source=Path("sales_source.xlsx"),
    limit=20,
)
for table, data in previews.items():
    print(f"{table}: {data['loadable_rows']} rows, "
          f"{len(data['bad_cells'])} bad cells")
```

### Full example script

```python
"""Load a source workbook into PostgreSQL — complete script."""
import sys
sys.path.insert(0, "tools")

from pathlib import Path
import validator, executor

config = Path("examples/01_simple/sales_config.xlsx")
source = Path("examples/01_simple/sales_source.xlsx")

# 1. Validate
issues = validator.validate(config, source)
errors = [i for i in issues if i.severity == "error"]
if errors:
    for e in errors:
        print(f"ERROR  {e.where}: {e.message}")
    raise SystemExit("Validation failed")

# 2. Generate DDL
ddl_path = Path("schema.postgres.sql")
validator.write_ddl(config, ddl_path, "postgres", prefix="")

# 3. Push
result = executor.execute(
    config, source,
    target="sqlite",
    database="output.db",
    schema_sql=ddl_path.read_text(),
    log=print,
)
print(f"\nDone: {result.total} rows → {result.target}")
```

> **Note:** For PostgreSQL, set `PGHOST`, `PGUSER`, `PGPASSWORD` in `.env` or
> as environment variables before running. The `db` module reads them
> automatically. See `.env.example` for all settings.

---

## How it works

### Two stages, deliberately separated

| Stage | Tool | What it does | Writes to DB? |
|---|---|---|---|
| **Validate** | `validator.py` | Checks config + source, dry-runs every cell, writes DDL | No |
| **Execute** | `executor.py` | Reads configured cells, casts, inserts with lineage | Yes |

Both are importable: `validate()` returns `Issue` records and prints nothing;
`execute()` returns a `LoadResult` and takes a `log=` callable. The web
application calls them directly — the browser and the CLI can never disagree.

### The configuration workbook

Three sheets:

| Sheet | Purpose |
|---|---|
| `target_config` | Where the data goes (target, database, schema, prefix, key type) |
| `sheet_config` | Which blocks to read — one row = one database table |
| `column_config` | Which cells to read — one row = one database column |

Start from `template/config_template.xlsx` — it has every header explained
with hover comments and `help_*` sheets.

### `source_ref` — where each column gets its value

| Format | Description | Example |
|---|---|---|
| `col:<letter>` | Read from an Excel column | `col:A`, `col:AM` |
| `const:<value>` | Fixed value for every row | `const:INR`, `const:v2` |
| `fn:<name>` | Computed at load time | `fn:now`, `fn:uuid`, `fn:sequence` |
| `expr:<expression>` | Calculated from other columns | `expr:{D} * {E} / 100` |
| `map:v1\|\|v2\|\|...` | Positional — different value per row | `map:Name\|\|Area\|\|City` |

---

## Project structure

```
tools/
  validator.py         Stage 1 — validate + generate DDL
  executor.py          Stage 2 — read, cast, insert
  values.py            Cell-to-database-value casting
  rows.py              Row reading (shared by executor + preview)
  preview.py           Schema model + data preview for the app
  db.py                Database targets (SQLite + PostgreSQL) + .env reader
  make_template.py     Regenerate template/config_template.xlsx
  make_examples.py     Regenerate examples 03–05, 07–08, 16–17
  show_tables.py       Dump loaded tables
  run_queries.py       Run SQL queries against loaded data

app/
  backend/             FastAPI (main.py, auth.py, state.py, service.py,
                       batch.py, sources.py, drive.py, users.py)
  frontend/            Angular 22 + Optimus UI (@openng/optimus-ui)
  run.sh               Start backend :8000 + frontend :4200

examples/
  01_simple/           One sheet, one table, 3 rows
  02_features/         Key-value blocks, multi-block sheets, fences, active=N
  03_uuid_keys/        UUID primary keys
  04_postgres_schema/  PostgreSQL schema + prefix
  05_data_types/       All 6 data types with messy values
  06_references/       Foreign-key references (orders + items)
  07_validation_errors/ Deliberately broken config (must fail)
  08_source_mismatch/  Right config, wrong source (must fail)
  09_swiggy_annexure/  Real client: 14 tables, 222 rows
  10–15               More real-world client files
  16_source_ref_showcase/ All source_ref types demonstrated
  17_kitchen_sink/     Every feature in one file (regression test)

template/              config_template.xlsx — starting point for new configs
docs/                  CONFIG_RULES.md, CONFIG_AUTHORING_GUIDE.md,
                       EXAMPLES.md, RUNNING.md, APP_RUNNING.md, API.md
util/                  seed.sh, clear_all.sh, test-examples.sh,
                       docker-publish.sh, env-switch.sh

Dockerfile             Monolithic image (backend + frontend)
app/backend/Dockerfile    Backend-only image
app/frontend/Dockerfile   Frontend-only image (Angular + nginx)
docker-compose.yml        Production: pull from Docker Hub
docker-compose.build.yml  Dev override: build locally
```

---

## Examples

17 examples cover every feature. Run them all with:

```bash
./util/test-examples.sh              # validate + push to PostgreSQL
./util/test-examples.sh --validate   # validate only, no push
```

| # | Scenario | Tables | Rows |
|---|---|---|---|
| 01 | One sheet, one table | 1 | 3 |
| 02 | Multi-block sheet, key-value, fences | 4 | 12 |
| 03 | UUID primary keys | 1 | 4 |
| 04 | PostgreSQL schema + prefix | 1 | 4 |
| 05 | All 6 data types | 1 | 4 |
| 06 | Foreign-key references | 2 | 9 |
| 07 | Validation errors (must fail) | — | — |
| 08 | Source mismatch (must fail) | — | — |
| 09 | Real Swiggy annexure | 14 | 222 |
| 12 | Petpooja daily growth | 1 | 31 |
| 13 | SmartQ payment report | 3 | 33 |
| 14 | Zomato business (CSV) | 1 | 470 |
| 15 | Magicpin ledger (10 tables) | 10 | 1141 |
| 16 | All source_ref types | 1 | 3 |
| 17 | Kitchen sink (every feature) | 3 | 18 |

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for full details and expected output.

---

## Configuration reference

See [docs/CONFIG_RULES.md](docs/CONFIG_RULES.md) for the complete reference, or
[docs/CONFIG_AUTHORING_GUIDE.md](docs/CONFIG_AUTHORING_GUIDE.md) for a
step-by-step walkthrough.

### Data types

| Type | What the parser does | Example |
|---|---|---|
| `text` | Trims whitespace; empty → NULL | `" VISA "` → `VISA` |
| `numeric` | Strips `₹`, commas, `%`; brackets → negative | `₹1,234.50` → `1234.5` |
| `integer` | Like numeric, truncated to whole number | `"42.7"` → `42` |
| `date` | Normalizes to `YYYY-MM-DD` | `02-Aug-2026` → `2026-08-02` |
| `timestamp` | Date + time | `2026-08-02 19:45` |
| `boolean` | `y/yes/true/1` → true; `n/no/false/0` → false | `Yes` → `true` |

### Automatic lineage columns

Every table gets these for free:

```
<table_name>_id    surrogate key (integer or UUID)
file_id            which load this row came from
file_name          source file name
file_sha256        content hash (for dedup)
source_ref         original reference (Drive link, upload ref, etc.)
sheet_name         worksheet the row came from
source_row_num     1-based Excel row number
```

---

## Docker deployment

Split architecture: separate frontend (nginx) and backend (FastAPI) containers.

```
Browser → :4200 (nginx) → /api/* proxied to backend:8000 (internal)
                        → /*     serves Angular SPA
```

```bash
# Production
docker compose up -d

# Dev (build locally)
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build

# Build and push images
./util/docker-publish.sh             # pushes :latest
./util/docker-publish.sh v1.2.0      # pushes :v1.2.0
```

Environment files: `.env.local` (run.sh), `.env.docker` (local Docker),
`.env.prod` (server). Switch with `./util/env-switch.sh <local|docker|prod>`.

---

## Environment variables

Copy `.env.example` to `.env` and fill in your values:

| Variable | Required | Description |
|---|---|---|
| `PGHOST` | yes | PostgreSQL host |
| `PGPORT` | no | PostgreSQL port (default 5432) |
| `PGUSER` | yes | PostgreSQL user |
| `PGPASSWORD` | yes | PostgreSQL password |
| `PGDATABASE` | no | Default database (overridden by config) |
| `APP_SCHEMA` | no | App state schema (default `excelparser_config`) |
| `APP_ENV` | no | `production` for secure cookies |
| `APP_ALLOWED_ORIGINS` | no | CORS origins |
| `GOOGLE_CLIENT_ID` | no | For Google Drive integration |
| `GOOGLE_CLIENT_SECRET` | no | For Google Drive integration |
| `GOOGLE_API_KEY` | no | For Google Picker UI |

---

## API

38 endpoints. See [docs/API.md](docs/API.md) for the full reference.

| Category | Endpoints |
|---|---|
| Health & utilities | `GET /api/health`, `GET /api/template` |
| Authentication | login, logout, me, password change |
| Projects | CRUD, duplicate, render, push, push-schema, DDL, CSV export |
| Batch | validate + push multiple files |
| Data Viewer | browse pushed files with audit metadata |
| Google Drive | OAuth flow, Picker, file browser |

---

## Documentation

| Document | What it covers |
|---|---|
| [CONFIG_RULES.md](docs/CONFIG_RULES.md) | Configuration reference — every column, every rule |
| [CONFIG_AUTHORING_GUIDE.md](docs/CONFIG_AUTHORING_GUIDE.md) | Step-by-step guide to writing configs from scratch |
| [EXAMPLES.md](docs/EXAMPLES.md) | All 17 examples explained with expected output |
| [RUNNING.md](docs/RUNNING.md) | CLI step-by-step: validate, execute, inspect |
| [APP_RUNNING.md](docs/APP_RUNNING.md) | Web application: install, login, use |
| [API.md](docs/API.md) | REST API reference (38 endpoints) |

---

## Development

### Checks

```bash
python3 -m pyflakes tools app/backend         # lint
(cd app/frontend && npm run build)            # Angular build (Node 22+)
./util/test-examples.sh                       # all 17 examples
./util/test-examples.sh --validate            # validate only
```

### Useful commands

```bash
./util/seed.sh                                # create admin / password
SEED_USER=alice SEED_PASS=secret ./util/seed.sh  # custom user
./util/clear_all.sh                           # wipe app state + re-seed

# Regenerate generated files
cd tools && python3 make_template.py ../template/config_template.xlsx
cd tools && python3 make_examples.py
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Parser | Python 3, openpyxl |
| Backend | FastAPI, Pydantic, psycopg 3, Argon2 |
| Frontend | Angular 22, Optimus UI |
| Database | PostgreSQL 14+ (app state + loaded data) |
| Deployment | Docker, nginx, docker-compose |


