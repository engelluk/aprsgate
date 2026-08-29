#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with sudo."
  exit 1
fi

if ! id aprsgate >/dev/null 2>&1; then
  useradd --system --home-dir /opt/aprsgate-dashboard --shell /usr/sbin/nologin aprsgate
fi

install -d -o aprsgate -g aprsgate -m 755 /opt/aprsgate-dashboard
install -m 755 "${SOURCE_DIR}/aprsgate_sdr_helper.py" /usr/local/sbin/aprsgate-sdr-helper
install -m 440 "${SOURCE_DIR}/systemd/aprsgate-sdr-helper.sudoers" /etc/sudoers.d/aprsgate-sdr-helper
visudo -cf /etc/sudoers.d/aprsgate-sdr-helper

if [[ ! -f /etc/default/aprsgate-sdr ]]; then
  cat > /etc/default/aprsgate-sdr <<'EOF'
RTL_PPM=0
RTL_GAIN=35
RTL_FREQUENCY=144.800M
RTL_SAMPLE_RATE=24000
RTL_DEVICE=0
RTL_BIAS_T=0
EOF
fi

install -m 644 "${SOURCE_DIR}/systemd/direwolf-sdr.service" /etc/systemd/system/direwolf-sdr.service
install -m 644 "${SOURCE_DIR}/systemd/aprsgate-dashboard.service" /etc/systemd/system/aprsgate-dashboard.service
install -o aprsgate -g aprsgate -m 755 "${SOURCE_DIR}/app.py" /opt/aprsgate-dashboard/app.py

systemctl daemon-reload
systemctl enable --now direwolf-sdr.service
systemctl enable --now aprsgate-dashboard.service
