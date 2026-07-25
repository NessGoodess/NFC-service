"""Map PC/SC reader names to logical slot codes.
#es: Mapea nombres de lectores PC/SC a códigos de slot lógicos.
"""

from __future__ import annotations

from app.core.config import load_readers_config


class SlotRegistry:
    """In-memory registry of active slots and optional auto-pairing.
    #es: Registro en memoria de slots activos y emparejamiento opcional.
    """

    def __init__(self) -> None:
        self._by_pcsc: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Reload slot definitions from readers.json.
        #es: Recarga las definiciones de slots desde readers.json.
        """
        cfg = load_readers_config()
        self._by_pcsc = {}
        self._labels = {}

        for slot in cfg.get("slots", []):
            if slot.get("active", True) is False:
                continue
            code = slot.get("code")
            if not code:
                continue
            self._labels[code] = slot.get("label", code)
            pcsc_name = slot.get("pcsc_name")
            if pcsc_name:
                self._by_pcsc[pcsc_name] = code

    def resolve(self, pcsc_name: str | None) -> str | None:
        """Resolve a PC/SC name to a slot code; auto-bind first free slot if needed.
        #es: Resuelve un nombre PC/SC a un código de slot; auto-asigna el primer slot libre si hace falta.
        """
        if not pcsc_name:
            return None
        if pcsc_name in self._by_pcsc:
            return self._by_pcsc[pcsc_name]

        # Auto-bind first unmapped active slot (setup/pairing helper).
        #es: Auto-asignar el primer slot activo sin mapear (ayuda de setup/emparejamiento).
        cfg = load_readers_config()
        for slot in cfg.get("slots", []):
            if slot.get("active", True) is False:
                continue
            code = slot.get("code")
            if not code or slot.get("pcsc_name"):
                continue
            self._by_pcsc[pcsc_name] = code
            slot["pcsc_name"] = pcsc_name
            return code

        return None

    def label_for(self, slot_code: str | None) -> str | None:
        """Human-readable label for a slot code.
        #es: Etiqueta legible para un código de slot.
        """
        if not slot_code:
            return None
        return self._labels.get(slot_code)

    def enrich_event(self, event: dict) -> dict:
        """Attach reader_slot_code / reader_label / reader_pcsc when possible.
        #es: Adjunta reader_slot_code / reader_label / reader_pcsc cuando sea posible.
        """
        reader_name = event.get("reader") or event.get("reader_pcsc")
        explicit_slot = event.get("reader_slot_code")

        # Prefer an explicit slot already present on the payload.
        #es: Preferir un slot explícito si ya viene en el payload.
        if explicit_slot:
            if reader_name:
                event["reader_pcsc"] = reader_name
                if reader_name not in self._by_pcsc:
                    self._by_pcsc[reader_name] = explicit_slot
            label = self.label_for(explicit_slot)
            if label:
                event["reader_label"] = label
            return event

        slot_code = self.resolve(reader_name)
        if slot_code:
            event["reader_slot_code"] = slot_code
            event["reader_pcsc"] = reader_name
            label = self.label_for(slot_code)
            if label:
                event["reader_label"] = label
        elif reader_name:
            event["reader_pcsc"] = reader_name
        return event


slot_registry = SlotRegistry()
