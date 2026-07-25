"""FastAPI application entrypoint for the NFC reader service.
#es: Punto de entrada FastAPI del servicio lector NFC.
"""

from __future__ import annotations

import asyncio

import httpx
import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import HEADERS, WEBHOOK_CONCURRENCY, WEBHOOK_URL
from app.hardware.monitor import start_card_monitor
from app.hardware.pcsc import reader_names
from app.services.slots import slot_registry
from app.services.status import reader_status_poller
from app.workers.flusher import outbox_flusher
from app.workers.sender import sender
from app import state

app = FastAPI()
app.include_router(router)


@app.on_event("startup")
async def startup():
    """Initialize concurrency, hardware monitor, and background workers.
    #es: Inicializa concurrencia, monitor de hardware y workers en segundo plano.
    """
    state.webhook_semaphore = asyncio.Semaphore(WEBHOOK_CONCURRENCY)
    slot_registry.reload()
    pruned = state.outbox.prune_sent(retention_days=7)
    if pruned:
        print(f"[OK] Outbox: removed {pruned} old acknowledged events")

    loop = asyncio.get_running_loop()
    try:
        available = reader_names()
        if not available:
            state.reader_status["connected"] = False
            state.reader_status["ready"] = False
            state.reader_status["readers"] = []
        else:
            start_card_monitor(loop)
    except Exception:
        state.reader_status["connected"] = False
        state.reader_status["ready"] = False
        state.reader_status["readers"] = []

    asyncio.create_task(sender())
    asyncio.create_task(outbox_flusher())
    asyncio.create_task(reader_status_poller())

    # Push initial reader status so consumers can sync UI/state.
    #es: Envía el estado inicial del lector para que los consumidores sincronicen UI/estado.
    if WEBHOOK_URL:
        initial_payload = {
            "event": "reader_status_changed",
            "connected": state.reader_status["connected"],
            "ready": state.reader_status["ready"],
            "readers": state.reader_status["readers"],
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(WEBHOOK_URL, json=initial_payload, headers=HEADERS)
                print(f"[OK] Initial status sent: connected={state.reader_status['connected']}")
        except Exception as e:
            print(f"Could not send initial status: {e}")


if __name__ == "__main__":
    # Single worker only: PC/SC readers must not be opened by multiple processes.
    #es: Un solo worker: los lectores PC/SC no deben abrirse desde varios procesos.
    uvicorn.run("app.main:app", host="0.0.0.0", port=9000, reload=False, workers=1)
