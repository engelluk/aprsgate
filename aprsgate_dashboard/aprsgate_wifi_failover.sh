#!/usr/bin/env bash
set -u

PRIMARY_DEVICE="${APRSGATE_PRIMARY_WIFI_DEVICE:-wlan1}"
PRIMARY_CONNECTION="${APRSGATE_PRIMARY_WIFI_CONNECTION:?APRSGATE_PRIMARY_WIFI_CONNECTION is required}"
FALLBACK_DEVICE="${APRSGATE_FALLBACK_WIFI_DEVICE:-wlan0}"
FALLBACK_CONNECTION="${APRSGATE_FALLBACK_WIFI_CONNECTION:?APRSGATE_FALLBACK_WIFI_CONNECTION is required}"
USB_VENDOR="${APRSGATE_PRIMARY_USB_VENDOR:-}"
USB_PRODUCT="${APRSGATE_PRIMARY_USB_PRODUCT:-}"
CHECK_INTERVAL="${APRSGATE_WIFI_FAILOVER_INTERVAL:-15}"

last_state=""

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

  [[ -n "$USB_VENDOR" && -n "$USB_PRODUCT" ]] || return 1

  modprobe rtl8xxxu >/dev/null 2>&1 || true

  for interface_path in /sys/bus/usb/devices/*:*; do
    usb_path="${interface_path%:*}"
    [[ -f "${usb_path}/idVendor" && -f "${usb_path}/idProduct" ]] || continue
    [[ "$(<"${usb_path}/idVendor")" == "$USB_VENDOR" ]] || continue
    [[ "$(<"${usb_path}/idProduct")" == "$USB_PRODUCT" ]] || continue

    interface_name="${interface_path##*/}"
    if [[ ! -L "${interface_path}/driver" ]]; then
      printf '%s' "$interface_name" > /sys/bus/usb/drivers/rtl8xxxu/bind 2>/dev/null || true
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

while true; do
  if [[ ! -d "/sys/class/net/${PRIMARY_DEVICE}" ]]; then
    bind_primary_device || true
  fi

  if [[ -d "/sys/class/net/${PRIMARY_DEVICE}" ]]; then
    if ! connection_active "$PRIMARY_CONNECTION" "$PRIMARY_DEVICE" ||
       ! device_connected "$PRIMARY_DEVICE"; then
      activate_connection "$PRIMARY_CONNECTION" "$PRIMARY_DEVICE" || true
    fi

    if connection_active "$PRIMARY_CONNECTION" "$PRIMARY_DEVICE" &&
       device_connected "$PRIMARY_DEVICE"; then
      deactivate_connection "$FALLBACK_CONNECTION"
      set_state "primary" "primary WiFi active on ${PRIMARY_DEVICE}; fallback disabled"
    else
      ensure_fallback
      set_state "fallback-primary-unavailable" "primary WiFi unavailable; fallback active on ${FALLBACK_DEVICE}"
    fi
  else
    ensure_fallback
    set_state "fallback-device-missing" "primary WiFi device missing; fallback active on ${FALLBACK_DEVICE}"
  fi

  sleep "$CHECK_INTERVAL"
done
