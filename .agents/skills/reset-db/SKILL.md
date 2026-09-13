---
name: reset-db
description: Reset the Excel Parser database — drop the app schema, clear cache, and re-seed the default user. Use when asked to reset db, clear db, wipe db, or start fresh.
---

# Reset the database

Run from the project root:

```bash
./util/clear_all.sh
```

This does three things:

1. **Drops all PostgreSQL schemas** — the app schema (`excelparser_config`)
   plus every target schema where loaded data lives. Tables in `public` are
   also dropped (but the `public` schema itself is kept).
2. **Deletes runtime directories** — `app/data/` (pushed SQLite databases),
   `app/cache/` (downloaded/uploaded workbooks), `app/snapshots/`.
3. **Re-seeds** — recreates the app schema and the default user (`admin` /
   `password`).

If the backend is running it will reconnect automatically on the next
request. No restart needed.

Expected output:

```
Clearing application state...
  dropped PostgreSQL schema: excelparser_config
  removed data/, cache/, snapshots/
Seeding user 'admin'...
created user: admin
password: password
Done. Login at http://localhost:4200
Application reset complete.
```
