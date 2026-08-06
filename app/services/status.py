"""Periodic PC/SC reader presence polling and reconnect.
#es: Sondeo periódico de presencia PC/SC y reconexión.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.core.config import HEADERS, READER_POLL_INTERVAL, WEBHOOK_URL
from app.hardware.monitor import start_card_monitor
from app.hardware.pcsc import reader_names
from app import state

# Re-push status even without USB changes so Laravel cache / UI select stay fresh.
#es: Reenvía status aunque no cambie el USB para que la caché Laravel / select de UI se mantengan.
HEARTBEAT_EVERY_POLLS = max(2, int(30 / max(READER_POLL_INTERVAL, 1)))


async def _post_status(client: httpx.AsyncClient, reason: str) -> None:
    payload = {
        "event": "reader_status_changed",
        "connected": state.reader_status["connected"],
        "ready": state.reader_status["ready"],
        "readers": state.reader_status["readers"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": reason,
    }
    if not WEBHOOK_URL:
        return
    for attempt in range(3):
        try:
            await client.post(WEBHOOK_URL, json=payload, headers=HEADERS)
            return
        except Exception as e:
            print(f"Error sending reader status (attempt {attempt + 1}): {e}")
            await asyncio.sleep(2 ** attempt)


async def reader_status_poller():
    """Watch reader connect/disconnect, restart monitoring, and notify the backend.
    #es: Vigila conexión/desconexión, reinicia el monitoreo y notifica al backend.
    """
    last_connected: bool = state.reader_status["connected"]
    last_readers: tuple = tuple(state.reader_status["readers"])
    polls_since_push = 0

    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            await asyncio.sleep(READER_POLL_INTERVAL)
            current_readers = tuple(reader_names())
            connected = len(current_readers) > 0
            changed = connected != last_connected or current_readers != last_readers
            polls_since_push += 1

            if changed:
                state.reader_status["connected"] = connected
                state.reader_status["readers"] = list(current_readers)
                if connected:
                    loop = asyncio.get_running_loop()
                    if start_card_monitor(loop):
                        state.reader_status["ready"] = True
                        print("[OK] Reader(s) reconnected:", current_readers)
                    else:
                        state.reader_status["ready"] = False
                else:
                    state.reader_status["ready"] = False
                    if state.card_monitor and state.webhook_observer:
                        try:
                            state.card_monitor.deleteObserver(state.webhook_observer)
                        except Exception:
                            pass
                    state.card_monitor = None
                    state.webhook_observer = None
                    print("[WARN] NFC reader disconnected")

                await _post_status(client, "change")
                last_connected = connected
                last_readers = current_readers
                polls_since_push = 0
            elif polls_since_push >= HEARTBEAT_EVERY_POLLS:
                # Keep Laravel connected_pcsc in sync for the config dropdown.
                #es: Mantiene connected_pcsc de Laravel al día para el dropdown de config.
                state.reader_status["readers"] = list(current_readers)
                state.reader_status["connected"] = connected
                await _post_status(client, "heartbeat")
                polls_since_push = 0
