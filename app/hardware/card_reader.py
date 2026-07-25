"""Read UID and credential payload from an inserted NFC tag.
#es: Lee UID y payload de credencial desde una etiqueta NFC insertada.
"""

from __future__ import annotations

from smartcard.util import toHexString


def read_uid_from_card(card) -> tuple[str | None, str]:
    """Read UID via GET DATA, then credential bytes from user pages 4–8.
    #es: Lee el UID con GET DATA y luego bytes de credencial en páginas 4–8.
    """
    conn = card.createConnection()
    conn.connect()

    # Read UID (standard PC/SC GET DATA).
    #es: Leer UID (GET DATA estándar PC/SC).
    GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    data, sw1, sw2 = conn.transmit(GET_UID)
    uid = None
    if sw1 == 0x90:
        uid = toHexString(data).replace(" ", "")

    # Read credential_id from NTAG-style user pages (4 bytes each).
    #es: Leer credential_id desde páginas de usuario tipo NTAG (4 bytes c/u).
    credential_id = ""
    for block in range(4, 9):  # pages/blocks 4–8
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
