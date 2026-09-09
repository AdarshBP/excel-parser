#!/usr/bin/env bash
# Reset the application to a clean initial state, then re-seed.
#
#   ./util/clear_all.sh          # wipe everything, create default user
#
# What is removed:
#   app schema in PG   users, sessions, projects, runs (DROP SCHEMA ... CASCADE)
#   app/data/          pushed SQLite databases
#   app/cache/         downloaded workbooks (Sheets / Drive)
#   app/snapshots/     workbook copies kept per run
#
# What is NOT removed:
#   .env               your credentials stay
#   examples/          the example workbooks and any generated .db / .sql
#   tools/             parser code
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Clearing application state..."

# Drop the app schema in PostgreSQL (tables: user, session, project, run, etc.)
cd app/backend
python3 -c "
import state
con = state.connect()
schema = state.APP_SCHEMA
con.execute(f'DROP SCHEMA IF EXISTS \"{schema}\" CASCADE')
con.commit()
con.close()
print(f'  dropped PostgreSQL schema: {schema}')
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
