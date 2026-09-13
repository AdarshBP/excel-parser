#!/usr/bin/env bash
# Build and push both Docker images to Docker Hub.
#
#   ./util/docker-publish.sh                     # build + push :latest
#   ./util/docker-publish.sh v1.2.0              # build + push :v1.2.0
#   REGISTRY=myorg ./util/docker-publish.sh      # push to myorg/ instead
#
# Run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-latest}"
REGISTRY="${REGISTRY:-adarshbp}"
BACKEND="${REGISTRY}/excel-parser-backend:${TAG}"
FRONTEND="${REGISTRY}/excel-parser-frontend:${TAG}"

echo "=== Building backend: ${BACKEND} ==="
docker build -f app/backend/Dockerfile -t "${BACKEND}" .

echo ""
echo "=== Building frontend: ${FRONTEND} ==="
docker build -t "${FRONTEND}" app/frontend/

echo ""
echo "=== Pushing ==="
docker push "${BACKEND}"
docker push "${FRONTEND}"

echo ""
echo "Done. Deploy with:"
echo "  docker compose up -d"
