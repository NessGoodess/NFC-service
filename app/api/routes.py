"""Local FastAPI HTTP endpoints for health, status, and credential assignment.
#es: Endpoints HTTP locales de salud, estado y asignación de credencial.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.config import WEBHOOK_CONCURRENCY, WEBHOOK_URL
from app import state

router = APIRouter()


@router.post("/assign-nfc")
async def assign_nfc(request: Request):
    """Queue a credential write for the next tapped card.
    #es: Encola la escritura de una credencial en la próxima tarjeta detectada.
    """
    data = await request.json()
    credential_id = data.get("credential_id")

    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id is required")

    state.pending_assign = {"credential_id": credential_id, "action": "assign"}
    print(f"Pending assign task: credential_id={credential_id}")

    return {"success": True, "message": f"Waiting for card to assign credential {credential_id}"}


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
