# Excel Parser - config-driven excel -> database loading

Two workbooks in, a database out:

```
configuration excel  ┐
                     ├─►  validator.py  ──►  is this loadable?  +  schema.sql
 source excel        ┘                        (errors / warnings, nothing written)
        │
        └───────────────────►  executor.py  ──►  SQLite  or  PostgreSQL
                                            (target_config says which; .env has
                                             the credentials, nothing else does)
```

Two stages, deliberately separated:

* **`validator.py` decides.** It checks the configuration workbook and, if you
  give it a source workbook, dry-runs the whole load: missing tabs, wrong
  `col:` references, bad `data_type`s, unusable names, cells that will not
  convert, rows that will be skipped, tables that would load 0 rows. It writes
  the `CREATE TABLE` statements only when there are no errors.
* **`executor.py` dumps.** No judgement, no interpretation: read the configured
  cells, cast, insert with lineage. It re-runs the validator first and refuses
  to write anything if there are errors (`--no-validate` to skip).

Both are importable: `validate()` returns `Issue(severity, where, message)`
records and prints nothing, `execute()` returns a `LoadResult` and takes a
`log=` callable - so an application can drive them and render the results
itself.

* **The configuration says where it goes too.** A `target_config` sheet pins the
  target (`sqlite`/`postgres`), the database, the PostgreSQL schema and the
  table prefix to the configuration; `--target` / `--database` / `--prefix`
  override it. Host, user and password stay in `.env` - never in the workbook.

* **Keys are your choice.** `id_type` in `target_config` (or `--id-type`, or the
  Keys selector in the app) makes every primary key and `file_id` either a
  database counter (`integer`, the default) or a UUID generated per row
  (`uuid`) - no database extension needed.

* **One active row of `sheet_config` = one flat table.** Blocks are read exactly
  as they sit in the sheet - nothing is merged, joined or derived.
* **Every row carries its origin**: `file_id`, `sheet_name`, `source_row_num`,
  unique together, so any value traces back to one worksheet cell.
* **No sheet, row or column knowledge in the code.** Adding a table or a column
  means adding a row to the configuration workbook and regenerating.

## What is in the box

```
examples/01_simple/            one sheet, one table
examples/02_features/          key/value blocks, two blocks per sheet, fences, active = N
examples/03_uuid_keys/         id_type = uuid instead of counter keys
examples/04_postgres_schema/   PostgreSQL database + db_schema + table_prefix
examples/05_data_types/        every data type and the messy cells it survives
examples/06_references/        foreign-key references between tables (orders + items)
examples/07_validation_errors/ a wrong configuration and what the validator says
examples/08_source_mismatch/   a right configuration against the wrong workbook
examples/09_swiggy_annexure/   the real Swiggy annexure: 13 tables, 217 rows
examples/10_zomato_settlement/ the real Zomato settlement report
examples/11_growthfalcons/     the real GrowthFalcons settlement report: 5 tables, 109 rows
tools/make_examples.py         regenerates examples 03-05, 07-08

template/config_template.xlsx  start here: the three sheets with every header explained
tools/make_template.py         regenerates that template; --annotate puts the same
                               header comments and help_* sheets on any config workbook

docs/EXAMPLES.md      the example reference: a scenario -> example table, then all
                      eleven examples explained with the output of each run
docs/CONFIG_RULES.md  how to write the configuration workbook: every column, every rule
docs/RUNNING.md       step-by-step run guide, PostgreSQL notes, common errors
docs/APP_RUNNING.md   the web application: install, login, run, use
docs/APP_PLAN.md      how the application is put together

app/backend/          FastAPI: main.py (endpoints), auth.py, state.py (PostgreSQL),
                      service.py, batch.py, sources.py, drive.py, users.py
app/frontend/         Angular 22 + Optimus UI
app/run.sh            starts both

util/seed.sh               create the default user (admin/password)
util/clear_all.sh          wipe app state (PG schema) + cache, then re-seed

tools/validator.py         stage 1: is it loadable? + the DDL (--ddl, --dialect)
tools/executor.py          stage 2: push the rows (target from the workbook, --trace N)
tools/values.py            cell -> database value casting, shared by both stages
tools/db.py                the two database targets + the .env reader
tools/show_tables.py       dump every table of a loaded database (either target)
tools/run_queries.py       run a .sql file of SELECTs (either target)
queries/swiggy_checks.sql  the checks used on example 9 / Swiggy (lineage, reconciliation)
tools/bootstrap_config.py  drafted the Swiggy config workbook (block list hardcoded in it)

.env.example               PostgreSQL settings to copy to .env and fill in

Dockerfile                 single image: backend + built frontend, PG is external
docker-compose.yml         dev stack: app + PostgreSQL

AGENTS.md                  project context for an AI coding agent: the design rule,
                           the layout, the commands, the checks, the security limits
.agents/skills/run-app/    skill: start the application and click through it
.agents/skills/check-parser/  skill: run every check and all eleven examples
```

Each example folder contains only the two workbooks; the schema and the database
are produced by running the commands. Every example configuration carries the
same hover note on every header and the same `help_*` sheets as the template.

## Read in this order

1. `docs/EXAMPLES.md` example 1 - one sheet, one table, 3 rows: the whole idea.
2. `docs/EXAMPLES.md` example 2 - every feature: `key_value` blocks, two tables
   from one sheet, `data_end_row` fences, currency/percent cleaning, rejected
   rows, `active = N`.
3. `docs/EXAMPLES.md` example 9 - the real Swiggy annexure: 13 tables, 217 rows,
   reconciled against the file's own Summary sheet.
4. `docs/EXAMPLES.md` scenario table at the top - it names the example that
   shows each feature (UUID keys, PostgreSQL schemas, data types, references,
   the two deliberately failing examples, and the real-world examples 09-11).
5. `docs/CONFIG_RULES.md` before you write your own configuration.
6. `docs/RUNNING.md` when you run it.

## Quick start

### With Docker (application)

```bash
docker compose up                              # app on :8000, PG on :5432
./util/seed.sh                                 # create default user (admin/password)
```

Open <http://localhost:8000> and sign in. See `docs/APP_RUNNING.md` for details.

### Command-line tools

```bash
python3 -m pip install openpyxl                # add "psycopg[binary]" for PostgreSQL

cd examples/01_simple
python3 ../../tools/validator.py sales_config.xlsx sales_source.xlsx --ddl schema.postgres.sql
python3 ../../tools/executor.py sales_config.xlsx sales_source.xlsx --env ../../.env --trace 3
python3 ../../tools/show_tables.py --config sales_config.xlsx --env ../../.env
```

Target, database, schema and prefix come from the workbook's `target_config`
sheet (`postgres` / `excel_parser` here), so the commands do not repeat them.
Credentials come from `.env` (copy `.env.example` to `.env` and fill it in)
```

The loader creates the tables on first run, then appends each later file under a
new `file_id`. Credentials come only from the environment / `.env` (never from
the code or the configuration workbook), and every value is sent as a query
parameter.

## Status

Both targets are implemented and were run against the Swiggy annexure: 217 rows,
identical results on SQLite and on PostgreSQL 16. The validator's dry run
predicts exactly what the executor then reports (same skipped rows, same
unconvertible cell).

On top of that sits the application in `app/`: log in, save a configuration
(source + configuration workbook, each a file path browsed from `WORKBOOK_DIR`,
a direct Google Sheets link, or a file picked from Google Drive - each with a
test-access button that verifies the file is reachable), see the schema as a
draggable ER diagram (block tables, `file_id` -> `source_file` lineage edges,
FK relationship edges from `references` columns) and a 20-row preview where
every value points at its source cell, review validation issues and data quality
(type mismatches, skipped rows), then push - either **Schema only** (DDL without
data) or **Schema + Data** (full load). The push dialog shows stat boxes and the
target before you confirm. Application state (users, sessions, projects, runs,
batches) lives in PostgreSQL under `APP_SCHEMA`, separate from loaded data.

The application also provides **batch mode**: select one configuration workbook
and multiple source files, validate all at once, then push - each file gets its
own `file_id`. A collapsible **side navigation** gives access to My work, Batch
run, a dark/light theme toggle, user info, and a **Settings** page (poll
interval, Drive connection status, app version). A **sync status indicator** in
the toolbar shows whether the workbook is up to date, has changed, or has a
connection error. Drive file selection uses **Google's native Picker UI**.

**Strict mode** is the default: type mismatches and skipped rows block the push
(no silent NULLs or dropped rows), and any failure triggers a rollback.
`source_file` carries only generic file metadata (`file_name`, `file_sha256`,
`row_count`, `loaded_at`) - no domain-specific columns.

It calls `validate()` / `render_ddl()` / `execute()` directly, so the browser
and a command-line run cannot disagree.
See `docs/APP_RUNNING.md`.
