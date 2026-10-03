#!/usr/bin/env bash
set -u

PRIMARY_DEVICE="${APRSGATE_PRIMARY_WIFI_DEVICE:-wlan1}"
PRIMARY_CONNECTION="${APRSGATE_PRIMARY_WIFI_CONNECTION:?APRSGATE_PRIMARY_WIFI_CONNECTION is required}"
FALLBACK_DEVICE="${APRSGATE_FALLBACK_WIFI_DEVICE:-wlan0}"
FALLBACK_CONNECTION="${APRSGATE_FALLBACK_WIFI_CONNECTION:?APRSGATE_FALLBACK_WIFI_CONNECTION is required}"
USB_VENDOR="${APRSGATE_PRIMARY_USB_VENDOR:-}"
USB_PRODUCT="${APRSGATE_PRIMARY_USB_PRODUCT:-}"
USB_DRIVER="${APRSGATE_PRIMARY_USB_DRIVER:-}"
CHECK_INTERVAL="${APRSGATE_WIFI_FAILOVER_INTERVAL:-15}"
PROFILE_FILE="${APRSGATE_PRIMARY_PROFILE_FILE:-/var/lib/aprsgate-wifi/primary-profile}"
LOCK_FILE="${APRSGATE_WIFI_LOCK_FILE:-/run/lock/aprsgate-wifi.lock}"
OFFLINE_FILE="${APRSGATE_WIFI_OFFLINE_FILE:-/run/aprsgate-wifi.offline}"
SETUP_CONNECTION="${APRSGATE_SETUP_CONNECTION:-aprsgate-setup-ap}"
SETUP_RETRY="${APRSGATE_SETUP_RETRY_INTERVAL:-120}"
RECONNECT_INTERVAL="${APRSGATE_PRIMARY_RECONNECT_INTERVAL:-120}"

last_state=""
healthy_checks=0
failed_checks=0
last_primary_attempt=0

log() {
  printf '%s\n' "$*"
}

set_state() {
  if [[ "$1" != "$last_state" ]]; then
    log "$2"
    last_state="$1"
  fi
}

connection_active() {
  nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null |
    grep -Fqx "${1}:${2}"
}

device_connected() {
  nmcli -g GENERAL.STATE device show "$1" 2>/dev/null |
    grep -q '^100'
}

primary_connection() {
  local saved
  if [[ -s "$PROFILE_FILE" ]]; then
    IFS= read -r saved < "$PROFILE_FILE"
    if [[ -n "$saved" && "$saved" != "$SETUP_CONNECTION" && "$saved" != "$FALLBACK_CONNECTION" ]]; then
      printf '%s' "$saved"
      return
    fi
  fi
  printf '%s' "$PRIMARY_CONNECTION"
}

device_healthy() {
  local device="$1" gateway output received
  device_connected "$device" || return 1
  gateway="$(nmcli -g IP4.GATEWAY device show "$device" 2>/dev/null | head -n 1)"
  [[ -n "$gateway" ]] || return 1
  output="$(LC_ALL=C ping -n -I "$device" -c 3 -i 0.3 -W 1 "$gateway" 2>/dev/null)" || true
  received="$(sed -nE 's/.* ([0-9]+) received.*/\1/p' <<< "$output" | tail -n 1)"
  [[ "$received" =~ ^[0-9]+$ && "$received" -ge 2 ]]
}

activate_connection() {
  local connection="$1"
  local device="$2"

  nmcli --wait 20 connection up "$connection" ifname "$device" >/dev/null 2>&1
}

deactivate_connection() {
  local connection="$1"

  nmcli --wait 10 connection down "$connection" >/dev/null 2>&1 || true
}

bind_primary_device() {
  local interface_path
  local usb_path
  local interface_name
  local bind_path

  [[ -n "$USB_VENDOR" && -n "$USB_PRODUCT" && -n "$USB_DRIVER" ]] || return 1

  modprobe "$USB_DRIVER" >/dev/null 2>&1 || true
  bind_path="/sys/bus/usb/drivers/${USB_DRIVER}/bind"
  [[ -w "$bind_path" ]] || return 1

  for interface_path in /sys/bus/usb/devices/*:*; do
    usb_path="${interface_path%:*}"
    [[ -f "${usb_path}/idVendor" && -f "${usb_path}/idProduct" ]] || continue
    [[ "$(<"${usb_path}/idVendor")" == "$USB_VENDOR" ]] || continue
    [[ "$(<"${usb_path}/idProduct")" == "$USB_PRODUCT" ]] || continue

    interface_name="${interface_path##*/}"
    if [[ ! -L "${interface_path}/driver" ]]; then
      printf '%s' "$interface_name" > "$bind_path" 2>/dev/null || true
    fi

    sleep 2
    [[ -d "/sys/class/net/${PRIMARY_DEVICE}" ]] && return 0
  done

  return 1
}

ensure_fallback() {
  if ! connection_active "$FALLBACK_CONNECTION" "$FALLBACK_DEVICE" ||
     ! device_connected "$FALLBACK_DEVICE"; then
    activate_connection "$FALLBACK_CONNECTION" "$FALLBACK_DEVICE" || true
  fi
}

if [[ "${APRSGATE_FAILOVER_LIB_ONLY:-0}" == "1" ]]; then
  return 0
fi

while true; do
  exec 9>"$LOCK_FILE"
  flock -w 30 9 || { sleep "$CHECK_INTERVAL"; continue; }
  current_primary="$(primary_connection)"
  now="$(date +%s)"
  if [[ ! -d "/sys/class/net/${PRIMARY_DEVICE}" ]]; then
    bind_primary_device || true
  fi

  if [[ -d "/sys/class/net/${PRIMARY_DEVICE}" ]]; then
    if connection_active "$SETUP_CONNECTION" "$PRIMARY_DEVICE"; then
      if (( now - last_primary_attempt >= SETUP_RETRY )); then
        deactivate_connection "$SETUP_CONNECTION"
        activate_connection "$current_primary" "$PRIMARY_DEVICE" || true
        last_primary_attempt="$now"
      fi
    elif ! connection_active "$current_primary" "$PRIMARY_DEVICE" ||
         ! device_connected "$PRIMARY_DEVICE"; then
      if ! device_healthy "$FALLBACK_DEVICE" ||
         (( now - last_primary_attempt >= RECONNECT_INTERVAL )); then
        activate_connection "$current_primary" "$PRIMARY_DEVICE" || true
        last_primary_attempt="$now"
      fi
    fi

    if connection_active "$current_primary" "$PRIMARY_DEVICE" && device_healthy "$PRIMARY_DEVICE"; then
      healthy_checks=$((healthy_checks + 1))
      failed_checks=0
      rm -f "$OFFLINE_FILE"
      if (( healthy_checks >= 3 )); then
        deactivate_connection "$FALLBACK_CONNECTION"
        set_state "primary" "primary WiFi healthy on ${PRIMARY_DEVICE}; fallback disabled"
      fi
    else
      failed_checks=$((failed_checks + 1))
      healthy_checks=0
      if (( failed_checks >= 2 )); then
        ensure_fallback
        set_state "fallback-primary-unhealthy" "primary WiFi unhealthy; fallback active on ${FALLBACK_DEVICE}"
        if device_healthy "$FALLBACK_DEVICE"; then
          rm -f "$OFFLINE_FILE"
          if connection_active "$current_primary" "$PRIMARY_DEVICE"; then
            deactivate_connection "$current_primary"
          fi
        else
          : > "$OFFLINE_FILE"
        fi
      fi
    fi
  else
    healthy_checks=0
    failed_checks=0
    ensure_fallback
    if device_healthy "$FALLBACK_DEVICE"; then
      rm -f "$OFFLINE_FILE"
    else
      : > "$OFFLINE_FILE"
    fi
    set_state "fallback-device-missing" "primary WiFi device missing; fallback active on ${FALLBACK_DEVICE}"
  fi

  flock -u 9
  exec 9>&-
  sleep "$CHECK_INTERVAL"
done
