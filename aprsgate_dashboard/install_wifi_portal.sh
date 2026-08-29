#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/opt/aprsgate-dashboard"
CONFIG_FILE="/etc/default/aprsgate-wifi"
SERVICE_FILE="/etc/systemd/system/aprsgate-wifi-portal.service"
FAILOVER_BIN="/usr/local/sbin/aprsgate-wifi-failover"
FAILOVER_SERVICE_FILE="/etc/systemd/system/aprsgate-wifi-failover.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with sudo."
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "nmcli is missing. Install and enable NetworkManager first."
  exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Missing ${CONFIG_FILE}. Copy config/aprsgate-wifi.env.example there and configure it first."
  exit 1
fi

mkdir -p "${APP_DIR}" /etc/systemd/system /usr/local/sbin
cp "${SOURCE_DIR}/wifi_portal.py" "${APP_DIR}/wifi_portal.py"
cp "${SOURCE_DIR}/systemd/aprsgate-wifi-portal.service" "${SERVICE_FILE}"
cp "${SOURCE_DIR}/aprsgate_wifi_failover.sh" "${FAILOVER_BIN}"
cp "${SOURCE_DIR}/systemd/aprsgate-wifi-failover.service" "${FAILOVER_SERVICE_FILE}"
chmod 755 "${APP_DIR}/wifi_portal.py"
chmod 755 "${FAILOVER_BIN}"

systemctl daemon-reload
systemctl enable --now aprsgate-wifi-portal.service
systemctl enable --now aprsgate-wifi-failover.service

echo "Wi-Fi portal and failover services installed."
echo "The setup SSID, password, interfaces, and profiles come from ${CONFIG_FILE}."
