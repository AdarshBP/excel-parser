#!/usr/bin/env bash
# Switch the active .env file.
#
#   ./util/env-switch.sh local      # → .env.local   (./app/run.sh dev)
#   ./util/env-switch.sh docker     # → .env.docker  (local Docker)
#   ./util/env-switch.sh prod       # → .env.prod    (production)
#
set -euo pipefail
cd "$(dirname "$0")/.."

ENV="${1:-}"
if [ -z "$ENV" ]; then
  echo "Usage: $0 <local|docker|prod>"
  echo ""
  echo "Current .env:"
  head -1 .env 2>/dev/null || echo "  (no .env file)"
  exit 1
fi

SOURCE=".env.${ENV}"
if [ ! -f "$SOURCE" ]; then
  echo "Error: $SOURCE not found"
  echo "Available: $(ls .env.* 2>/dev/null | xargs -n1 basename | tr '\n' ' ')"
  exit 1
fi

cp "$SOURCE" .env
echo "Switched to $SOURCE → .env"
head -1 .env
