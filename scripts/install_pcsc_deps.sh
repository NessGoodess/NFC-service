#!/usr/bin/env bash
# Install OS packages needed for PC/SC + Python venv (run before install_pi.sh, or let install_pi.sh call this).
#es: Instala paquetes del sistema para PC/SC + venv Python (antes de install_pi.sh, o déjalo llamarlo).
#
# Optional: skip and install packages yourself, then continue with install_pi.sh.
#es: Opcional: omite este script, instala los paquetes a mano y sigue con install_pi.sh.
#
# Manual equivalent / equivalente manual:
#   sudo apt-get update
#   sudo apt-get install -y git build-essential swig libccid libpcsclite-dev pcscd python3-dev python3-venv
#   sudo systemctl enable --now pcscd

set -euo pipefail

echo "=== Installing PC/SC system dependencies ==="
echo "=== Instalando dependencias de sistema PC/SC ==="

PACKAGES=(
  git
  build-essential
  swig
  libccid
  libpcsclite-dev
  pcscd
  python3-dev
  python3-venv
)

MISSING_PACKAGES=()
for pkg in "${PACKAGES[@]}"; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    MISSING_PACKAGES+=("$pkg")
    echo "[ ] Missing / Falta: $pkg"
  else
    echo "[x] Already installed / Ya instalado: $pkg"
  fi
done

if [ "${#MISSING_PACKAGES[@]}" -ne 0 ]; then
  echo
  echo "=== Installing / Instalando: ${MISSING_PACKAGES[*]} ==="
  sudo apt-get update
  sudo apt-get install -y "${MISSING_PACKAGES[@]}"
else
  echo
  echo "All packages already installed. / Todos los paquetes ya están instalados."
fi

sudo systemctl enable pcscd
# Socket activation may leave the daemon idle until first client; that is OK.
#es: Con socket activation el demonio puede quedar idle hasta el primer cliente; es normal.
sudo systemctl enable --now pcscd.socket 2>/dev/null || sudo systemctl enable --now pcscd

echo
echo "Done. Next: ./scripts/install_pi.sh"
echo "Listo. Siguiente: ./scripts/install_pi.sh"
echo "If pcsc_scan says Access denied over SSH, add a Polkit rule for your user (see project docs)."
echo "Si pcsc_scan dice Access denied por SSH, agrega una regla Polkit para tu usuario."
