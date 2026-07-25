"""Drain SQLite outbox to the backend with durable retries across restarts.
#es: Drena el outbox SQLite al backend con reintentos durables entre reinicios.
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import WEBHOOK_CONCURRENCY
from app.services.webhook import post_webhook
from app import state


async def outbox_flusher():
    """Deliver pending outbox rows and mark them sent or failed.
    #es: Entrega filas pendientes del outbox y las marca enviadas o fallidas.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        print("[OK] SQLite outbox flusher started")
        while True:
            try:
                pending = state.outbox.fetch_pending(limit=WEBHOOK_CONCURRENCY * 2)
                if not pending:
                    await asyncio.sleep(1)
                    continue

                for item in pending:
                    ok = await post_webhook(client, item["payload"], retries=2)
                    if ok:
                        state.outbox.mark_sent(item["id"])
                    else:
                        state.outbox.mark_failed_attempt(
                            item["id"],
                            f"delivery failed after attempts={item['attempts'] + 1}",
                        )
                        await asyncio.sleep(min(2 ** min(item["attempts"], 5), 30))
                await asyncio.sleep(0.15)
            except Exception as e:
                print(f"[ERR] outbox_flusher(): {e}")
                await asyncio.sleep(2)
