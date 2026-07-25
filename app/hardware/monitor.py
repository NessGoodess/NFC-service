"""CardMonitor lifecycle and PC/SC card observer.
#es: Ciclo de vida de CardMonitor y observador de tarjetas PC/SC.
"""

from __future__ import annotations

import asyncio

from smartcard.CardMonitoring import CardMonitor, CardObserver

from app.hardware.card_reader import read_uid_from_card
from app.hardware.pcsc import reader_names
from app.services.slots import slot_registry
from app import state


class WebhookObserver(CardObserver):
    """Forward insert/remove card events into the asyncio queue.
    #es: Reenvía eventos de inserción/retirada de tarjeta a la cola asyncio.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self.loop = loop
        self.queue = queue

    def update(self, observable, cards):
        added_cards, removed_cards = cards

        for card in added_cards:
            try:
                uid, credential_id = read_uid_from_card(card)
            except Exception:
                uid = None
                credential_id = "Null"
            print(f"Card detected: UID={uid}, credential_id={credential_id}")
            event = {
                "event": "card_inserted",
                "reader": str(card.reader),
                "uid": uid,
                "credential_id": credential_id,
            }
            event = slot_registry.enrich_event(event)
            # Thread-safe enqueue onto the main asyncio loop.
            #es: Encolar de forma thread-safe en el loop principal de asyncio.
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

        for card in removed_cards:
            print(f"Card removed from reader {card.reader}")
            event = {"event": "card_removed", "reader": str(card.reader)}
            event = slot_registry.enrich_event(event)
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)


def start_card_monitor(loop: asyncio.AbstractEventLoop) -> bool:
    """Start or restart CardMonitor. Returns True if readers were found and monitoring started.
    #es: Inicia o reinicia CardMonitor. True si hay lectores y el monitoreo arrancó.
    """
    try:
        if state.card_monitor is not None and state.webhook_observer is not None:
            try:
                state.card_monitor.deleteObserver(state.webhook_observer)
            except Exception:
                pass
            state.card_monitor = None
            state.webhook_observer = None
        available = reader_names()
        if not available:
            state.reader_status["connected"] = False
            state.reader_status["ready"] = False
            state.reader_status["readers"] = []
            return False
        state.card_monitor = CardMonitor()
        state.webhook_observer = WebhookObserver(loop, state.event_queue)
        state.card_monitor.addObserver(state.webhook_observer)
        state.reader_status["connected"] = True
        state.reader_status["ready"] = True
        state.reader_status["readers"] = available
        return True
    except Exception as e:
        print(f"Error starting CardMonitor: {e}")
        state.reader_status["connected"] = bool(reader_names())
        state.reader_status["ready"] = False
        state.reader_status["readers"] = reader_names()
        return False
