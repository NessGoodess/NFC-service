"""Drain in-memory event queue into outbox / webhook.
#es: Drena la cola en memoria hacia el outbox / webhook.
"""

from __future__ import annotations

import asyncio

import httpx

from app.services.webhook import post_webhook
from app import state


async def sender():
    """Process queued card events into the durable outbox.
    #es: Procesa eventos de tarjeta hacia el outbox durable.
    """
    print("[OK] NFC sender started. Waiting for cards...")
    while True:
        try:
            # Events are already enriched in the card monitor.
            #es: Los eventos ya vienen enriquecidos desde el monitor de tarjetas.
            event = await state.event_queue.get()
            print(
                f"[QUEUE] event={event.get('event')} "
                f"slot={event.get('reader_slot_code')} cred={event.get('credential_id')}"
            )

            if event["event"] == "card_inserted":
                uid = event.get("uid")
                reader_name = event.get("reader")
                print(f"Card inserted: {uid} on {reader_name}")

                # Persist reads so process restarts do not lose them.
                #es: Persistir lecturas para que un reinicio del proceso no las pierda.
                event_id = state.outbox.enqueue(event)
                print(f"[OUTBOX] enqueued client_event_id={event_id}")
                continue

            # Status / removed: direct post (no durable side effects).
            #es: Estado / removed: POST directo (sin efectos durables).
            async with httpx.AsyncClient(timeout=10) as client:
                await post_webhook(client, event)

        except Exception as e:
            print(f"[ERR] sender(): {e}")
            await asyncio.sleep(1)
