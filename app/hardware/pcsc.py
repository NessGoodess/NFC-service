"""PC/SC reader discovery helpers.
#es: Utilidades para descubrir lectores PC/SC.
"""

from __future__ import annotations

from smartcard.System import readers


def is_nfc_reader(name: str) -> bool:
    """Return True for contactless (PICC) interfaces; ignore SAM interfaces.
    #es: True para interfaces contactless (PICC); ignora interfaces SAM.
    """
    upper = name.upper()
    if " SAM " in upper or upper.endswith(" SAM 0"):
        return False
    return True


def reader_names() -> list[str]:
    """List available NFC reader names (safe to call from the poll loop).
    #es: Lista nombres de lectores NFC disponibles (seguro desde el bucle de sondeo).
    """
    try:
        return [str(r) for r in readers() if is_nfc_reader(str(r))]
    except Exception:
        return []
