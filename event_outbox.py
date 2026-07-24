"""SQLite outbox for durable NFC webhook delivery (Phase 2)."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from config import BASE_DIR

DEFAULT_DB_PATH = Path(os.getenv("NFC_OUTBOX_DB", str(BASE_DIR / "nfc_outbox.db")))

# EventOutbox is a class that manages the outbox for durable NFC webhook delivery.
# Español: EventOutbox es una clase que gestiona el outbox para la entrega durable de webhooks NFC.
class EventOutbox:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_event_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    sent_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, id)"
            )
            conn.commit()

    def enqueue(self, payload: dict[str, Any], client_event_id: str | None = None) -> str:
        event_id = client_event_id or str(uuid.uuid4())
        body = dict(payload)
        body["client_event_id"] = event_id

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outbox (client_event_id, payload_json, status)
                VALUES (?, ?, 'pending')
                """,
                (event_id, json.dumps(body, ensure_ascii=False)),
            )
            conn.commit()
        return event_id

    def fetch_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, client_event_id, payload_json, attempts
                FROM outbox
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "client_event_id": row["client_event_id"],
                "payload": json.loads(row["payload_json"]),
                "attempts": row["attempts"],
            }
            for row in rows
        ]

    def mark_sent(self, row_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET status = 'sent', sent_at = datetime('now')
                WHERE id = ?
                """,
                (row_id,),
            )
            conn.commit()

    def mark_failed_attempt(self, row_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                (error[:500], row_id),
            )
            conn.commit()

    def pending_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM outbox WHERE status = 'pending'"
            ).fetchone()
            return int(row["c"] if row else 0)

    def prune_sent(self, retention_days: int = 7) -> int:
        """Remove acknowledged events after a short diagnostic retention period."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM outbox
                WHERE status = 'sent'
                  AND sent_at < datetime('now', ?)
                """,
                (f"-{retention_days} days",),
            )
            conn.commit()
            return cursor.rowcount
