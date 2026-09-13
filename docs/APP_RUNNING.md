# Running the Excel Parser application

The application is a thin shell around the parser in `tools/`: it never re-implements
parsing. The backend imports `validator.validate()`, `validator.render_ddl()`,
`preview.model()` / `preview.previews()` and `executor.execute()`, so what the browser
shows is what a push writes.

```
app/
  backend/    FastAPI  (http://127.0.0.1:8000)
  frontend/   Angular 22 + Optimus UI  (http://localhost:4200)
  data/       destination SQLite databases written by a push
  cache/      Google Sheets downloaded as .xlsx

Application state (users, sessions, projects, runs, batches) lives in PostgreSQL
under the APP_SCHEMA (default: excelparser_config), NOT in SQLite.
```

## 1. Install

### Local

```bash
pip install -r app/backend/requirements.txt
(cd app/frontend && npm ci)            # needs Node 22+
```

### Docker

```bash
docker compose up                      # app on :8000, PG on :5432
docker compose up -d db                # just PG (for local dev with ./run.sh)
```

## 2. Create your login

```bash
./util/seed.sh                         # creates admin / password
# or interactively:
cd app/backend && python3 users.py add yourname
```

Passwords are stored as Argon2id hashes in PostgreSQL. Minimum 8 characters.
Five failed attempts lock the account for five minutes.

## 3. Start it

### Local dev

```bash
cd app && ./run.sh                     # backend :8000 + frontend :4200
```

Open <http://localhost:4200> and sign in.

### Docker

```bash
docker compose up
```

Open <http://localhost:8000> (frontend is built and served by FastAPI).

### Seed after first start

```bash
./util/seed.sh                         # admin / password
./util/clear_all.sh                    # full reset: drops PG schema, re-seeds
```

## 4. Using it

### Design mode (`/project/:id`)

1. **New configuration** — name + source workbook + configuration workbook.
   Each field supports: **Browse** (local file upload from your computer),
   **Link** (Google Sheets URL), or **Drive** (Google Drive OAuth picker).
2. **Render** — reads both workbooks:
   * **ER diagram**: draggable table boxes, zoom, FK relationship edges,
     lineage edges to `source_file`. Click a table to preview its data.
   * **Blocks**: list view of all configured blocks.
   * **Data quality**: type mismatches and skipped rows shown as errors
     that block the push (strict mode).
   * **Validation**: config errors and warnings.
3. **Push** — two options:
   * **Schema only**: CREATE TABLE without inserting data.
   * **Schema + Data**: validates, creates tables, inserts all rows.
   Push is disabled when there are config errors or data quality issues.

### Batch mode (`/batch`)

1. Select one **configuration** workbook (upload, link, or Drive).
2. Add multiple **source files** — upload from your computer or pick from Drive.
3. **Validate all** — each file is checked independently. Duplicate files
   (same SHA-256 content) are rejected.
4. **Push all** — only available when every file passes validation.
   Each file gets its own `file_id`. Batch stops on first failure.
   Every batch push (including per-file uploads) is recorded and appears
   in Push history.

### Data Viewer (`/data-viewer`)

Browse all files that have been pushed to the database — from both project
pushes and batch pushes. Search by file name, project name, or database.
Click a file to see per-table breakdown with audit metadata
(`load_config_audit`). Enable via the toggle in Settings.

### Side navigation

Always-expanded sidebar:
* **Configurations** — saved configurations + push history
* **Batch run** — multi-file processing
* **Data Viewer** — browse pushed files (optional, enable in Settings)
* **Push history** — unified timeline of all pushes (project + batch)
* Theme toggle (dark/light), user avatar with sign out
* **Settings** (gear icon) — poll interval, Drive status, feature toggles

### Settings (`/settings`)

* **Poll interval** — 5s / 10s / 15s / 30s / 60s (default 10s)
* **Google Drive** — connection status + disconnect button
* **About** — app version + backend version (from `GET /api/health`)
* Settings are persisted in localStorage.

### Sync status indicator

The toolbar shows the current sync state:
* **Green dot + "Synced [time]"** — workbook is up to date
* **Amber pulsing dot + "Changed — re-render"** — workbook changed since last render
* **Red pulsing dot + "Sync failed"** — connection or Drive error

## 5. Destination and credentials

Where data goes comes from the configuration workbook's `target_config` sheet
(`target`, `database`, `db_schema`, `table_prefix`, `id_type`) — see
`docs/CONFIG_RULES.md`. The **Keys** selector overrides `id_type` per project.

PostgreSQL host, user and password come from `.env` / the environment only.
No credential is ever stored in a workbook or returned by the API.

Application state lives in PostgreSQL under `APP_SCHEMA` (default
`excelparser_config`), separate from loaded data which goes to the schema
chosen by the user's `target_config`.

## 6. Google Drive

1. Enable the Google Drive API **and the Google Picker API** in Google Cloud console.
2. Create OAuth Web application credentials.
3. Create an API key (for the Picker) and restrict it to the Picker API.
4. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_API_KEY` in `.env`.
5. Users click "Connect Google Drive" and sign in with their own Google account.
   The consent prompt only appears on first connect; a `BroadcastChannel`
   notifies the original tab when consent completes in the popup.
6. File selection opens **Google's native Picker UI** (replaces the earlier
   custom Drive file list dialog). The backend endpoint `GET /api/drive/picker`
   returns the API key and access token needed by the Picker.

Drive caching: downloads are always fresh (no stale cached files); metadata
is cached 30s for poll fingerprinting (reduces Google API calls); Drive
status is cached 10s across components; file names are cached permanently
per session. Auto-test is debounced to 800ms.

## 7. Docker deployment

```bash
docker build -t excel-parser .
docker run -p 8000:8000 --env-file .env excel-parser
```

The image builds the Angular frontend, bundles it with the FastAPI backend.
PostgreSQL must be reachable at `PGHOST`/`PGPORT`.

Environment variables:
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` — database
- `APP_SCHEMA` — app state schema (default: `excelparser_config`)
- `APP_ENV=production` — secure cookies
- `APP_ALLOWED_ORIGINS` — CORS origins
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — optional, for Drive
- `GOOGLE_API_KEY` — optional, for Google Picker UI (Drive file selection)
