#!/usr/bin/env bash
set -euo pipefail

export APRSGATE_PRIMARY_WIFI_CONNECTION=primary-wifi
export APRSGATE_FALLBACK_WIFI_CONNECTION=fallback-wifi
export APRSGATE_FAILOVER_LIB_ONLY=1

source "$(dirname "$0")/../aprsgate_dashboard/aprsgate_wifi_failover.sh"

device_connected() { return 0; }
nmcli() { printf '192.168.178.1\n'; }
ping() { printf '3 packets transmitted, 2 received, 33%% packet loss\n'; }
device_healthy wlan1

ping() { printf '3 packets transmitted, 1 received, 66%% packet loss\n'; }
if device_healthy wlan1; then
  echo "Unhealthy link was accepted" >&2
  exit 1
fi

PROFILE_FILE="$(mktemp)"
trap 'rm -f "$PROFILE_FILE"' EXIT
printf 'new-profile\n' > "$PROFILE_FILE"
[[ "$(primary_connection)" == "new-profile" ]]
printf '%s\n' "$SETUP_CONNECTION" > "$PROFILE_FILE"
[[ "$(primary_connection)" == "primary-wifi" ]]
