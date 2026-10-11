#!/usr/bin/env bash
# Run on a machine WITH PyPI/npm access, then copy vendor/ + data/raw/ to the offline machine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WHEELHOUSE="$ROOT/vendor/wheelhouse"

mkdir -p "$WHEELHOUSE"

echo "==> Downloading Python wheels into vendor/wheelhouse"
python3 -m pip download -r "$ROOT/api/requirements.txt" -d "$WHEELHOUSE"
python3 -m pip download -e "$ROOT/ingest[dev]" -d "$WHEELHOUSE" 2>/dev/null || \
  python3 -m pip download "$ROOT/ingest" -d "$WHEELHOUSE"

echo "==> Clone Google Fonts (optional, several GB)"
if [[ ! -d "$ROOT/data/raw/google-fonts/ofl" ]]; then
  git clone --depth 1 https://github.com/google/fonts "$ROOT/data/raw/google-fonts"
fi

echo "==> npm install for web (optional)"
if command -v npm >/dev/null && [[ -f "$ROOT/web/package.json" ]]; then
  (cd "$ROOT/web" && npm install && npm pack --dry-run 2>/dev/null || true)
fi

echo "Done. Copy the whole repo (including vendor/wheelhouse and data/raw) to the offline machine, then:"
echo "  make install-offline"
