#!/usr/bin/env bash
# Seed the application database with a default user.
#
#   ./util/seed.sh                     # uses defaults below
#   SEED_USER=alice SEED_PASS=mysecretpass99 ./util/seed.sh
#
# Idempotent: skips creation if the user already exists.
set -euo pipefail
cd "$(dirname "$0")/.."

SEED_USER="${SEED_USER:-admin}"
SEED_PASS="${SEED_PASS:-password}"

echo "Seeding user '${SEED_USER}'..."

cd app/backend
python3 -c "
import state, auth

state.init()

con = state.connect()
row = con.execute('SELECT 1 FROM \"user\" WHERE username = %s',
                  ('${SEED_USER}'.strip().lower(),)).fetchone()
con.close()

if row:
    print('user ${SEED_USER} already exists - skipping')
else:
    auth.create_user('${SEED_USER}', '${SEED_PASS}')
    print('created user: ${SEED_USER}')
    print('password: ${SEED_PASS}')
"

echo "Done. Login at http://localhost:4200"
