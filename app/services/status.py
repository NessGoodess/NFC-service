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


async def reader_status_poller():
    """Watch reader connect/disconnect, restart monitoring, and notify the backend.
    #es: Vigila conexión/desconexión, reinicia el monitoreo y notifica al backend.
    """
    last_connected: bool = state.reader_status["connected"]
    last_readers: tuple = tuple(state.reader_status["readers"])
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            await asyncio.sleep(READER_POLL_INTERVAL)
            current_readers = tuple(reader_names())
            connected = len(current_readers) > 0
            if connected != last_connected or current_readers != last_readers:
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
                payload = {
                    "event": "reader_status_changed",
                    "connected": state.reader_status["connected"],
                    "ready": state.reader_status["ready"],
                    "readers": state.reader_status["readers"],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                if WEBHOOK_URL:
                    for attempt in range(3):
                        try:
                            await client.post(WEBHOOK_URL, json=payload, headers=HEADERS)
                            break
                        except Exception as e:
                            print(f"Error sending reader status (attempt {attempt + 1}): {e}")
                            await asyncio.sleep(2 ** attempt)
                last_connected = connected
                last_readers = current_readers
