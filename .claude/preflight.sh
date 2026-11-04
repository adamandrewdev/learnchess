#!/usr/bin/env bash
# Project checks. Everything runs in containers; nothing is installed on the host.
# Exit non-zero on the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== backend: ruff + pytest (api image)"
docker compose build -q api
docker compose run --rm --no-deps -T -v "$PWD/tests:/app/tests" api \
  sh -c 'ruff check . && ruff format --check backend core tests && python -m pytest -q tests'

echo "== frontend: eslint + build (node container, build output discarded)"
docker run --rm -v "$PWD/frontend:/app" -v learnchess_web_node_modules:/app/node_modules \
  -w /app node:22-alpine \
  sh -c 'npm install --no-fund --no-audit --silent && npx eslint --max-warnings 0 . \
         && npx vite build --outDir /tmp/dist --emptyOutDir --logLevel warn'

echo "== preflight OK"
