#!/usr/bin/env bash
# `make walkthrough`: reprovisions Floci, runs every inbox inquiry in replay, captures every screen
# docs/product-walkthrough.md links (web/scripts/capture.mjs, the 1440x900 window each), converts the
# PNGs to WebP in docs/product-walkthrough-shots/ and runs the test that keeps the doc and shots in step.
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in cwebp lsof node uv; do
  command -v "$tool" > /dev/null || { echo "walkthrough: $tool is required" >&2; exit 1; }
done
if lsof -nP -iTCP:8765 -sTCP:LISTEN > /dev/null; then
  echo "walkthrough: port 8765 is in use; stop that console first" >&2
  exit 1
fi
work=$(mktemp -d)
shots=docs/product-walkthrough-shots
mkdir -p "$shots"
uv run python -m hcpagents.infra --reset
(cd web && npm ci --silent && npm run build --silent && npx playwright-core install --only-shell --no-remove chromium)

uv run uvicorn hcpagents.api:app --port 8765 > "$work/serve.log" 2>&1 &
server=$!
trap 'kill "$server" 2> /dev/null || true; wait "$server" 2> /dev/null || true' EXIT
for _ in $(seq 1 60); do curl -sf -o /dev/null -H "X-User: u-raman" localhost:8765/api/meta && break; sleep 1; done
for id in $(curl -sf -H "X-User: u-raman" localhost:8765/api/inquiries | uv run python -c "import json,sys; print(' '.join(i['id'] for i in json.load(sys.stdin)))"); do
  curl -sf -o /dev/null -H "X-User: u-raman" -X POST "localhost:8765/api/inquiries/$id/run"
done

node web/scripts/capture.mjs "$work/shots"
[ -n "${WALKTHROUGH_SCREENS:-}" ] || rm -f "$shots"/*.webp
for png in "$work"/shots/*.png; do
  cwebp -quiet -q 80 "$png" -o "$shots/$(basename "${png%.png}").webp"
done
echo "walkthrough: wrote $(ls "$work"/shots/*.png | wc -l | tr -d ' ') captures to $shots"
uv run pytest -q tests/test_walkthrough.py
