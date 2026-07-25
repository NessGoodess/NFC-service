#!/usr/bin/env bash
# NFC Reader service entrypoint (single uvicorn worker — PC/SC must stay single-process).
#es: Entrypoint del servicio NFC (un solo worker uvicorn — PC/SC debe ser un solo proceso).
# Webhook concurrency is handled inside the app via asyncio, not uvicorn workers.
#es: La concurrencia del webhook se maneja dentro de la app con asyncio, no con workers de uvicorn.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${APP_DIR}"

export NFC_WEBHOOK_CONCURRENCY="${NFC_WEBHOOK_CONCURRENCY:-3}"
export NFC_READER_POLL_INTERVAL="${NFC_READER_POLL_INTERVAL:-8}"

if [ -d "${APP_DIR}/.venv" ]; then
  # shellcheck source=/dev/null
  source "${APP_DIR}/.venv/bin/activate"
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${NFC_SERVICE_PORT:-9000}" \
  --workers 1 \
  --loop asyncio \
  --log-level info
