"""PC/SC reader discovery helpers.
#es: Utilidades para descubrir lectores PC/SC.
"""

from __future__ import annotations

import re

from smartcard.System import readers

# ACR1252: "... Dual Reader SAM] 01 00" — SAM is a word, not always " SAM ".
# ACR122U: "... SAM Interface 0"
_SAM_INTERFACE = re.compile(r"\bSAM\b", re.IGNORECASE)


def is_nfc_reader(name: str) -> bool:
    """Return True for contactless (PICC) interfaces; ignore SAM interfaces.
    #es: True para interfaces contactless (PICC); ignora interfaces SAM.
    """
    return _SAM_INTERFACE.search(name) is None


def reader_names() -> list[str]:
    """List available NFC reader names (safe to call from the poll loop).
    #es: Lista nombres de lectores NFC disponibles (seguro desde el bucle de sondeo).
    """
    try:
        return [str(r) for r in readers() if is_nfc_reader(str(r))]
    except Exception:
        return []
