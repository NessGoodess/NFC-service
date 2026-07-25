#!/usr/bin/env bash
# Install the NFC reader service (venv, deps, systemd unit) on a Linux host with PC/SC.
#es: Instala el servicio lector NFC (venv, deps, unit systemd) en un host Linux con PC/SC.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="${SUDO_USER:-$USER}"
SERVICE_NAME="nfc-reader"

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

mkdir -p "${APP_DIR}/data"

if [ ! -f "${APP_DIR}/config/.env" ]; then
  cp "${APP_DIR}/config/.env.example" "${APP_DIR}/config/.env"
  echo "Edit ${APP_DIR}/config/.env before starting the service."
fi

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=NFC Reader FastAPI service
After=network-online.target pcscd.service
Wants=network-online.target
Requires=pcscd.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/scripts/run_pi.sh
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

chmod +x "${APP_DIR}/scripts/run_pi.sh" "${APP_DIR}/scripts/install_pi.sh"

sudo systemctl daemon-reload
sudo systemctl enable pcscd "${SERVICE_NAME}"

echo
echo "Install complete."
echo "1) Configure ${APP_DIR}/config/.env and ${APP_DIR}/config/readers.json"
echo "2) Start:  sudo systemctl start ${SERVICE_NAME}"
echo "3) Logs:   journalctl -u ${SERVICE_NAME} -f"
