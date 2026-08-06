"""Map PC/SC reader names to optional local slot hints.
#es: Mapea nombres PC/SC a pistas locales de slot (opcionales).

Laravel owns definitive PC/SC → panel binding. This registry only attaches a
hint from readers.json when already configured — it never auto-binds.
"""

from __future__ import annotations

from app.core.config import load_readers_config


class SlotRegistry:
    """Read-only in-memory map of configured PC/SC → slot code.
    #es: Mapa en memoria de solo lectura PC/SC → código de slot configurado.
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
        """Return configured slot for a PC/SC name. Never invent bindings.
        #es: Devuelve el slot configurado para un PC/SC. Nunca inventa enlaces.
        """
        if not pcsc_name:
            return None
        return self._by_pcsc.get(pcsc_name)

    def label_for(self, slot_code: str | None) -> str | None:
        """Human-readable label for a slot code.
        #es: Etiqueta legible para un código de slot.
        """
        if not slot_code:
            return None
        return self._labels.get(slot_code)

    def enrich_event(self, event: dict) -> dict:
        """Attach reader_pcsc and optional local slot hint when preconfigured.
        #es: Adjunta reader_pcsc y pista local de slot si ya está configurada.
        """
        reader_name = event.get("reader") or event.get("reader_pcsc")
        if reader_name:
            event["reader_pcsc"] = reader_name

        slot_code = self.resolve(reader_name)
        if slot_code:
            event["reader_slot_code"] = slot_code
            label = self.label_for(slot_code)
            if label:
                event["reader_label"] = label
        else:
            # Let Laravel resolve by DB pcsc_name; do not invent a panel here.
            event.pop("reader_slot_code", None)
            event.pop("reader_label", None)

        return event


slot_registry = SlotRegistry()
