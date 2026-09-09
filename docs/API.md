# API Reference

Base URL: `http://localhost:8000`

All endpoints except `/api/health`, `/api/auth/login`, `/api/template`, and
`/api/auth/callback/google` require a session cookie (`session`). Mutating
requests (POST/PATCH/DELETE) also require the `X-CSRF-Token` header matching
the cookie value.

Errors return `{"detail": "..."}` with the appropriate HTTP status code.
Database errors → 503, validation errors → 400, not found → 404.

---

## Health & Utilities

### `GET /api/health`

Server health check. No authentication required.

**Response** `200`
```json
{ "status": "ok", "version": "1.0.0" }
```

---

### `GET /api/template`

Download the configuration template workbook. No authentication required.

**Response** `200` — file download (`config_template.xlsx`)

---

## Authentication

### `POST /api/auth/login`

Create a session. No authentication required.

**Body**
```json
{ "username": "admin", "password": "password" }
```

**Response** `200` — sets `session` cookie
```json
{ "username": "admin", "must_change_password": false }
```

---

### `POST /api/auth/logout`

End the session.

**Response** `200`
```json
{ "status": "logged out" }
```

---

### `GET /api/auth/me`

Current user info.

**Response** `200`
```json
{ "username": "admin", "must_change_password": false }
```

---

### `POST /api/auth/password`

Change the current user's password. Requires CSRF.

**Body**
```json
{ "current": "old-password", "new": "new-password-min-8-chars" }
```

**Response** `200`
```json
{ "status": "password changed" }
```

---

## Projects

A project pairs one config workbook with one source workbook.

### `GET /api/projects`

List all projects for the current user, newest first.

| Query param | Default | Description |
|---|---|---|
| `limit` | 100 | Max results (1–200) |

**Response** `200` — array of project objects
```json
[
  {
    "project_id": "abc123",
    "name": "My Project",
    "source_ref": "examples/01_simple/sales_source.xlsx",
    "config_ref": "examples/01_simple/sales_config.xlsx",
    "source_kind": "local",
    "config_kind": "local",
    "target": {},
    "auto_render": false,
    "created_at": "...",
    "updated_at": "...",
    "last_render_at": null,
    "last_push_at": null
  }
]
```

---

### `POST /api/projects`

Create a new project. Both references are resolved (downloaded if remote) to
verify they are accessible. Requires CSRF.

**Body**
```json
{
  "name": "My Project",
  "source_ref": "examples/01_simple/sales_source.xlsx",
  "config_ref": "examples/01_simple/sales_config.xlsx",
  "target": {
    "target": "postgres",
    "database": "excel_parser",
    "prefix": "stg_",
    "id_type": "integer"
  },
  "auto_render": false
}
```

`source_ref` / `config_ref` accept:
- Local path (relative to project root or inside `WORKBOOK_DIR`)
- Google Sheets URL (`https://docs.google.com/spreadsheets/d/...`)
- Drive reference (`drive:<file_id>`)

`target` is optional; fields within it override what the config workbook says.

**Response** `201` — the created project object

---

### `GET /api/projects/{project_id}`

Get one project with its last render result and fingerprints.

**Response** `200`
```json
{
  "project_id": "...",
  "name": "...",
  "render": { "tables": [...], "issues": [...], "previews": {...}, ... },
  "fingerprints": { "source": "sha256...", "config": "sha256..." },
  ...
}
```

---

### `PATCH /api/projects/{project_id}`

Update project fields. Only supplied fields are changed. Requires CSRF.

**Body** — all fields optional
```json
{
  "name": "Renamed",
  "source_ref": "new/path.xlsx",
  "config_ref": "new/config.xlsx",
  "target": { "prefix": "new_" },
  "auto_render": true
}
```

**Response** `200` — the updated project object

---

### `DELETE /api/projects/{project_id}`

Delete a project and all its runs. Requires CSRF.

**Response** `200`
```json
{ "status": "deleted" }
```

---

### `POST /api/projects/{project_id}/duplicate`

Clone a project (new ID, same refs and settings, name gets " (copy)" suffix).
Requires CSRF.

**Response** `201` — the new project object

---

## Render & Push

### `POST /api/projects/{project_id}/render`

Validate, build the schema model, and preview data rows. This is the main
"refresh" action the UI calls. Requires CSRF.

| Query param | Default | Description |
|---|---|---|
| `limit` | 20 | Max preview rows per table (1–200) |

**Response** `200`
```json
{
  "tables": [
    {
      "table_name": "sales",
      "full_name": "stg_sales",
      "columns": [
        { "name": "invoice_no", "type": "TEXT NOT NULL", "is_key": true }
      ]
    }
  ],
  "control_tables": [...],
  "issues": [
    { "severity": "warning", "where": "sheet_config[sales]", "message": "..." }
  ],
  "previews": {
    "sales": {
      "columns": ["invoice_no", "amount"],
      "rows": [{ "row_num": 2, "cells": [...] }],
      "loadable_rows": 3,
      "bad_cells": [],
      "skipped": []
    }
  },
  "target": { "target": "postgres", "host": "localhost", "database": "excel_parser", ... },
  "source": { "name": "sales_source.xlsx", "ref": "..." },
  "config": { "name": "sales_config.xlsx", "ref": "..." },
  "can_push": true,
  "rendered_at": "...",
  "preview_limit": 20
}
```

---

### `GET /api/projects/{project_id}/status`

Lightweight poll endpoint (called every 5–60s by the UI). Compares workbook
fingerprints against the last render to detect external edits.

**Response** `200`
```json
{
  "source_changed": false,
  "config_changed": false,
  "never_rendered": false,
  "source": { "name": "sales_source.xlsx", "sha256": "...", "size": 12345 },
  "config": { "name": "sales_config.xlsx", "sha256": "...", "size": 6789 },
  "last_render_at": "...",
  "last_push_at": null,
  "auto_render": false,
  "checked_at": "..."
}
```

---

### `GET /api/projects/{project_id}/target`

Where a push would write to (resolved from config + environment).

**Response** `200`
```json
{
  "target": "postgres",
  "host": "localhost",
  "database": "excel_parser",
  "db_schema": "staging",
  "prefix": "stg_",
  "id_type": "integer",
  "credentials": "from the server environment/.env"
}
```

---

### `GET /api/projects/{project_id}/ddl`

The generated SQL schema as plain text.

| Query param | Default | Description |
|---|---|---|
| `dialect` | from config | `sqlite` or `postgres` |

**Response** `200` — `text/plain` SQL

---

### `GET /api/projects/{project_id}/export-csv`

Export a rendered preview table as a CSV download.

| Query param | Required | Description |
|---|---|---|
| `table` | yes | Table name to export (e.g. `stg_sales`) |

**Response** `200` — CSV file download

---

### `POST /api/projects/{project_id}/push-schema`

Apply the DDL (CREATE TABLE) without inserting any data. Idempotent — skips
tables that already exist. Requires CSRF.

**Response** `200`
```json
{
  "target": { ... },
  "target_label": "postgres excel_parser",
  "created": true,
  "tables_existed": [],
  "tables_created": ["stg_sales", "stg_load_config_audit"],
  "message": "2 table(s) created in postgres excel_parser"
}
```

---

### `POST /api/projects/{project_id}/push`

Validate, create tables if needed, and insert all rows. Strict mode — any
type mismatch or skipped row blocks the push. Requires CSRF.

| Query param | Default | Description |
|---|---|---|
| `skip_audit` | false | Skip writing to `load_config_audit` |

**Response** `200`
```json
{
  "run_id": "...",
  "file_id": "uuid...",
  "row_total": 3,
  "rows_per_table": { "stg_sales": 3 },
  "skipped_rows": 0,
  "bad_cells": 0,
  "target_label": "postgres excel_parser",
  "target": { ... },
  "issues": [...],
  "log": ["..."],
  "source_name": "sales_source.xlsx",
  "config_name": "sales_config.xlsx"
}
```

---

## Runs

A run is a recorded push attempt (succeeded or failed).

### `GET /api/runs`

List runs for the current user.

| Query param | Default | Description |
|---|---|---|
| `project_id` | — | Filter by project (optional) |
| `limit` | 50 | Max results (1–200) |

**Response** `200` — array of run summaries
```json
[
  {
    "run_id": "...",
    "project_id": "...",
    "project_name": "My Project",
    "started_at": "...",
    "finished_at": "...",
    "status": "succeeded",
    "target": "postgres",
    "database": "excel_parser",
    "db_schema": "staging",
    "prefix": "stg_",
    "row_total": 3,
    "file_id": "uuid...",
    "source_name": "sales_source.xlsx",
    "config_name": "sales_config.xlsx"
  }
]
```

---

### `GET /api/runs/{run_id}`

Full details of one run, including per-table row counts and issues.

**Response** `200`
```json
{
  "run_id": "...",
  "status": "succeeded",
  "rows_per_table": { "stg_sales": 3 },
  "issues": [...],
  "log_text": "...",
  ...
}
```

---

## Batch

Process multiple source files against one config in a single operation.

### `POST /api/batch/validate`

Validate all source files. Each is checked independently. Requires CSRF.

**Body**
```json
{
  "config_ref": "path/to/config.xlsx",
  "source_refs": [
    "path/to/source1.xlsx",
    "drive:abc123",
    "https://docs.google.com/spreadsheets/d/..."
  ],
  "target": { "prefix": "stg_" }
}
```

**Response** `200`
```json
{
  "results": [
    {
      "ref": "path/to/source1.xlsx",
      "name": "source1.xlsx",
      "status": "valid",
      "message": "3 tables, 217 rows",
      "issues": [],
      "rows": 217,
      "tables": 3,
      "bad_cells": 0,
      "skipped": 0,
      "sha256": "..."
    }
  ],
  "all_valid": true,
  "total": 1,
  "valid": 1,
  "errors": 0
}
```

---

### `POST /api/batch/push`

Push all source files. Re-validates first — refuses if any file fails.
Stops on first push failure. Requires CSRF.

**Body** — same as `/api/batch/validate`

**Response** `200`
```json
{
  "batch_id": "...",
  "files": [
    {
      "ref": "...",
      "name": "source1.xlsx",
      "status": "pushed",
      "file_id": "uuid...",
      "rows": 217,
      "per_table": { "order_level": 122, "summary": 9 }
    }
  ],
  "total_rows": 217,
  "pushed": 1,
  "failed": 0,
  "total": 1,
  "target": { "target": "postgres", "database": "...", ... }
}
```

---

## Source References

### `POST /api/test-ref`

Test whether a workbook reference is accessible and valid. If `role=config`,
also checks that `sheet_config` and `column_config` sheets exist.

**Body**
```json
{ "ref": "path/to/file.xlsx", "role": "source" }
```

**Response** `200`
```json
{
  "ok": true,
  "name": "file.xlsx",
  "sheets": ["Sheet1", "Sheet2"],
  "size": 12345,
  "role": "source"
}
```

---

### `POST /api/auto-config`

Generate a configuration workbook from a CSV file's headers. CSV only.

**Body**
```json
{
  "ref": "path/to/data.csv",
  "table_name": "my_table",
  "database": "excel_parser",
  "db_schema": "staging"
}
```

**Response** `200`
```json
{ "ok": true, "config_ref": "cache/autoconfig_abc12345.xlsx", "name": "autoconfig_abc12345.xlsx" }
```

---

### `GET /api/local-workbooks`

List all `.xlsx` and `.csv` files inside the project directory.

**Response** `200`
```json
{
  "root": "/path/to/excel_parser",
  "files": ["examples/01_simple/sales_source.xlsx", ...]
}
```

---

### `GET /api/workbook-dir`

Browse files in the configured `WORKBOOK_DIR` (directory-based picker).

| Query param | Default | Description |
|---|---|---|
| `folder` | `""` | Relative subfolder to browse into |

**Response** `200`
```json
{
  "root": "/path/to/workbooks",
  "folder": "",
  "items": [
    { "name": "subfolder", "path": "subfolder", "kind": "folder", "size": null },
    { "name": "data.xlsx", "path": "/path/to/workbooks/data.xlsx", "kind": "file", "size": 12345 }
  ]
}
```

---

## Google Drive

Requires `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`. Without
them, `/api/drive/status` returns `configured: false` and Drive endpoints
return errors.

### `GET /api/drive/status`

Is Drive configured on the server, and is the current user connected?

**Response** `200`
```json
{
  "configured": true,
  "connected": true,
  "email": "user@gmail.com",
  "connected_at": "...",
  "redirect_uri": "http://localhost:8000/api/auth/callback/google"
}
```

---

### `POST /api/drive/connect`

Start the Google OAuth flow. Returns the consent URL. Requires CSRF.

**Response** `200`
```json
{ "url": "https://accounts.google.com/o/oauth2/v2/auth?..." }
```

---

### `GET /api/auth/callback/google`

OAuth callback — Google redirects the browser here after consent.
No session required (uses the single-use `state` token).

| Query param | Description |
|---|---|
| `state` | OAuth state token from `/connect` |
| `code` | Authorization code from Google |
| `error` | Error string if user denied access |

**Response** `302` — redirects to `{APP_FRONTEND_URL}/drive-connected?connected=1` (or `0` on failure)

---

### `POST /api/drive/disconnect`

Revoke the Google token and forget it. Requires CSRF.

**Response** `200`
```json
{ "status": "disconnected" }
```

---

### `GET /api/drive/picker`

Credentials for the Google Picker UI. Requires `GOOGLE_API_KEY` in `.env`.

**Response** `200`
```json
{
  "api_key": "AIza...",
  "access_token": "ya29...",
  "client_id": "123...apps.googleusercontent.com"
}
```

---

### `GET /api/drive/files`

Browse Google Drive for Sheets, `.xlsx` files, and folders.

| Query param | Default | Description |
|---|---|---|
| `search` | `""` | Search query (max 200 chars) |
| `folder` | `""` | Drive folder ID to browse into |
| `limit` | 50 | Max results (1–200) |

**Response** `200`
```json
{
  "files": [
    {
      "id": "abc123",
      "name": "My Sheet",
      "mimeType": "application/vnd.google-apps.spreadsheet",
      "modifiedTime": "...",
      "size": "12345",
      "webViewLink": "https://docs.google.com/...",
      "owners": [{ "emailAddress": "..." }]
    }
  ],
  "nextPageToken": null
}
```

---

### `GET /api/drive/files/{file_id}`

Metadata for one Drive file (so a saved `drive:<id>` reference can show a name).

**Response** `200`
```json
{
  "id": "abc123",
  "name": "My Sheet",
  "mime_type": "application/vnd.google-apps.spreadsheet",
  "modified_at": "...",
  "ref": "drive:abc123"
}
```

---

## Endpoint Summary

| Method | Path | Auth | CSRF | Description |
|---|---|---|---|---|
| `GET` | `/api/health` | no | no | Health check |
| `GET` | `/api/template` | no | no | Download config template |
| `POST` | `/api/auth/login` | no | no | Create session |
| `POST` | `/api/auth/logout` | yes | no | End session |
| `GET` | `/api/auth/me` | yes | no | Current user |
| `POST` | `/api/auth/password` | yes | yes | Change password |
| `GET` | `/api/projects` | yes | no | List projects |
| `POST` | `/api/projects` | yes | yes | Create project |
| `GET` | `/api/projects/{id}` | yes | no | Get project + last render |
| `PATCH` | `/api/projects/{id}` | yes | yes | Update project |
| `DELETE` | `/api/projects/{id}` | yes | yes | Delete project + runs |
| `POST` | `/api/projects/{id}/duplicate` | yes | yes | Clone project |
| `POST` | `/api/projects/{id}/render` | yes | yes | Validate + preview |
| `GET` | `/api/projects/{id}/status` | yes | no | Poll for changes |
| `GET` | `/api/projects/{id}/target` | yes | no | Where push writes to |
| `GET` | `/api/projects/{id}/ddl` | yes | no | Generated SQL |
| `GET` | `/api/projects/{id}/export-csv` | yes | no | Export table as CSV |
| `POST` | `/api/projects/{id}/push-schema` | yes | yes | Create tables only |
| `POST` | `/api/projects/{id}/push` | yes | yes | Validate + insert rows |
| `GET` | `/api/runs` | yes | no | List runs |
| `GET` | `/api/runs/{id}` | yes | no | Run details |
| `POST` | `/api/batch/validate` | yes | yes | Validate multiple files |
| `POST` | `/api/batch/push` | yes | yes | Push multiple files |
| `POST` | `/api/test-ref` | yes | no | Test workbook reference |
| `POST` | `/api/auto-config` | yes | no | Generate config from CSV |
| `GET` | `/api/local-workbooks` | yes | no | List local files |
| `GET` | `/api/workbook-dir` | yes | no | Browse WORKBOOK_DIR |
| `GET` | `/api/drive/status` | yes | no | Drive connection status |
| `POST` | `/api/drive/connect` | yes | yes | Start OAuth flow |
| `GET` | `/api/auth/callback/google` | no | no | OAuth callback |
| `POST` | `/api/drive/disconnect` | yes | yes | Revoke Drive token |
| `GET` | `/api/drive/picker` | yes | no | Picker credentials |
| `GET` | `/api/drive/files` | yes | no | Browse Drive files |
| `GET` | `/api/drive/files/{id}` | yes | no | Drive file metadata |

**Total: 32 endpoints**
