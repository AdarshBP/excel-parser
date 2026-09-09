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
`file_id → source_file.file_id`; there are no foreign keys between blocks.

## Layout

```
tools/validator.py   stage 1 — decides: is this loadable? writes the DDL. Never writes to a DB.
tools/executor.py    stage 2 — dumps: read configured cells, cast, insert with lineage.
tools/values.py      cell -> database value casting, shared by both stages
tools/rows.py        row reading, shared by executor and preview
tools/preview.py     the model + cast-row previews the app renders
tools/db.py          the two database targets and the .env reader
tools/make_template.py, tools/make_examples.py   regenerate template/ and examples 03-05, 07-08

app/backend/         FastAPI: main.py (endpoints), auth.py, state.py (PostgreSQL),
                     service.py, batch.py, sources.py (local path / direct link / Drive),
                     drive.py (Google OAuth + Drive), users.py (accounts CLI)
app/frontend/        Angular 22 + Optimus UI (@openng/optimus-ui)
app/run.sh           starts backend :8000 and frontend :4200

util/seed.sh         create the default user (admin/password)
util/clear_all.sh    wipe app state (PG schema) + cache, then re-seed

examples/01..11      each folder holds only the two workbooks
template/            config_template.xlsx — every header explained
docs/                EXAMPLES.md, CONFIG_RULES.md, RUNNING.md, APP_RUNNING.md, APP_PLAN.md
Dockerfile           single image: backend + built frontend, PG is external
docker-compose.yml   dev stack: app + PostgreSQL
```

## Setup

```bash
pip install -r app/backend/requirements.txt        # backend
(cd app/frontend && npm ci)                        # needs Node 22+
```

Or with Docker:

```bash
docker compose up                                  # app on :8000, PG on :5432
```

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
(cd app/backend && python3 -m pytest -q)           # test_drive.py
(cd app/frontend && npm run build)                 # Node 22+ required
```

Expected row counts, useful as a regression check: example 01 = 3 rows,
02 = 12, 03 = 4 UUID rows, 05 = 4, 06 = 9 (3 orders + 6 items),
09 (Swiggy) = 217 with `order_level` 122, 11 (GrowthFalcons) = 109.
Examples 07 and 08 must fail validation and exit 1 with nothing written.

## Application features

* **Design mode** (`/project/:id`): configure source + config workbook, render
  the schema as an ER diagram (with drag, zoom, FK edges), preview data rows,
  see validation + data quality issues, push schema only or schema + data.
* **Batch mode** (`/batch`): select one config + multiple source files (via
  file path, Google Sheets link, or Google Drive), validate all at once — push
  only proceeds when every file passes. Each file gets its own `file_id`.
* **Side navigation**: collapsible sidebar with My work, Batch run, theme
  toggle, user info, and a Settings link (gear icon) in the footer.
* **Settings page** (`/settings`): poll interval (5s/10s/15s/30s/60s, default
  10s), Google Drive connection status + disconnect, about section with app
  version + backend version. Persisted in localStorage.
* **Sync status indicator**: toolbar shows green dot + "Synced [time]" when
  up to date, amber pulsing dot + "Changed — re-render" when the workbook
  changed, red pulsing dot + "Sync failed" on connection/Drive error.
* **Tooltips**: all buttons across the app have tooltips with consistent
  positioning.
* **Strict mode**: type mismatches and skipped rows block the push (no silent
  NULLs or dropped rows). Rollback on any failure.
* **`null_default`**: optional column in `column_config` — what to store when
  a cell is empty (e.g. `0` for numeric, `N/A` for text).
* **`references`**: optional column in `column_config` — declares an FK
  relationship shown as a dashed line in the ER diagram.
* **Dark/light theme**: toggle in the sidebar, persisted in localStorage.
* **Google Picker API**: Drive file selection uses Google's native Picker UI
  instead of a custom file list dialog. Requires `GOOGLE_API_KEY` in `.env`.
  Backend endpoint `GET /api/drive/picker` returns the API key + access token.
* **Backend health**: `GET /api/health` returns `{status, version}`.
* **Drive caching**: downloads always fresh; metadata cached 30s for poll
  fingerprinting; Drive status cached 10s across components; file names
  cached permanently per session. Auto-test debounced to 800ms.

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
* Local paths as a source are restricted to the project directory or
  `WORKBOOK_DIR`, and are a development convenience only.
* Client-facing errors must not carry stack traces or internal paths.
* Global exception handlers catch DB errors (503) and unhandled errors (500)
  with safe messages; details are logged server-side only.

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
