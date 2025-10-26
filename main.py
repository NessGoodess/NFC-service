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


from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString
from smartcard.System import readers

app = FastAPI()

WEBHOOK_URL = os.getenv("NFC_WEBHOOK_URL")+"/reader/uid-catcher"
reader_status = {"connected": False, "ready": False}

# Cola de eventos
event_queue: asyncio.Queue = asyncio.Queue()
pending_assign: dict | None = None

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

@app.on_event("startup")
async def startup():
    # Obtenemos loop principal
    loop = asyncio.get_running_loop()

    # Iniciamos CardMonitor con observer
    try:
        available_readers = readers()
        if not available_readers:
            reader_status["connected"] = False
            return
        else:
            reader_status["connected"] = True
    except Exception:
        reader_status["connected"] = False
        return
    
    cm = CardMonitor()
    observer = WebhookObserver(loop, event_queue)
    cm.addObserver(observer)
    reader_status["ready"] = True

    asyncio.create_task(sender())

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

# --- helper: escribir credential_id en páginas de usuario (páginas 4..39)
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

    # Rellenar a múltiplo de 4
    padded_len = math.ceil(len(payload) / 4) * 4
    padded = payload.ljust(padded_len, b"\x00")

    # Encontrar lector y conectarse
    for r in pcsc_readers():
        if str(r) == reader_name:
            try:
                conn = r.createConnection()
                conn.connect()

                # Escribir 4 bytes por página usando APDU FF D6 00 <page> 04 <4 bytes>
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

# --- En sender(), reemplaza el bloque donde tenías la 'simulación' por algo así:
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
                    print(f"📶 Tarjeta insertada: {uid} en {reader_name}")

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
                            print(f"✅ {msg}")
                        else:
                            print(f"❌ Falló la escritura: {msg}")

                        # Intentar enviar resultado al webhook (con reintentos simples)
                        for attempt in range(3):
                            try:
                                await client.post(WEBHOOK_URL, json=payload)
                                break
                            except Exception as e:
                                print(f"⚠️ Error enviando webhook (intento {attempt+1}): {e}")
                                await asyncio.sleep(2 ** attempt)

                        pending_assign = None

                # Enviar también el evento crudo al webhook (opcional)
                try:
                    await client.post(WEBHOOK_URL, json=event)
                except Exception as e:
                    print(f"⚠️ No se pudo enviar evento crudo al webhook: {e}")

            except Exception as e:
                print(f"❌ Error en sender(): {e}")
                await asyncio.sleep(1)
@app.post("/assign-nfc")
async def assign_nfc(request: Request):
    global pending_assign
    data = await request.json()
    credential_id = data.get("credential_id")

    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id is required")

    pending_assign = {"credential_id": credential_id, "action": "assign"}
    print(f"📦 Nueva tarea pendiente: asignar credential_id {credential_id}")

    return {"success": True, "message": f"Esperando tarjeta para credencial {credential_id}"}

@app.get("/")
async def root():
    return {"msg": "FastAPI NFC webhook", "webhook": WEBHOOK_URL}

@app.get("/status")
async def status():
    return reader_status

if __name__ == "__main__":
    uvicorn.run("main_webhook:app", host="0.0.0.0", port=8000, reload=True)
