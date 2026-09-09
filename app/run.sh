#!/usr/bin/env bash
# Start the Excel Parser application: FastAPI on :8000, Angular on :4200.
#
#   ./run.sh                 both, in the foreground (Ctrl-C stops both)
#   ./run.sh backend         only the API
#   ./run.sh frontend        only the UI
#
# First run:
#   pip install -r backend/requirements.txt
#   (cd frontend && npm ci)
#   python backend/users.py add <name>          # creates your login
#
# PostgreSQL credentials, if you push there, come from ../.env - never from a
# workbook and never from this script.
set -euo pipefail
cd "$(dirname "$0")"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-4200}"
export APP_ALLOWED_ORIGINS="${APP_ALLOWED_ORIGINS:-http://localhost:$UI_PORT}"

backend() {
  cd backend
  exec python3 -m uvicorn main:app --host 127.0.0.1 --port "$API_PORT"
}

frontend() {
  cd frontend
  exec npx ng serve --port "$UI_PORT"
}

case "${1:-both}" in
  backend)  backend ;;
  frontend) frontend ;;
  both)
    ( backend ) &
    api=$!
    trap 'kill $api 2>/dev/null || true' EXIT
    ( frontend )
    ;;
  *) echo "usage: $0 [both|backend|frontend]" >&2; exit 2 ;;
esac
