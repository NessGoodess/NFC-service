#!/usr/bin/env bash
# Install the EST118 NFC service on Raspberry Pi OS.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-$USER}"
SERVICE_NAME="est118-nfc-reader"

sudo apt-get update
sudo apt-get install -y \
  libccid \
  libpcsclite-dev \
  pcscd \
  python3-dev \
  python3-venv

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo "Edita ${APP_DIR}/.env antes de iniciar el servicio."
fi

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=EST118 NFC Reader FastAPI
After=network-online.target pcscd.service
Wants=network-online.target
Requires=pcscd.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/run_pi.sh
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pcscd "${SERVICE_NAME}"

echo
echo "Instalación lista."
echo "1) Configura ${APP_DIR}/.env y ${APP_DIR}/readers.json"
echo "2) Inicia: sudo systemctl start ${SERVICE_NAME}"
echo "3) Logs:   journalctl -u ${SERVICE_NAME} -f"
