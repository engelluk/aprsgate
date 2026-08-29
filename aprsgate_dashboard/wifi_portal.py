#!/usr/bin/env python3
import json
import os
import re
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


HOST = "0.0.0.0"
PORT = int(os.environ.get("APRSGATE_WIFI_PORTAL_PORT", "8088"))
WIFI_DEVICE = os.environ.get("APRSGATE_WIFI_DEVICE", "wlan0")
AP_SSID = os.environ.get("APRSGATE_SETUP_SSID", "APRSgate-Setup")
AP_PASSWORD = os.environ.get("APRSGATE_SETUP_PASSWORD", "")
AP_CONNECTION = os.environ.get("APRSGATE_SETUP_CONNECTION", "aprsgate-setup-ap")
CHECK_INTERVAL_SECONDS = int(os.environ.get("APRSGATE_WIFI_CHECK_INTERVAL", "30"))


INDEX_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>APRSgate WLAN Setup</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0f14;
      --panel: #121a22;
      --panel-2: #18222d;
      --text: #d9e4ee;
      --muted: #8a98a6;
      --line: #293744;
      --blue: #6ab7ff;
      --green: #39d98a;
      --red: #ff5c70;
      --yellow: #f2bf4d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    main {
      width: min(860px, calc(100% - 28px));
      margin: 0 auto;
      padding: 28px 0 36px;
    }
    header {
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 7vw, 52px);
      line-height: 1;
      letter-spacing: 0;
      text-transform: uppercase;
    }
    .sub, .muted { color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
      min-width: 0;
    }
    .span-2 { grid-column: span 2; }
    label {
      display: block;
      margin: 12px 0 6px;
      color: var(--muted);
      font-size: 13px;
    }
    input, select, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #070a0e;
      color: var(--text);
      font: inherit;
      padding: 10px 12px;
    }
    button {
      width: auto;
      cursor: pointer;
      background: var(--panel-2);
      margin-top: 12px;
    }
    button:hover { border-color: var(--blue); color: var(--blue); }
    .networks {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .network {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-2);
    }
    .status { margin-top: 12px; overflow-wrap: anywhere; }
    .ok { color: var(--green); }
    .bad { color: var(--red); }
    .warn { color: var(--yellow); }
    @media (max-width: 700px) {
      .grid { grid-template-columns: 1fr; }
      .span-2 { grid-column: span 1; }
      .network { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <h1>WLAN Setup</h1>
    <div class="sub">APRSgate verbindet sich automatisch mit gespeicherten Netzwerken. Wenn keines erreichbar ist, bleibt dieses Setup-WLAN aktiv.</div>
  </header>
  <section class="grid">
    <div class="panel">
      <h2>Status</h2>
      <div id="status" class="status muted">Lade...</div>
      <button type="button" onclick="refresh()">Aktualisieren</button>
    </div>
    <form class="panel" onsubmit="connectNetwork(event)">
      <h2>Einwählen</h2>
      <label for="ssid">SSID</label>
      <input id="ssid" name="ssid" autocomplete="off" required>
      <label for="password">Passwort</label>
      <input id="password" name="password" type="password" autocomplete="current-password">
      <button type="submit">Verbinden</button>
      <div id="connect-result" class="status muted"></div>
    </form>
    <div class="panel span-2">
      <h2>Gefundene WLANs</h2>
      <button type="button" onclick="scanNetworks()">Scannen</button>
      <div id="networks" class="networks"></div>
    </div>
  </section>
</main>
<script>
async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Fehler");
  return payload;
}

function setStatus(payload) {
  const status = document.getElementById("status");
  const state = document.createElement("span");
  state.className = payload.connected ? "ok" : "warn";
  state.textContent = payload.connected ? "verbunden" : "nicht verbunden";
  status.replaceChildren(state);
  const details = [
    `Gerät: ${payload.device}`,
    `Aktive SSID: ${payload.active_ssid || "-"}`,
    `Setup-AP: ${payload.setup_ap_active ? "aktiv" : "inaktiv"}`,
    `Bekannte WLANs: ${payload.known_connections.join(", ") || "-"}`,
  ];
  details.forEach((detail) => status.append(document.createElement("br"), document.createTextNode(detail)));
}

function setMessage(element, message, className) {
  const span = document.createElement("span");
  span.className = className;
  span.textContent = message;
  element.replaceChildren(span);
}

async function refresh() {
  try {
    setStatus(await api("/api/status"));
  } catch (error) {
    setMessage(document.getElementById("status"), error.message, "bad");
  }
}

async function scanNetworks() {
  const container = document.getElementById("networks");
  container.textContent = "Scanne...";
  try {
    const payload = await api("/api/scan");
    container.innerHTML = "";
    payload.networks.forEach((network) => {
      const row = document.createElement("div");
      row.className = "network";
      const title = document.createElement("div");
      const ssid = document.createElement("strong");
      ssid.textContent = network.ssid || "(versteckt)";
      const details = document.createElement("span");
      details.className = "muted";
      details.textContent = `${network.security || "offen"} · ${network.signal}%`;
      title.append(ssid, document.createElement("br"), details);
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Auswählen";
      button.onclick = () => { document.getElementById("ssid").value = network.ssid; };
      row.append(title, button);
      container.append(row);
    });
    if (!payload.networks.length) container.textContent = "Keine WLANs gefunden.";
  } catch (error) {
    setMessage(container, error.message, "bad");
  }
}

async function connectNetwork(event) {
  event.preventDefault();
  const result = document.getElementById("connect-result");
  result.textContent = "Verbinde...";
  const form = new FormData(event.target);
  try {
    const payload = await api("/api/connect", {
      method: "POST",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: new URLSearchParams(form),
    });
    setMessage(result, payload.message, "ok");
    await refresh();
  } catch (error) {
    setMessage(result, error.message, "bad");
  }
}

refresh();
scanNetworks();
</script>
</body>
</html>
"""


def run_nmcli(*args, check=False):
    result = subprocess.run(
        ["nmcli", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "nmcli failed"
        raise RuntimeError(detail)
    return result


def nmcli_lines(*args):
    result = run_nmcli(*args, check=True)
    return [line for line in result.stdout.splitlines() if line.strip()]


def active_ssid():
    result = run_nmcli("-t", "-f", "ACTIVE,SSID", "dev", "wifi")
    if result.returncode != 0:
        return ""
    for line in result.stdout.splitlines():
        fields = line.split(":", 1)
        if len(fields) == 2 and fields[0] == "yes":
            return fields[1]
    return ""


def setup_ap_active():
    result = run_nmcli("-t", "-f", "NAME,DEVICE", "connection", "show", "--active")
    return any(line.startswith(f"{AP_CONNECTION}:{WIFI_DEVICE}") for line in result.stdout.splitlines())


def known_connections():
    result = run_nmcli("-t", "-f", "NAME,TYPE", "connection", "show")
    if result.returncode != 0:
        return []
    names = []
    for line in result.stdout.splitlines():
        parts = line.rsplit(":", 1)
        if len(parts) == 2 and parts[1] == "802-11-wireless" and parts[0] != AP_CONNECTION:
            names.append(parts[0])
    return names


def is_connected():
    ssid = active_ssid()
    return bool(ssid and ssid != AP_SSID)


def ensure_setup_ap():
    if setup_ap_active():
        return
    print(f"wifi monitor: starting setup AP {AP_SSID}", flush=True)
    existing = run_nmcli("-t", "-f", "NAME", "connection", "show")
    if AP_CONNECTION not in existing.stdout.splitlines():
        run_nmcli(
            "connection", "add",
            "type", "wifi",
            "ifname", WIFI_DEVICE,
            "con-name", AP_CONNECTION,
            "ssid", AP_SSID,
            check=True,
        )
        run_nmcli("connection", "modify", AP_CONNECTION, "802-11-wireless.mode", "ap", check=True)
        run_nmcli("connection", "modify", AP_CONNECTION, "802-11-wireless.band", "bg", check=True)
        run_nmcli("connection", "modify", AP_CONNECTION, "ipv4.method", "shared", check=True)
        run_nmcli("connection", "modify", AP_CONNECTION, "ipv6.method", "ignore", check=True)
        run_nmcli("connection", "modify", AP_CONNECTION, "wifi-sec.key-mgmt", "wpa-psk", check=True)
        run_nmcli("connection", "modify", AP_CONNECTION, "wifi-sec.psk", AP_PASSWORD, check=True)
        run_nmcli("connection", "modify", AP_CONNECTION, "connection.autoconnect", "no", check=True)
    run_nmcli("connection", "up", AP_CONNECTION, check=True)


def stop_setup_ap():
    if setup_ap_active():
        print(f"wifi monitor: stopping setup AP {AP_SSID}", flush=True)
        run_nmcli("connection", "down", AP_CONNECTION)


def try_known_connections():
    for name in known_connections():
        print(f"wifi monitor: trying known connection {name}", flush=True)
        result = run_nmcli("connection", "up", name)
        if result.returncode == 0 and is_connected():
            print(f"wifi monitor: connected via {name}", flush=True)
            return True
    return False


def scan_networks():
    run_nmcli("device", "wifi", "rescan", "ifname", WIFI_DEVICE)
    time.sleep(2)
    lines = nmcli_lines("-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", WIFI_DEVICE)
    networks = []
    seen = set()
    for line in lines:
        ssid, signal, security = (line.split(":") + ["", "", ""])[:3]
        if not ssid or ssid in seen or ssid == AP_SSID:
            continue
        seen.add(ssid)
        networks.append({
            "ssid": ssid,
            "signal": signal,
            "security": security,
        })
    return networks


def connect_to_network(ssid, password):
    if not ssid:
        raise ValueError("SSID fehlt")
    stop_setup_ap()
    args = ["device", "wifi", "connect", ssid, "ifname", WIFI_DEVICE]
    if password:
        args.extend(["password", password])
    result = run_nmcli(*args)
    if result.returncode != 0:
        ensure_setup_ap()
        detail = result.stderr.strip() or result.stdout.strip() or "Verbindung fehlgeschlagen"
        raise RuntimeError(detail)
    return active_ssid() or ssid


def validate_runtime_config():
    valid_passphrase = 8 <= len(AP_PASSWORD) <= 63
    valid_raw_key = bool(re.fullmatch(r"[0-9A-Fa-f]{64}", AP_PASSWORD))
    if not (valid_passphrase or valid_raw_key):
        raise RuntimeError(
            "APRSGATE_SETUP_PASSWORD must be set to an 8-63 character "
            "passphrase or a 64-character hexadecimal WPA key"
        )


def monitor_wifi():
    while True:
        try:
            if is_connected():
                stop_setup_ap()
            elif setup_ap_active():
                pass
            elif not try_known_connections():
                ensure_setup_ap()
        except Exception as error:
            print(f"wifi monitor: {error}", flush=True)
        time.sleep(CHECK_INTERVAL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_bytes(self, body, content_type, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(body, "application/json; charset=utf-8", status)

    def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
        self.send_json({"error": str(message)}, status)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/":
                self.send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                self.send_json({
                    "device": WIFI_DEVICE,
                    "connected": is_connected(),
                    "active_ssid": active_ssid(),
                    "setup_ap_active": setup_ap_active(),
                    "setup_ssid": AP_SSID,
                    "known_connections": known_connections(),
                })
            elif path == "/api/scan":
                self.send_json({"networks": scan_networks()})
            elif path == "/healthz":
                self.send_json({"ok": True})
            else:
                self.send_error_json("not found", HTTPStatus.NOT_FOUND)
        except Exception as error:
            self.send_error_json(error, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/connect":
            self.send_error_json("not found", HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        fields = parse_qs(self.rfile.read(length).decode("utf-8"))
        ssid = fields.get("ssid", [""])[0].strip()
        password = fields.get("password", [""])[0]
        try:
            connected = connect_to_network(ssid, password)
            self.send_json({"message": f"Verbunden mit {connected}"})
        except Exception as error:
            self.send_error_json(error)


def main():
    validate_runtime_config()
    threading.Thread(target=monitor_wifi, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"aprsgate wifi portal listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
