"""Local FastAPI HTTP endpoints for health and status.
#es: Endpoints HTTP locales de salud y estado.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import WEBHOOK_CONCURRENCY, WEBHOOK_URL
from app import state

router = APIRouter()


@router.get("/")
async def root():
    """Basic health payload with configured webhook URL.
    #es: Respuesta básica de salud con la URL de webhook configurada.
    """
    return {"msg": "FastAPI NFC webhook", "webhook": WEBHOOK_URL}


@router.get("/status")
async def status():
    """Reader presence, queue depth, and outbox backlog.
    #es: Presencia de lectores, profundidad de cola y backlog del outbox.
    """
    return {
        **state.reader_status,
        "webhook_concurrency": WEBHOOK_CONCURRENCY,
        "workers": 1,
        "queue_size": state.event_queue.qsize(),
        "outbox_pending": state.outbox.pending_count(),
    }
