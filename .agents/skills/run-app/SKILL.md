---
name: run-app
description: Start the Excel Parser web application (FastAPI backend on :8000, Angular frontend on :4200) and sign in. Use when asked to run, start, serve, open or click around the app.
---

# Start the Excel Parser application

Run from the project root.

1. Install once, if `app/frontend/node_modules` or the backend packages are missing:

   ```bash
   pip install -r app/backend/requirements.txt
   (cd app/frontend && npm ci)
   ```

   Angular 22 needs Node 22 / npm 11. If `node -v` reports anything older, put a
   Node 22 toolchain first on `PATH` before `npm ci` and before any `npm` command —
   the build fails silently late otherwise.

2. Make sure a login exists (accounts are CLI-only, there is no sign-up):

   ```bash
   cd app/backend && python3 users.py list
   python3 users.py add <name>          # asks for a password twice, min 12 chars
   ```

3. Start both processes in the foreground of their own shell so their logs are
   readable:

   ```bash
   cd app && ./run.sh                   # ./run.sh backend | ./run.sh frontend for one
   ```

4. Wait for the Angular dev server to report it is listening, then open
   <http://localhost:4200> and sign in. `ng serve` proxies `/api` to the backend,
   so never open :8000 in the browser.

5. To exercise it: **New configuration** → File path
   `examples/01_simple/sales_source.xlsx` and `examples/01_simple/sales_config.xlsx`
   → Render (expect one table, 3 rows) → View DDL → Push (expect 3 rows inserted,
   no password shown anywhere). The Swiggy example
   (`examples/09_swiggy_annexure/`) renders 14 blocks / 222 rows with
   `order_level` 122.

Notes:

* `app/state.db` (users, sessions, saved configurations, history), `app/data/`
  (pushed SQLite databases) and `app/cache/` (downloaded workbooks) are runtime
  state — never commit or archive them, and never delete them without asking.
* The Google Drive option reports "not configured" until `GOOGLE_CLIENT_ID` and
  `GOOGLE_CLIENT_SECRET` are in `.env`; file paths and direct links work without
  them. Do not claim the OAuth flow works unless real credentials were used.
