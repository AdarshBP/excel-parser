# AGENTS.md — Excel Parser

Config-driven Excel → database loading. Two workbooks in (a *configuration*
workbook and a *source* workbook), tables and rows out, in PostgreSQL (or SQLite).
`app/` is a web front end over exactly the same functions — it never parses
anything itself.

Read `README.md`, then `docs/CONFIG_RULES.md` before touching anything that
reads a workbook.

## The rule that shapes everything

One active row of `sheet_config` = one independent flat table. Blocks are read
exactly as they sit in the sheet: nothing is merged, joined, normalised or
derived, and two blocks on one worksheet are two separate tables. Do not add
inference about what the data "means".

Every staged row carries its origin — `file_id`, `sheet_name`,
`source_row_num`, unique together. `source_file` and `load_config_audit` hold
the file and load metadata. The only real relationship in the schema is
`file_id → load_config_audit.file_id`; there are no foreign keys between blocks.

## Layout

```
tools/validator.py   stage 1 — decides: is this loadable? writes the DDL. Never writes to a DB.
tools/executor.py    stage 2 — dumps: read configured cells, cast, insert with lineage.
tools/values.py      cell -> database value casting, shared by both stages
tools/rows.py        row reading, shared by executor and preview
tools/preview.py     the model + cast-row previews the app renders
tools/db.py          the two database targets and the .env reader
tools/make_template.py, tools/make_examples.py   regenerate template/ and examples 03-05, 07-08, 16-17

app/backend/         FastAPI: main.py (endpoints), auth.py, state.py (PostgreSQL),
                     service.py, batch.py, sources.py (upload / link / Drive),
                     drive.py (Google OAuth + Drive), users.py (accounts CLI)
app/frontend/        Angular 22 + Optimus UI (@openng/optimus-ui)
app/frontend/nginx.conf  production nginx: SPA + /api proxy + upload size
app/run.sh           starts backend :8000 and frontend :4200

util/seed.sh         create the default user (admin/password)
util/clear_all.sh    wipe app state (PG schema) + cache, then re-seed
util/test-examples.sh  validate + push all examples, compare row counts
util/docker-publish.sh  build + push Docker images to Hub
util/env-switch.sh   switch .env between local/docker/prod

examples/01..17      each folder holds only the two workbooks
template/            config_template.xlsx — every header explained
docs/                EXAMPLES.md, CONFIG_RULES.md, RUNNING.md, APP_RUNNING.md, APP_PLAN.md, API.md
Dockerfile           monolithic image (backend + frontend), PG external
app/backend/Dockerfile   backend-only image
app/frontend/Dockerfile  frontend-only image (Angular build + nginx)
docker-compose.yml       production: pull from Docker Hub
docker-compose.build.yml dev override: build locally + host.docker.internal
```

## Setup

```bash
pip install -r app/backend/requirements.txt        # backend
(cd app/frontend && npm ci)                        # needs Node 22+
```

Or with Docker (split frontend + backend):

```bash
# Local dev: build from source
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build

# Production: pull from Docker Hub
docker compose up -d

# Build and push images
./util/docker-publish.sh             # pushes :latest
./util/docker-publish.sh v1.2.0      # pushes :v1.2.0
```

Environment files: `.env.local` (run.sh), `.env.docker` (local Docker),
`.env.prod` (server). Switch with `./util/env-switch.sh <local|docker|prod>`.

## Commands

Parser, from inside an example folder:

```bash
cd examples/01_simple
python3 ../../tools/validator.py sales_config.xlsx sales_source.xlsx --ddl schema.postgres.sql
python3 ../../tools/executor.py  sales_config.xlsx sales_source.xlsx --trace 3
python3 ../../tools/show_tables.py --config sales_config.xlsx
```

`executor.py` needs the DDL file the validator wrote, in the working directory.

Application:

```bash
./util/seed.sh                                     # create default user (admin/password)
SEED_USER=alice SEED_PASS=mysecpass1 ./util/seed.sh  # or a custom user
./util/clear_all.sh                                # wipe PG app schema + cache, then re-seed
cd app/backend && python3 users.py add <name>      # interactive alternative (prompts for password)
cd app && ./run.sh                                 # or ./run.sh backend | frontend
```

Checks to run before calling a change done:

```bash
python3 -m pyflakes tools app/backend
(cd app/frontend && npm run build)                 # Node 22+ required
./util/test-examples.sh                            # validate + push all examples to PG
./util/test-examples.sh --validate                 # validate only, no push
```

Expected row counts (verified by `test-examples.sh`): 01 = 3, 02 = 12,
03 = 4 (UUID), 04 = 4, 05 = 4, 06 = 9 (3+6), 12 = 31, 13 = 33,
14 = 470 (CSV), 15 = 1141, 16 = 3, 17 = 18 (5+8+5).
09 (Swiggy) = 217, 11 (GrowthFalcons) = 109 — client files, skipped if absent.
Examples 07 and 08 must fail validation and exit 1 with nothing written.

## Application features

* **Design mode** (`/project/:id`): configure source + config workbook, render
  the schema as an ER diagram (with drag, zoom, FK edges), preview data rows,
  see validation + data quality issues, push schema only or schema + data.
* **Batch mode** (`/batch`): select one config + upload multiple source files
  (drag & drop / file picker, Google Sheets link, or Google Drive). Files are
  validated and pushed **one at a time** with live progress. Each file gets its
  own `file_id`. Max 20 files per batch, 20 MB each. Uploaded files are
  processed in memory — nothing is saved to disk after the request. All batch
  push endpoints (`push`, `push-one`, `push-upload`) record results in the
  `batch` table so they appear in Push history.
* **Data Viewer** (`/data-viewer`): browse all pushed files (from both project
  and batch pushes), search by name/database, view per-table breakdown with
  audit metadata from `load_config_audit`. Enable via Settings toggle.
* **Side navigation**: always-expanded sidebar with branded EP icon,
  Configurations, Batch run, Data Viewer (optional), Push history, theme
  toggle, and user avatar with sign-out.
* **Settings page** (`/settings`): poll interval (5s/10s/15s/30s/60s, default
  10s), Google Drive connection status + disconnect, about section with app
  version + backend version. Persisted in localStorage.
* **Sync status indicator**: toolbar shows green dot + "Synced [time]" when
  up to date, amber pulsing dot + "Changed — re-render" when the workbook
  changed, red pulsing dot + "Sync failed" on connection/Drive error.
* **Tooltips**: all buttons across the app have tooltips with consistent
  positioning.
* **Strict mode**: type mismatches block the push. Skipped rows (empty
  required columns) and empty sections are logged as warnings but do not
  block — these are normal for multi-block sheets like Swiggy annexures.
* **`null_default`**: optional column in `column_config` — what to store when
  a cell is empty (e.g. `0` for numeric, `N/A` for text).
* **`references`**: optional column in `column_config` — declares an FK
  relationship shown as a dashed line in the ER diagram.
* **`source_ref` formats**: `col:<letter>` reads from an Excel column,
  `const:<value>` fills every row with a fixed value, `fn:<name>` fills every
  row with a computed value (`now`, `today`, `uuid`, `file_name`, `sequence`),
  `expr:<expression>` computes a value from other columns (e.g.
  `expr:({A} + {B}) * {C}`, `expr:{A} & " - " & {C}`; operators: `+`, `-`,
  `*`, `/`, `&`, parentheses `()`, unary minus `-{X}`). NULL in arithmetic
  → NULL (like SQL). `script` and `null_default` apply after the result is
  cast. Expressions can reference other computed column names with
  `{column_name}` syntax (two-pass: col/const/fn first, expr second).
  Expression tokens are cached per load for performance.
* **`row_filter`**: optional column in `sheet_config` — skip rows that
  don't match. Syntax: `col:D > 0`, `col:B = "Delivered"`,
  `col:A is_not_empty`. Operators: `=`, `!=`, `>`, `<`, `>=`, `<=`,
  `contains`, `not_contains`, `is_empty`, `is_not_empty`. Combine with
  `AND` / `OR`.
* **`date_format`**: optional column in `column_config` — pins the date
  parsing to a specific strptime format (e.g. `%m/%d/%Y` for US dates,
  `%d/%m/%Y` for EU/Indian). Eliminates DD/MM vs MM/DD ambiguity.
* **`script`**: optional column in `column_config` — post-cast transformations
  (e.g. `trim|uppercase`, `round_2`, `pct_to_fraction`). 28 scripts available
  across text, numeric, date, and guard categories. See `CONFIG_RULES.md`.
* **Dark/light theme**: toggle in the sidebar, persisted in localStorage.
* **Google Picker API**: Drive file selection uses Google's native Picker UI
  instead of a custom file list dialog. Requires `GOOGLE_API_KEY` in `.env`.
  Backend endpoint `GET /api/drive/picker` returns the API key + access token.
* **Backend health**: `GET /api/health` returns `{status, version}`.
* **Drive caching**: downloads always fresh; metadata cached 30s for poll
  fingerprinting; Drive status cached 10s across components; file names
  cached permanently per session. Auto-test debounced to 800ms.
* **Browser file pick (File System Access API)**: on Chrome/Edge, users can
  pick local files via the OS file picker. The browser holds a persistent
  `FileSystemFileHandle` so files can be re-read on render/push without
  re-selecting. Files are uploaded to `POST /api/upload-workbook` and stored
  content-addressed in `cache/` as `upload:<hash>.<ext>` refs. Client-side
  change detection compares `File.lastModified` on each poll. Not available
  in Firefox/Safari — those browsers fall back to the Link/Drive modes.
  Service: `app/frontend/src/app/core/file-handle.ts`.

## Conventions

* The parser knows nothing about where a workbook came from: every source is
  handed to it as an `.xlsx` on disk. New source types belong in
  `app/backend/sources.py`, not in `tools/`.
* Both stages are importable and quiet: `validate()` returns `Issue` records,
  `execute()` returns a `LoadResult` and takes a `log=` callable. Keep printing
  in the CLI layer.
* Anything that changes the configuration format needs `docs/CONFIG_RULES.md`,
  `template/config_template.xlsx` (via `tools/make_template.py`) and every
  example configuration updated together, and the examples re-run.
* Small, focused edits; no `Any`/`getattr`/`setattr`; imports at the top.
* Application state lives in PostgreSQL under `APP_SCHEMA` (default
  `excelparser_config`), not SQLite. Loaded data goes to a separate schema
  chosen by the user's `target_config`.

## Security

* Credentials live only in `.env` / the environment — never in a workbook, in
  the code, in a log line or in an API response. `.env` is gitignored.
* Passwords are Argon2id hashes. Google OAuth tokens are stored server-side per
  application user and are never returned by the API.
* Every value goes to the database as a query parameter; identifiers
  (table/schema names from the workbook) are validated before use.
* Workbook sources are browser uploads (content-addressed `upload:` refs in
  `cache/`), Google Sheets links, or Google Drive files. Local file paths
  are accepted only for backward compatibility and are restricted to the
  project directory.
* Client-facing errors must not carry stack traces or internal paths.
* Global exception handlers catch DB errors (503) and unhandled errors (500)
  with safe messages; details are logged server-side only.

## Schema evolution

When the configuration adds or removes columns between loads:

* **Column added**: `db.py` detects the new column via `_add_missing_columns()`
  and runs `ALTER TABLE ADD COLUMN` automatically. New columns are nullable
  (existing rows get NULL).
* **Column removed**: the column stays in the database. New rows get a
  type-appropriate default (0 for numeric, false for boolean, NULL for text/date).
  The executor detects orphaned columns via `table_columns()` and includes them
  in the INSERT with defaults. A log line is emitted for each orphaned column.
* **Dedup**: the executor refuses to load a file with identical SHA256 content.
  In batch mode, this check runs during validation so duplicates are caught
  before the user clicks Push.
* **Deferred schema creation**: `PostgresTarget.__init__()` only sets
  `search_path` — it never runs `CREATE SCHEMA`. The schema is created inside
  `ensure_schema()`, which is called only during an actual push. This prevents
  read-only operations (validation, duplicate checks) from silently recreating
  a schema that was dropped by `clear_all.sh`.

## Docker deployment

Split architecture: separate frontend (nginx) and backend (FastAPI) containers.

```
Browser → :4200 (nginx) → /api/* proxied to backend:8000 (internal)
                        → /*     serves Angular SPA
```

* `docker-compose.yml` — production: pulls from Docker Hub
* `docker-compose.build.yml` — dev override: builds locally
* `app/backend/Dockerfile` — mirrors repo layout at `/excel_parser/` so
  `state.py`'s `PROJECT_ROOT` resolves correctly
* `app/frontend/Dockerfile` — Angular build → nginx with SPA fallback
* `app/frontend/nginx.conf` — proxies `/api`, passes cookies, 50 MB upload limit
* `.env.example` — template with all settings documented
* `.env.local` / `.env.docker` / `.env.prod` — per-environment configs (gitignored)

Google OAuth redirect URI must match the entry point:
* Local dev (`run.sh`): `http://localhost:8000/api/auth/callback/google`
* Docker / production: `http(s)://<domain>/api/auth/callback/google`

Public pages for Google OAuth verification: `/home`, `/privacy`, `/terms`
(static HTML in `app/frontend/public/`, served by nginx).

## Client file examples (12–15)

Real-world client workbooks live in `clientFiles/`. Configs for them follow the
same pattern as examples 01–11 but cover wider layouts:

| Example | Source type | Tables | Key layout challenge |
|---|---|---|---|
| `12_petpooja_growth` | xlsx, 1 sheet | 1 table, 84 cols (A–CF) | Skip summary rows 7–10 (`data_start_row=11`); wide daily report |
| `13_smartq_payment` | xlsx, 1 sheet | 3 tables on one sheet | Gaps between blocks — fence each with `data_start_row`/`data_end_row`; `'-'` values → NULL via money cast |
| `14_zomato_business` | **CSV** | 1 pivoted table, 36 cols | 10 restaurants × 47 metrics; 30 date columns (G–AJ); CSV sheet name = file stem |
| `15_magicpin_ledger` | xlsx, 5 sheets | 10 active + 1 inactive | 7 sections on "Payout Breakup" sheet (each its own table); 976-row Order Level; empty "Additional Deductions" set `active=N` |

Expected row counts: 12 = 31, 13 = 33 (5+8+20), 14 = 470, 15 = 1141
(976+7+7+14+3+3+4+2+64+61).

## How to create a config for a new client file

1. **Inspect the source** — open with openpyxl (`data_only=True`), print every
   row with non-null cells. Note sheet names, header rows, where data starts,
   summary/total rows to skip, empty gaps between blocks, and the last data row.
2. **Map blocks** — each contiguous data block with its own header becomes one
   row in `sheet_config` (a separate `table_name`). Multiple blocks on one
   sheet are fine — fence them with `header_row`, `data_start_row`,
   `data_end_row`. Use `layout=key_value` for label/value pairs (no header
   row), `layout=table` for header + data rows.
3. **Map columns** — for each block, list every column letter → `column_name`,
   pick `data_type` from the messiest value (not the first one), set
   `nullable=N` only for columns that truly must never be empty, mark natural
   keys with `is_key=Y`.
4. **Generate the xlsx** — use openpyxl to write `readme`, `target_config`,
   `sheet_config`, `column_config` sheets. Follow the Swiggy/SmartQ examples
   for the exact header row.
5. **Re-save the source if needed** — some xlsx files lack dimension metadata
   (`max_row=None` in read-only mode). Open + save with openpyxl to fix, or
   rely on the < 20 MB fast path in `csv_adapter.open_source()`.
6. **Validate** — `python3 tools/validator.py config.xlsx source.xlsx --ddl schema.postgres.sql`.
   Must exit 0 with 0 errors.
7. **Test** — run executor with `--target sqlite --database test.db --trace 2`,
   verify row counts, spot-check values, then delete the test artifacts.

## Performance: openpyxl read_only mode

`csv_adapter.open_source()` opens xlsx files. Before 2026-09, it always used
`read_only=True`, which streams XML and makes `ws.cell(row, col)` O(n) per
call — fine for small sheets but O(n²) overall for the validator/executor's
cell-by-cell loop on wide tables (e.g. 976 rows × 64 cols hangs for hours).

**Fix**: files < 20 MB now open in normal mode (`read_only=False`), which loads
everything into memory and gives O(1) cell access. Files > 20 MB still use
`read_only=True` to avoid memory pressure. The 20 MB threshold is well above
any real workbook and well below Drive's 40 MB cap.

Drive files are unaffected: they are always downloaded to a local `.xlsx`
first (`sources.resolve()` → `drive.download()` → `cache/`), so
`open_source()` sees a local file and the size check works normally.
