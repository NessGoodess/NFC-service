"""NTAG APDU read/write helpers via PC/SC.
#es: Utilidades APDU de lectura/escritura NTAG vía PC/SC.
"""

from __future__ import annotations

import math

from smartcard.System import readers as pcsc_readers


def read_pages_from_reader(reader_name, start_page, num_pages):
    """Read consecutive 4-byte pages from the named reader.
    #es: Lee páginas consecutivas de 4 bytes desde el lector indicado.
    """
    for r in pcsc_readers():
        if str(r) == reader_name:
            conn = r.createConnection()
            conn.connect()
            data_bytes = bytearray()
            for page in range(start_page, start_page + num_pages):
                # Driver-wrapped READ BINARY: FF B0 00 <page> 04
                #es: READ BINARY envuelto por el driver: FF B0 00 <page> 04
                READ_CMD = [0xFF, 0xB0, 0x00, page, 0x04]
                data, sw1, sw2 = conn.transmit(READ_CMD)
                if sw1 != 0x90:
                    raise RuntimeError(f"Error reading page {page}: SW1={hex(sw1)} SW2={hex(sw2)}")
                data_bytes.extend(bytes(data))
            return bytes(data_bytes)
    raise RuntimeError(f"Reader '{reader_name}' not found")


def write_credential_to_tag(reader_name: str, credential_id: str, start_page: int = 4):
    """Write credential_id (UTF-8) to NTAG213-style user pages (4..39).

    Returns (True, message) on success, or (False, message) on failure.
    #es: Escribe credential_id (UTF-8) en páginas de usuario estilo NTAG213 (4..39).
    #es: Devuelve (True, mensaje) si OK, o (False, mensaje) si falla.
    """
    # Prepare and pad payload to a multiple of 4 bytes.
    #es: Preparar y rellenar el payload a múltiplo de 4 bytes.
    payload = credential_id.encode("utf-8")
    max_user_pages = 36  # pages 4..39
    max_bytes = max_user_pages * 4  # 144 bytes

    if len(payload) > max_bytes:
        return False, f"credential_id too long ({len(payload)} bytes), max {max_bytes}"

    padded_len = math.ceil(len(payload) / 4) * 4
    padded = payload.ljust(padded_len, b"\x00")

    for r in pcsc_readers():
        if str(r) == reader_name:
            try:
                conn = r.createConnection()
                conn.connect()

                page = start_page
                for i in range(0, len(padded), 4):
                    chunk = list(padded[i : i + 4])
                    WRITE_CMD = [0xFF, 0xD6, 0x00, page, 0x04] + chunk
                    data, sw1, sw2 = conn.transmit(WRITE_CMD)
                    if sw1 != 0x90:
                        return False, f"Error writing page {page}: SW1={hex(sw1)} SW2={hex(sw2)}"
                    page += 1

                # Read back written pages to verify.
                #es: Releer las páginas escritas para verificar.
                num_pages_written = len(padded) // 4
                read_back = read_pages_from_reader(reader_name, start_page, num_pages_written)
                # Compare only original length (ignore padding).
                #es: Comparar solo la longitud original (ignorar padding).
                if read_back[: len(payload)] != payload:
                    return False, "Verification failed: read-back data does not match"
                return True, f"Write verified on pages {start_page}..{start_page + num_pages_written - 1}"
            except Exception as e:
                return False, f"Error accessing reader '{reader_name}': {e}"

    return False, f"Reader '{reader_name}' not found"
