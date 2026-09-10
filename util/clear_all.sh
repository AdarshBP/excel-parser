#!/usr/bin/env bash
# Reset the application to a clean initial state, then re-seed.
#
#   ./util/clear_all.sh          # wipe everything, create default user
#
# What is removed:
#   app schema in PG     users, sessions, projects, runs (DROP SCHEMA ... CASCADE)
#   target schemas in PG loaded data tables (every non-system schema except public)
#   public tables in PG  any loaded data tables in the public schema
#   app/data/            pushed SQLite databases
#   app/cache/           downloaded workbooks (Sheets / Drive)
#   app/snapshots/       workbook copies kept per run
#
# What is NOT removed:
#   .env               your credentials stay
#   examples/          the example workbooks and any generated .db / .sql
#   tools/             parser code
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Clearing application state..."

# Drop ALL non-system schemas in PostgreSQL (app schema + any target schemas)
cd app/backend
python3 -c "
import os, psycopg
from pathlib import Path

# Load .env so PG credentials are available
env_path = Path(__file__).resolve().parent.parent.parent / '.env' if False else Path('../../.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip().strip('\"').strip(\"'\")
        if k and k not in os.environ: os.environ[k] = v

url = os.environ.get('DATABASE_URL')
if url:
    con = psycopg.connect(url)
else:
    con = psycopg.connect(
        host=os.environ.get('PGHOST', 'localhost'),
        port=os.environ.get('PGPORT', '5432'),
        dbname=os.environ.get('PGDATABASE', 'excel_parser'),
        user=os.environ.get('PGUSER', ''),
        password=os.environ.get('PGPASSWORD', ''),
    )

# Find all non-system schemas
rows = con.execute(
    \"SELECT schema_name FROM information_schema.schemata \"
    \"WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')\"
).fetchall()
schemas = [r[0] for r in rows]

for s in schemas:
    if s == 'public':
        # Don't drop public itself, but drop all its tables
        tables = con.execute(
            \"SELECT table_name FROM information_schema.tables \"
            \"WHERE table_schema = 'public' AND table_type = 'BASE TABLE'\"
        ).fetchall()
        for t in tables:
            con.execute(f'DROP TABLE IF EXISTS public.\"{t[0]}\" CASCADE')
        if tables:
            print(f'  dropped {len(tables)} table(s) from public schema')
    else:
        con.execute(f'DROP SCHEMA IF EXISTS \"{s}\" CASCADE')
        print(f'  dropped schema: {s}')

con.commit()
con.close()
if not [s for s in schemas if s != 'public']:
    print('  no custom schemas to drop')
"
cd ../..

# Clean local runtime directories
rm -rf app/data
rm -rf app/cache
rm -rf app/snapshots

echo "  removed data/, cache/, snapshots/"

# Re-create the schema and seed the default user
./util/seed.sh

echo "Application reset complete."
