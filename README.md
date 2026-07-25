# NFC Reader service

Local FastAPI service for multiple PC/SC NFC USB readers. Forwards card events to a backend webhook with a durable SQLite outbox.

## Layout

```text
NFC-Reader/
├── app/                   # service code
│   ├── main.py
│   ├── state.py
│   ├── api/
│   ├── core/
│   ├── hardware/
│   ├── services/
│   └── workers/
├── config/
│   ├── .env.example       # copy to config/.env
│   ├── .env               # local secrets (gitignored)
│   └── readers.json       # logical slots ↔ PC/SC names
├── data/                  # SQLite outbox (runtime)
├── scripts/
│   ├── install_pi.sh      # deps + venv + systemd unit
│   └── run_pi.sh          # service entrypoint
├── SYSTEMD_CONFIG.txt     # site-specific deploy notes
└── requirements.txt
```

Start: `uvicorn app.main:app` or `python -m app.main`.

## Concurrency model

**Do not use `uvicorn --workers > 1`.** Each worker is a separate process and would contend for the same PC/SC readers.

| Layer | Recommended concurrency |
|------|--------------------------|
| **uvicorn** | `--workers 1` (single owner of the hardware) |
| **asyncio** | Event queue + up to **N** concurrent POSTs (`NFC_WEBHOOK_CONCURRENCY`) |
| **Backend** | Process events with your own workers/queues as needed |

## Install (Linux + systemd + pcscd)

```bash
git clone <REPO_URL> ~/NFC-Reader
cd ~/NFC-Reader
chmod +x scripts/*.sh
./scripts/install_pi.sh
nano config/.env
# review config/readers.json
sudo systemctl start nfc-reader
journalctl -u nfc-reader -f
```

Site-specific hardware, tokens, and host details: see `SYSTEMD_CONFIG.txt`.

## Configuration

1. Copy `config/.env.example` → `config/.env` (service token + backend URL).
2. Edit `config/readers.json` with logical slots for your readers.
3. On first start, a reader without `pcsc_name` can auto-bind to the first free active slot (pairing mode).

Useful env vars (`config/.env`):

```env
NFC_SERVICE_TOKEN=...
NFC_WEBHOOK_URL=https://your-api.example/api
NFC_WEBHOOK_CONCURRENCY=3
NFC_READER_POLL_INTERVAL=8
```

## Durable delivery

- `card_inserted` events are persisted in SQLite (`data/nfc_outbox.db`) before webhook delivery.
- Each event includes `client_event_id` (UUID) so the backend can ACK (e.g. 202) and apply idempotency.
- Process restarts do not drop pending outbox rows.

## Local endpoints

- `GET /` — health / configured webhook URL
- `GET /status` — readers, in-memory queue, outbox pending count
- `POST /assign-nfc` — write a credential onto the next tapped card
