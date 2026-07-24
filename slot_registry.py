"""Map PC/SC reader names to logical slot codes."""

from __future__ import annotations

from config import load_readers_config


class SlotRegistry:
    def __init__(self) -> None:
        self._by_pcsc: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
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
        if not pcsc_name:
            return None
        if pcsc_name in self._by_pcsc:
            return self._by_pcsc[pcsc_name]

        # Auto-bind first unmapped active slot (pairing helper for setup on Pi).
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
        if not slot_code:
            return None
        return self._labels.get(slot_code)

    def enrich_event(self, event: dict) -> dict:
        reader_name = event.get("reader") or event.get("reader_pcsc")
        explicit_slot = event.get("reader_slot_code")

        # Prefer explicit slot from webhook payloads when present.
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
