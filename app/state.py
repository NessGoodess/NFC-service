"""Shared mutable runtime state for the NFC service.
#es: Estado mutable compartido en runtime del servicio NFC.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.services.outbox import EventOutbox

if TYPE_CHECKING:
    from smartcard.CardMonitoring import CardMonitor

    from app.hardware.monitor import WebhookObserver

# Live connection/readiness snapshot exposed by GET /status.
#es: Instantánea de conexión/listo expuesta por GET /status.
reader_status: dict[str, Any] = {"connected": False, "ready": False, "readers": []}

# In-memory event queue → SQLite outbox → backend webhook.
#es: Cola de eventos en memoria → outbox SQLite → webhook del backend.
event_queue: asyncio.Queue = asyncio.Queue()
outbox = EventOutbox()
webhook_semaphore: asyncio.Semaphore | None = None
# Next credential write request waiting for a card tap.
#es: Siguiente escritura de credencial pendiente de un toque de tarjeta.
pending_assign: dict | None = None
card_monitor: CardMonitor | None = None
webhook_observer: WebhookObserver | None = None
