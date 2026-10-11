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
"$ROOT/.venv-api/bin/pip" install --no-index --find-links="$WHEELHOUSE" -r "$ROOT/api/requirements-dev.txt"

echo "Installed. Run: make ingest && make api   (UI at http://localhost:8000/ui)"
