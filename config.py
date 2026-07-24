"""Load Raspberry Pi / NFC reader configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
READERS_CONFIG_PATH = Path(os.getenv("NFC_READERS_CONFIG", BASE_DIR / "readers.json"))


def load_readers_config() -> dict[str, Any]:
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
    cfg = load_readers_config()
    return int(os.getenv("NFC_WEBHOOK_CONCURRENCY", cfg.get("webhook_concurrency", 3)))


def get_reader_poll_interval() -> int:
    cfg = load_readers_config()
    return int(os.getenv("NFC_READER_POLL_INTERVAL", cfg.get("reader_poll_interval_seconds", 8)))
