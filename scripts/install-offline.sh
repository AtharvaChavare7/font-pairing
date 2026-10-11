#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WHEELHOUSE="$ROOT/vendor/wheelhouse"

if [[ ! -d "$WHEELHOUSE" ]] || [[ -z "$(ls -A "$WHEELHOUSE" 2>/dev/null)" ]]; then
  echo "Missing vendor/wheelhouse. On a networked machine run: ./scripts/bootstrap-offline.sh"
  exit 1
fi

python3 -m venv "$ROOT/.venv-ingest"
"$ROOT/.venv-ingest/bin/pip" install --no-index --find-links="$WHEELHOUSE" "$ROOT/ingest[dev]"

python3 -m venv "$ROOT/.venv-api"
"$ROOT/.venv-api/bin/pip" install --no-index --find-links="$WHEELHOUSE" -r "$ROOT/api/requirements.txt"

if [[ -d "$ROOT/web/node_modules" ]]; then
  echo "web/node_modules present — Next.js dev server available via make web"
else
  echo "web/node_modules missing — use make web-static (no npm required)"
fi
