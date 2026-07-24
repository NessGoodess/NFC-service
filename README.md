# NFC Reader — Raspberry Pi 5

Servicio FastAPI local para 2–4 lectores PC/SC (ACR122U / Reader 111) conectados al Pi.

## Hardware objetivo

- Raspberry Pi 5 (4 GB), BCM2712 @ 2.4 GHz
- 2–4 lectores NFC USB en la misma máquina
- ~600 alumnos / día (picos en entrada)

## Workers: 1 proceso + 3 envíos concurrentes

**No se debe usar `--workers 3` en uvicorn** para este servicio. Cada worker es un proceso distinto y todos intentarían abrir los lectores PC/SC → conflictos y lecturas perdidas.

| Capa | Concurrencia recomendada |
|------|--------------------------|
| **uvicorn** | `--workers 1` (único dueño del hardware) |
| **asyncio** | Cola de eventos + hasta **3 POST** simultáneos al backend (`NFC_WEBHOOK_CONCURRENCY=3`) |
| **Laravel** | 3 queue workers en el servidor (procesamiento de asistencia, fase 2) |

Instalación inicial en Raspberry Pi OS:

```bash
chmod +x install_pi.sh run_pi.sh
./install_pi.sh
# Editar .env y readers.json
sudo systemctl start est118-nfc-reader
journalctl -u est118-nfc-reader -f
```

## Configuración

1. Copia `.env.example` → `.env` (token Sanctum, URL del backend).
2. Edita `readers.json` con los slots lógicos (niños / niñas).
3. En el primer arranque, al detectar un lector sin `pcsc_name`, se auto-asigna al primer slot libre (modo pairing).

Configuración validada para dos lectores ACR1252:

```text
PICC 0 → boys-entry
PICC 1 → girls-entry
```

Los dispositivos `SAM 0` / `SAM 1` no son lectores de tarjetas y se filtran.

Variables útiles:

```env
NFC_SERVICE_TOKEN=...
NFC_WEBHOOK_URL=https://tu-api.com/api
NFC_WEBHOOK_CONCURRENCY=3
NFC_READER_POLL_INTERVAL=8
```

## Fase 2 — Confiabilidad

- Lecturas `card_inserted` se persisten en SQLite (`nfc_outbox.db`) antes de enviarse.
- Cada evento lleva `client_event_id` (UUID) → Laravel hace ACK 202 e idempotencia en `nfc_read_events`.
- Procesamiento async con `ProcessNfcReadJob` (en local: `NFC_INLINE_PROCESS=true` o `QUEUE_CONNECTION=sync`).

Producción Laravel (3 workers de cola):

```bash
php artisan queue:work --queue=default --sleep=1 --tries=3 --timeout=60
```

Los tres workers son de **Laravel**, no de uvicorn. En el Pi siempre se mantiene
un solo proceso uvicorn.

Verificación del backend:

```bash
php artisan migrate --force
php artisan db:seed --class=NfcReaderSlotSeeder
php scripts/audit_nfc_phase12.php
php scripts/check_nfc_idempotency.php
```

El reporte debe mostrar dos slots de entrada activos, cero `failed_nfc_jobs`,
cero duplicados y ambos `PICC` conectados.

## Endpoints locales

- `GET /` — health / URL de webhook configurada
- `GET /status` — lectores, cola en memoria y outbox pendiente
- `POST /assign-nfc` — escritura de credencial en tarjeta

## Deprecado

El folder `nfc_service/` (nfcpy, un solo lector) no se usa. Mantener solo `NFC-Reader/`.

