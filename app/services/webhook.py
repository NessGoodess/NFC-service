"""HTTP webhook delivery to the configured backend API.
#es: Entrega de webhooks HTTP al API backend configurado.
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import HEADERS, WEBHOOK_URL
from app import state


async def post_webhook(client: httpx.AsyncClient, payload: dict, retries: int = 3) -> bool:
    """POST webhook. Returns True on HTTP 2xx (including 202 Accepted).
    #es: POST al webhook. True en HTTP 2xx (incluye 202 Accepted).
    """
    if not WEBHOOK_URL:
        return False
    assert state.webhook_semaphore is not None
    async with state.webhook_semaphore:
        for attempt in range(retries):
            try:
                response = await client.post(WEBHOOK_URL, json=payload, headers=HEADERS)
                if response.status_code >= 400:
                    print(
                        f"[WARN] Webhook HTTP {response.status_code} "
                        f"(attempt {attempt + 1}): {response.text[:200]}"
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue
                print(
                    f"[OK] Webhook {payload.get('event')} "
                    f"cred={payload.get('credential_id')} slot={payload.get('reader_slot_code')} "
                    f"-> HTTP {response.status_code}"
                )
                return True
            except Exception as e:
                print(f"[ERR] Webhook (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 ** attempt)
    return False
