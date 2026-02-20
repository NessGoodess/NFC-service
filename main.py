# main_webhook.py
import math
import time
from smartcard.System import readers as pcsc_readers
import asyncio
import json
import os
from fastapi import FastAPI, Request, HTTPException
import uvicorn
import httpx
from dotenv import load_dotenv

load_dotenv()

from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString
from smartcard.System import readers

TOKEN = os.getenv("NFC_SERVICE_TOKEN")
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

app = FastAPI()

WEBHOOK_BASE = (os.getenv("NFC_WEBHOOK_URL") or "").rstrip("/")
WEBHOOK_URL = f"{WEBHOOK_BASE}/reader/read-event" if WEBHOOK_BASE else ""
READER_POLL_INTERVAL = int(os.getenv("NFC_READER_POLL_INTERVAL", "5"))
reader_status = {"connected": False, "ready": False, "readers": []}

# Cola de eventos
event_queue: asyncio.Queue = asyncio.Queue()
pending_assign: dict | None = None
card_monitor: CardMonitor | None = None


class WebhookObserver(CardObserver):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self.loop = loop
        self.queue = queue

    def update(self, observable, cards):
        added_cards, removed_cards = cards

        for card in added_cards:
            try:
                uid, credential_id = self._read_uid_from_card(card)
            except Exception:
                uid = None
                credential_id = "Null"
            print(f"Tarjeta detectada: UID={uid}, credential ID={credential_id}")
            event = {
                "event": "card_inserted", 
                "reader": str(card.reader), 
                "uid": uid,
                "credential_id": credential_id
            }
            # Enviamos al loop principal de asyncio de forma thread-safe
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

        for card in removed_cards:
            print(f"Tarjeta removida del lector {card.reader}")
            event = {"event": "card_removed", "reader": str(card.reader)}
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    def _read_uid_from_card(self, card):
        conn = card.createConnection()
        conn.connect()

        # --- Leer UID ---
        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        data, sw1, sw2 = conn.transmit(GET_UID)
        uid = None
        if sw1 == 0x90:
            uid = toHexString(data).replace(" ", "")

        # --- Leer credential_id ---
        credential_id = ""
        for block in range(4, 9):  # bloques 4-8
            READ_CMD = [0xFF, 0xB0, 0x00, block, 0x04]
            data, sw1, sw2 = conn.transmit(READ_CMD)
            if sw1 == 0x90:
                credential_id += bytes(data).decode("utf-8", errors="ignore").strip()
            else:
                credential_id = None
                break
        if credential_id is None or credential_id == "":
            credential_id = "Null"

        return uid, credential_id

webhook_observer: WebhookObserver | None = None

def _reader_names():
    """Lista de nombres de lectores actualmente disponibles (thread-safe para polling)."""
    try:
        return [str(r) for r in readers()]
    except Exception:
        return []


def _start_card_monitor(loop: asyncio.AbstractEventLoop) -> bool:
    """Inicia o reinicia el CardMonitor. Devuelve True si hay lectores y se inició."""
    global card_monitor, webhook_observer
    try:
        if card_monitor is not None and webhook_observer is not None:
            try:
                card_monitor.deleteObserver(webhook_observer)
            except Exception:
                pass
            card_monitor = None
            webhook_observer = None
        available = _reader_names()
        if not available:
            reader_status["connected"] = False
            reader_status["ready"] = False
            reader_status["readers"] = []
            return False
        card_monitor = CardMonitor()
        webhook_observer = WebhookObserver(loop, event_queue)
        card_monitor.addObserver(webhook_observer)
        reader_status["connected"] = True
        reader_status["ready"] = True
        reader_status["readers"] = available
        return True
    except Exception as e:
        print(f"Error iniciando CardMonitor: {e}")
        reader_status["connected"] = bool(_reader_names())
        reader_status["ready"] = False
        reader_status["readers"] = _reader_names()
        return False


async def _reader_status_poller():
    """Comprueba periódicamente si el lector sigue conectado; reconecta y notifica al backend."""
    global card_monitor, webhook_observer
    last_connected: bool = reader_status["connected"]
    last_readers: tuple = tuple(reader_status["readers"])
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            await asyncio.sleep(READER_POLL_INTERVAL)
            current_readers = tuple(_reader_names())
            connected = len(current_readers) > 0
            if connected != last_connected or current_readers != last_readers:
                reader_status["connected"] = connected
                reader_status["readers"] = list(current_readers)
                if connected:
                    loop = asyncio.get_running_loop()
                    if _start_card_monitor(loop):
                        reader_status["ready"] = True
                        print("🟢 Lector(es) reconectado(s):", current_readers)
                    else:
                        reader_status["ready"] = False
                else:
                    reader_status["ready"] = False
                    if card_monitor and webhook_observer:
                        try:
                            card_monitor.deleteObserver(webhook_observer)
                        except Exception:
                            pass
                    card_monitor = None
                    webhook_observer = None
                    print("🔴 Lector NFC desconectado")
                payload = {
                    "event": "reader_status_changed",
                    "connected": reader_status["connected"],
                    "ready": reader_status["ready"],
                    "readers": reader_status["readers"],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                if WEBHOOK_URL:
                    for attempt in range(3):
                        try:
                            await client.post(WEBHOOK_URL, json=payload, headers=headers)
                            break
                        except Exception as e:
                            print(f"Error enviando estado del lector (intento {attempt+1}): {e}")
                            await asyncio.sleep(2 ** attempt)
                last_connected = connected
                last_readers = current_readers


@app.on_event("startup")
async def startup():
    loop = asyncio.get_running_loop()
    try:
        available = _reader_names()
        if not available:
            reader_status["connected"] = False
            reader_status["ready"] = False
            reader_status["readers"] = []
        else:
            _start_card_monitor(loop)
    except Exception:
        reader_status["connected"] = False
        reader_status["ready"] = False
        reader_status["readers"] = []

    asyncio.create_task(sender())
    asyncio.create_task(_reader_status_poller())

    # Enviar estado inicial al backend para sincronizar el frontend
    if WEBHOOK_URL:
        initial_payload = {
            "event": "reader_status_changed",
            "connected": reader_status["connected"],
            "ready": reader_status["ready"],
            "readers": reader_status["readers"],
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(WEBHOOK_URL, json=initial_payload, headers=headers)
                print(f"📡 Estado inicial enviado: connected={reader_status['connected']}")
        except Exception as e:
            print(f"No se pudo enviar estado inicial: {e}")

    # Tarea que consume la cola y envía webhook
# --- helper: leer páginas (4 bytes cada página) usando APDU PC/SC
def read_pages_from_reader(reader_name, start_page, num_pages):
    for r in pcsc_readers():
        if str(r) == reader_name:
            conn = r.createConnection()
            conn.connect()
            data_bytes = bytearray()
            for page in range(start_page, start_page + num_pages):
                # APDU de lectura de 4 bytes (envuelto por el driver): FF B0 00 <page> 04
                READ_CMD = [0xFF, 0xB0, 0x00, page, 0x04]
                data, sw1, sw2 = conn.transmit(READ_CMD)
                if sw1 != 0x90:
                    raise RuntimeError(f"Error leyendo página {page}: SW1={hex(sw1)} SW2={hex(sw2)}")
                data_bytes.extend(bytes(data))
            return bytes(data_bytes)
    raise RuntimeError(f"Lector '{reader_name}' no encontrado")

def write_credential_to_tag(reader_name: str, credential_id: str, start_page: int = 4):
    """
    Escribe credential_id (utf-8) en páginas de usuario del NTAG213 (4..39).
    Devuelve (True, mensaje) si OK, o (False, mensaje) si falla.
    """
    # Preparar bytes
    payload = credential_id.encode("utf-8")
    max_user_pages = 36  # páginas 4..39
    max_bytes = max_user_pages * 4  # 144 bytes

    if len(payload) > max_bytes:
        return False, f"credential_id demasiado largo ({len(payload)} bytes), max {max_bytes}"

    padded_len = math.ceil(len(payload) / 4) * 4
    padded = payload.ljust(padded_len, b"\x00")

    for r in pcsc_readers():
        if str(r) == reader_name:
            try:
                conn = r.createConnection()
                conn.connect()

                page = start_page
                for i in range(0, len(padded), 4):
                    chunk = list(padded[i:i+4])
                    WRITE_CMD = [0xFF, 0xD6, 0x00, page, 0x04] + chunk
                    data, sw1, sw2 = conn.transmit(WRITE_CMD)
                    if sw1 != 0x90:
                        return False, f"Error escribiendo página {page}: SW1={hex(sw1)} SW2={hex(sw2)}"
                    page += 1

                # Leer de vuelta las páginas escritas para verificar
                num_pages_written = len(padded) // 4
                read_back = read_pages_from_reader(reader_name, start_page, num_pages_written)
                # comparar sólo hasta la longitud original (sin padding)
                if read_back[:len(payload)] != payload:
                    return False, "Verificación falló: datos leídos no coinciden"
                return True, f"Escritura verificada en páginas {start_page}..{start_page+num_pages_written-1}"
            except Exception as e:
                return False, f"Error al acceder al lector '{reader_name}': {e}"

    return False, f"Lector '{reader_name}' no encontrado"

async def sender():
    global pending_assign

    async with httpx.AsyncClient(timeout=10) as client:
        print("🟢 Sender NFC iniciado. Esperando tarjetas...")
        while True:
            try:
                event = await event_queue.get()

                if event["event"] == "card_inserted":
                    uid = event.get("uid")
                    reader_name = event.get("reader")
                    print(f"Tarjeta insertada: {uid} en {reader_name}")

                    if pending_assign and pending_assign.get("action") == "assign":
                        credential_id = pending_assign["credential_id"]

                        # Escribir en la tarjeta (real)
                        success, msg = write_credential_to_tag(reader_name, credential_id)
                        payload = {
                            "event": "nfc_assigned",
                            "credential_id": credential_id,
                            "uid": uid,
                            "success": success,
                            "message": msg
                        }

                        if success:
                            print(f"{msg}")
                        else:
                            print(f"Falló la escritura: {msg}")

                        # Intentar enviar resultado al webhook (con reintentos simples)
                        for attempt in range(3):
                            try:
                                await client.post(WEBHOOK_URL, json=payload, headers=headers)
                                break
                            except Exception as e:
                                print(f"Error enviando webhook (intento {attempt+1}): {e}")
                                await asyncio.sleep(2 ** attempt)

                        pending_assign = None

                # Enviar también el evento crudo al webhook (opcional)
                try:
                    await client.post(WEBHOOK_URL, json=event, headers=headers)
                except Exception as e:
                    print(f"No se pudo enviar evento crudo al webhook: {e}")

            except Exception as e:
                print(f"Error en sender(): {e}")
                await asyncio.sleep(1)
@app.post("/assign-nfc")
async def assign_nfc(request: Request):
    global pending_assign
    data = await request.json()
    credential_id = data.get("credential_id")

    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id is required")

    pending_assign = {"credential_id": credential_id, "action": "assign"}
    print(f"Nueva tarea pendiente: asignar credential_id {credential_id}")

    return {"success": True, "message": f"Esperando tarjeta para credencial {credential_id}"}

@app.get("/")
async def root():
    return {"msg": "FastAPI NFC webhook", "webhook": WEBHOOK_URL}

@app.get("/status")
async def status():
    return reader_status

if __name__ == "__main__":
    uvicorn.run("reader:app", host="0.0.0.0", port=9000, reload=True)