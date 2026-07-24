#!/usr/bin/env bash
# Raspberry Pi 5 — NFC Reader service
# IMPORTANT: use a single worker. PC/SC hardware cannot be opened by multiple processes.
# Webhook concurrency (3) is handled inside the app via asyncio, not uvicorn workers.

set -euo pipefail
cd "$(dirname "$0")"

export NFC_WEBHOOK_CONCURRENCY="${NFC_WEBHOOK_CONCURRENCY:-3}"
export NFC_READER_POLL_INTERVAL="${NFC_READER_POLL_INTERVAL:-8}"

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

exec uvicorn main:app \
  --host 0.0.0.0 \
  --port "${NFC_SERVICE_PORT:-9000}" \
  --workers 1 \
  --loop asyncio \
  --log-level info
