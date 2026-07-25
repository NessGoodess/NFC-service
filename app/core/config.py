"""Load NFC reader service configuration from environment and JSON.
#es: Carga la configuración del servicio NFC desde variables de entorno y JSON.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Project root (NFC-Reader/), not the app/ package directory.
#es: Raíz del proyecto (NFC-Reader/), no el directorio del paquete app/.
BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

# Ensure runtime data directory exists (outbox DB, etc.).
#es: Asegura que exista el directorio de datos en runtime (DB outbox, etc.).
DATA_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(CONFIG_DIR / ".env")

READERS_CONFIG_PATH = Path(
    os.getenv("NFC_READERS_CONFIG", CONFIG_DIR / "readers.json")
)


def load_readers_config() -> dict[str, Any]:
    """Return readers.json contents, or safe defaults if the file is missing.
    #es: Devuelve el contenido de readers.json, o valores seguros si no existe.
    """
    if not READERS_CONFIG_PATH.exists():
        return {
            "global_armed": True,
            "webhook_concurrency": 3,
            "reader_poll_interval_seconds": 8,
            "slots": [],
        }

    with open(READERS_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_webhook_concurrency() -> int:
    """Max concurrent webhook POSTs (env overrides JSON).
    #es: Máximo de POST concurrentes al webhook (env tiene prioridad sobre JSON).
    """
    cfg = load_readers_config()
    return int(os.getenv("NFC_WEBHOOK_CONCURRENCY", cfg.get("webhook_concurrency", 3)))


def get_reader_poll_interval() -> int:
    """Seconds between PC/SC presence polls (env overrides JSON).
    #es: Segundos entre sondeos de presencia PC/SC (env tiene prioridad sobre JSON).
    """
    cfg = load_readers_config()
    return int(os.getenv("NFC_READER_POLL_INTERVAL", cfg.get("reader_poll_interval_seconds", 8)))


TOKEN = os.getenv("NFC_SERVICE_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

WEBHOOK_BASE = (os.getenv("NFC_WEBHOOK_URL") or "").strip().strip('"').rstrip("/")
# Backend read-event endpoint built from the configured API base URL.
#es: Endpoint de eventos construido a partir de la URL base del API.
WEBHOOK_URL = f"{WEBHOOK_BASE}/reader/read-event" if WEBHOOK_BASE else ""
READER_POLL_INTERVAL = get_reader_poll_interval()
WEBHOOK_CONCURRENCY = get_webhook_concurrency()
