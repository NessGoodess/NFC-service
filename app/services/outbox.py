"""SQLite outbox for durable NFC webhook delivery.
#es: Outbox SQLite para entrega durable de webhooks NFC.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR

DEFAULT_DB_PATH = Path(os.getenv("NFC_OUTBOX_DB", str(DATA_DIR / "nfc_outbox.db")))


class EventOutbox:
    """Persist events before webhook delivery so restarts do not drop them.
    #es: Persiste eventos antes del webhook para que un reinicio no los pierda.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with WAL-friendly pragmas.
        #es: Abre una conexión SQLite con pragmas aptos para WAL.
        """
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        """Create outbox table and status index if missing.
        #es: Crea la tabla outbox y el índice de estado si no existen.
        """
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
        """Insert a pending event and return its client_event_id.
        #es: Inserta un evento pendiente y devuelve su client_event_id.
        """
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
        """Fetch oldest pending rows for delivery.
        #es: Obtiene las filas pendientes más antiguas para entregarlas.
        """
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
        """Mark a row as successfully delivered.
        #es: Marca una fila como entregada correctamente.
        """
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
        """Increment attempts and store the last delivery error.
        #es: Incrementa intentos y guarda el último error de entrega.
        """
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
        """Count pending outbox rows.
        #es: Cuenta filas pendientes del outbox.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM outbox WHERE status = 'pending'"
            ).fetchone()
            return int(row["c"] if row else 0)

    def prune_sent(self, retention_days: int = 7) -> int:
        """Delete acknowledged events older than the retention window.
        #es: Elimina eventos confirmados más antiguos que la ventana de retención.
        """
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
