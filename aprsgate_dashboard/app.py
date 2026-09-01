#!/usr/bin/env python3
import json
import math
import os
import re
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import parse_qs, urlparse


SERVICE = "direwolf-sdr.service"
HOST = "0.0.0.0"
PORT = int(os.environ.get("APRSGATE_DASHBOARD_PORT", "8080"))
SDR_HELPER = "/usr/local/sbin/aprsgate-sdr-helper"
PACKET_STORE = os.environ.get("APRSGATE_PACKET_STORE", "/var/lib/aprsgate-dashboard/packets.jsonl")
MAX_STORED_PACKETS = int(os.environ.get("APRSGATE_MAX_STORED_PACKETS", "50000"))
DIAGNOSTIC_SERVICES = (
    "aprsgate-dashboard.service",
    "direwolf-sdr.service",
    "aprsgate-wifi-portal.service",
    "aprsgate-wifi-failover.service",
)


INDEX_HTML = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>APRSgate Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0f14;
      --panel: #111820;
      --panel-2: #151e28;
      --text: #d7e1ea;
      --muted: #7e8c99;
      --line: #25313d;
      --green: #39d98a;
      --yellow: #f2bf4d;
      --red: #ff5c70;
      --blue: #6ab7ff;
      --cyan: #7ef3e2;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px) 0 0 / 44px 44px,
        linear-gradient(180deg, rgba(255,255,255,.018) 1px, transparent 1px) 0 0 / 44px 44px,
        var(--bg);
      color: var(--text);
      font-family: "Courier New", ui-monospace, SFMono-Regular, Menlo, monospace;
    }

    main {
      width: min(1180px, calc(100% - 28px));
      margin: 0 auto;
      padding: 26px 0 34px;
    }

    header {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
      padding-bottom: 22px;
      border-bottom: 1px solid var(--line);
    }

    h1 {
      margin: 0;
      font-size: clamp(28px, 6vw, 64px);
      line-height: .95;
      letter-spacing: 0;
      text-transform: uppercase;
    }

    .sub {
      color: var(--muted);
      margin-top: 10px;
      font-size: 14px;
    }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .mode-tabs {
      display: inline-flex;
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
    }

    .mode-tabs button {
      border: 0;
      border-right: 1px solid var(--line);
      border-radius: 0;
    }

    .mode-tabs button:last-child { border-right: 0; }
    .mode-tabs button[aria-selected="true"] { background: var(--blue); color: #07101a; }

    button, a.button {
      appearance: none;
      border: 1px solid var(--line);
      color: var(--text);
      background: var(--panel);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      font-size: 13px;
      text-decoration: none;
      cursor: pointer;
    }

    button:hover, a.button:hover { border-color: var(--blue); color: var(--blue); }

    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
      margin-top: 18px;
    }

    .panel {
      background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.01)), var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }

    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-5 { grid-column: span 5; }
    .span-7 { grid-column: span 7; }
    .span-12 { grid-column: span 12; }

    .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      margin-bottom: 10px;
    }

    .value {
      font-size: 24px;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }

    .small { font-size: 13px; color: var(--muted); margin-top: 8px; overflow-wrap: anywhere; }
    .ok { color: var(--green); }
    .warn { color: var(--yellow); }
    .bad { color: var(--red); }
    .blue { color: var(--blue); }
    .cyan { color: var(--cyan); }

    .kv {
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 8px 12px;
      font-size: 14px;
    }

    .kv div:nth-child(odd) { color: var(--muted); }
    .kv div:nth-child(even) { overflow-wrap: anywhere; }

    pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 12px;
      line-height: 1.45;
      max-height: 420px;
      overflow: auto;
      color: #c6d3df;
    }

    .events {
      display: grid;
      gap: 8px;
      font-size: 13px;
    }

    .event {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 6px;
      padding: 10px;
      overflow-wrap: anywhere;
    }

    .packet-tools {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) auto;
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }

    input {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #070a0e;
      color: var(--text);
      font: inherit;
      font-size: 13px;
      padding: 10px 12px;
    }

    input:focus {
      outline: 1px solid var(--blue);
      border-color: var(--blue);
    }

    .calibration-form {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      align-items: end;
    }

    .field { min-width: 0; }

    .field label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      margin-bottom: 6px;
    }

    .field button { width: 100%; }

    .calibration-result {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }

    .result-cell {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 6px;
      padding: 10px;
      min-width: 0;
    }

    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      max-height: 480px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 1040px;
      font-size: 12px;
    }

    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }

    th {
      position: sticky;
      top: 0;
      background: #0f151d;
      color: var(--muted);
      text-transform: uppercase;
      z-index: 1;
    }

    tbody tr:hover { background: rgba(106, 183, 255, .06); }
    td.raw { max-width: 360px; overflow-wrap: anywhere; }

    .meter {
      height: 7px;
      border: 1px solid var(--line);
      border-radius: 99px;
      overflow: hidden;
      background: #070a0e;
      margin-top: 14px;
    }

    .meter > div {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--green), var(--cyan), var(--blue));
      transition: width .25s ease;
    }

    footer {
      color: var(--muted);
      margin-top: 18px;
      font-size: 12px;
    }

    .view[hidden] { display: none; }

    .status-view { margin-top: 24px; }

    .status-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }

    .status-header h2 {
      margin: 0;
      font-size: 20px;
      text-transform: uppercase;
    }

    .status-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 22px 28px;
      margin-top: 22px;
    }

    .status-group { min-width: 0; }
    .status-group.wide { grid-column: 1 / -1; }

    .status-group h3 {
      margin: 0 0 9px;
      color: var(--muted);
      font-size: 12px;
      font-weight: normal;
      text-transform: uppercase;
    }

    .status-kv {
      border-top: 1px solid var(--line);
    }

    .status-row {
      display: grid;
      grid-template-columns: minmax(130px, 38%) minmax(0, 1fr);
      gap: 14px;
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
    }

    .status-key { color: var(--muted); }
    .status-value { overflow-wrap: anywhere; white-space: pre-wrap; }

    .status-table-wrap {
      width: 100%;
      overflow: auto;
      border-top: 1px solid var(--line);
    }

    .status-table { min-width: 920px; }
    .status-table th, .status-table td { padding: 8px 9px; }
    .status-list { line-height: 1.7; overflow-wrap: anywhere; }

    .map-view { margin-top: 24px; }

    .map-toolbar {
      display: grid;
      grid-template-columns: auto minmax(190px, 1fr) 180px auto;
      gap: 10px;
      align-items: center;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }

    .period-tabs {
      display: inline-flex;
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
    }

    .period-tabs button {
      min-width: 42px;
      border: 0;
      border-right: 1px solid var(--line);
      border-radius: 0;
      padding: 10px;
    }

    .period-tabs button:last-child { border-right: 0; }
    .period-tabs button[aria-pressed="true"] { background: var(--cyan); color: #071311; }

    select {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
      font-size: 13px;
      padding: 10px 12px;
    }

    .track-toggle {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }

    .track-toggle input { width: 16px; height: 16px; accent-color: var(--cyan); }

    .map-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border-bottom: 1px solid var(--line);
    }

    .map-stat {
      min-width: 0;
      padding: 13px 14px 12px 0;
      border-right: 1px solid var(--line);
    }

    .map-stat:not(:first-child) { padding-left: 14px; }
    .map-stat:last-child { border-right: 0; }
    .map-stat .label { margin-bottom: 5px; }
    .map-stat-value { font-size: 18px; overflow-wrap: anywhere; }

    .map-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 292px;
      min-height: 520px;
      height: min(720px, 68vh);
      border-bottom: 1px solid var(--line);
    }

    #stationMap {
      width: 100%;
      height: 100%;
      min-height: 520px;
      background: #101820;
      border-right: 1px solid var(--line);
    }

    .station-rail {
      min-width: 0;
      display: flex;
      flex-direction: column;
      background: rgba(11, 15, 20, .92);
    }

    .station-rail-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 12px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
    }

    .station-list { overflow: auto; min-height: 0; }

    .station-item {
      width: 100%;
      display: grid;
      grid-template-columns: 12px minmax(0, 1fr) auto;
      gap: 9px;
      align-items: center;
      padding: 11px 12px;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      background: transparent;
      text-align: left;
    }

    .station-item:hover, .station-item.active { background: var(--panel-2); color: var(--text); }
    .station-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cyan); }
    .station-dot.digipeated { background: var(--yellow); }
    .station-call { display: block; color: var(--text); font-size: 13px; }
    .station-meta { display: block; margin-top: 4px; color: var(--muted); font-size: 11px; }
    .station-distance { color: var(--muted); font-size: 11px; white-space: nowrap; }
    .map-message { padding: 18px 12px; color: var(--muted); font-size: 12px; }

    .map-legend {
      padding: 8px 10px;
      background: rgba(11, 15, 20, .92);
      border: 1px solid #34414d;
      color: var(--text);
      font: 11px "Courier New", monospace;
      line-height: 1.8;
    }

    .map-legend span { display: inline-flex; align-items: center; gap: 6px; margin-right: 10px; }
    .legend-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cyan); }
    .legend-dot.digipeated { background: var(--yellow); }
    .legend-dot.track { width: 6px; height: 6px; opacity: .6; }
    .legend-dot.gateway { background: var(--blue); }

    .leaflet-container { font-family: "Courier New", ui-monospace, monospace; }
    .leaflet-popup-content-wrapper, .leaflet-popup-tip {
      background: #111820;
      color: var(--text);
      border-radius: 6px;
    }
    .leaflet-popup-content-wrapper { border: 1px solid var(--line); }
    .leaflet-popup-content { margin: 12px 14px; min-width: 220px; }
    .leaflet-popup-close-button { color: var(--muted) !important; }
    .leaflet-control-attribution { background: rgba(255,255,255,.88) !important; color: #25313d; }
    .popup-call { color: var(--cyan); font-size: 16px; margin-bottom: 8px; }
    .popup-row { display: grid; grid-template-columns: 94px 1fr; gap: 8px; padding: 3px 0; font-size: 11px; }
    .popup-key { color: var(--muted); }

    @media (max-width: 880px) {
      header { grid-template-columns: 1fr; align-items: start; }
      .actions { justify-content: flex-start; }
      .span-3, .span-4, .span-5, .span-7 { grid-column: span 12; }
      .kv { grid-template-columns: 1fr; gap: 3px 0; }
      .calibration-form, .calibration-result { grid-template-columns: 1fr; }
      .status-grid { grid-template-columns: 1fr; }
      .status-group.wide { grid-column: auto; }
      .status-row { grid-template-columns: 1fr; gap: 3px; }
      .map-toolbar { grid-template-columns: 1fr; }
      .period-tabs { width: 100%; }
      .period-tabs button { flex: 1; }
      .map-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .map-stat:nth-child(2) { border-right: 0; }
      .map-stat:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
      .map-layout { grid-template-columns: 1fr; height: auto; }
      #stationMap { height: 58vh; min-height: 440px; border-right: 0; border-bottom: 1px solid var(--line); }
      .station-rail { max-height: 320px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>APRSgate</h1>
        <div id="stationIdentity" class="sub">Configured station / RTL-SDR / Dire Wolf / 144.800 MHz</div>
      </div>
      <div class="actions">
        <div class="mode-tabs" role="tablist" aria-label="Ansicht">
          <button id="overviewTab" type="button" role="tab" aria-selected="true" aria-controls="overviewView">Uebersicht</button>
          <button id="mapTab" type="button" role="tab" aria-selected="false" aria-controls="mapView">Karte</button>
          <button id="statusTab" type="button" role="tab" aria-selected="false" aria-controls="statusView">Status</button>
        </div>
        <button id="refresh" title="Status neu laden">Refresh</button>
        <a id="aprsFiLink" class="button" href="https://aprs.fi/" target="_blank" rel="noreferrer">APRS.fi</a>
      </div>
    </header>

    <section id="overviewView" class="grid view" role="tabpanel" aria-labelledby="overviewTab">
      <article class="panel span-3">
        <div class="label">Dire Wolf</div>
        <div id="service" class="value">...</div>
        <div id="serviceDetail" class="small">lade Status</div>
        <div class="meter"><div id="heartbeat"></div></div>
      </article>

      <article class="panel span-3">
        <div class="label">APRS-IS</div>
        <div id="aprsis" class="value">...</div>
        <div id="server" class="small">warte auf Logdaten</div>
      </article>

      <article class="panel span-3">
        <div class="label">SDR</div>
        <div id="sdr" class="value">...</div>
        <div id="usb" class="small">USB pruefen</div>
      </article>

      <article class="panel span-3">
        <div class="label">System</div>
        <div id="temp" class="value">...</div>
        <div id="uptime" class="small">...</div>
      </article>

      <article class="panel span-3">
        <div class="label">Pakete</div>
        <div id="packetCount" class="value">0</div>
        <div id="packetDetail" class="small">keine Pakete</div>
      </article>

      <article class="panel span-5">
        <div class="label">Konfiguration</div>
        <div class="kv">
          <div>Rufzeichen</div><div id="call">...</div>
          <div>Frequenz</div><div id="freq">...</div>
          <div>Position</div><div id="position">...</div>
          <div>Beacon</div><div id="beacon">...</div>
        </div>
      </article>

      <article class="panel span-7">
        <div class="label">Letzte Ereignisse</div>
        <div id="events" class="events"></div>
      </article>

      <article class="panel span-12">
        <div class="label">SDR-Kalibrierung</div>
        <div class="calibration-form">
          <div class="field">
            <label for="calFreq">Testfrequenz MHz</label>
            <input id="calFreq" type="number" step="0.001" min="24" max="1766" value="145.500">
          </div>
          <div class="field">
            <label for="calPpm">PPM</label>
            <input id="calPpm" type="number" step="1" min="-200" max="200" value="0">
          </div>
          <div class="field">
            <label for="calGain">Gain dB</label>
            <input id="calGain" type="number" step="0.1" min="0" max="50" value="35">
          </div>
          <div class="field">
            <label for="calSpan">Scan kHz</label>
            <input id="calSpan" type="number" step="10" min="20" max="500" value="120">
          </div>
          <div class="field">
            <button id="measureCalibration" type="button">Peak messen</button>
          </div>
          <div class="field">
            <button id="applyCalibration" type="button">Werte speichern</button>
          </div>
        </div>
        <div id="calibrationStatus" class="small">PTT auf einer freien erlaubten 2m-Frequenz gedrueckt halten, dann Peak messen klicken.</div>
        <div class="calibration-result">
          <div class="result-cell"><div class="label">Aktuell</div><div id="calCurrent" class="value">...</div></div>
          <div class="result-cell"><div class="label">Peak</div><div id="calPeak" class="value">-</div></div>
          <div class="result-cell"><div class="label">Abweichung</div><div id="calOffset" class="value">-</div></div>
          <div class="result-cell"><div class="label">Vorschlag</div><div id="calSuggestion" class="value">-</div></div>
        </div>
      </article>

      <article class="panel span-12">
        <div class="label">Empfangene APRS-Pakete</div>
        <div class="packet-tools">
          <input id="packetFilter" type="search" placeholder="Rufzeichen filtern, z.B. DL1ABC, DB0, -9">
          <a id="exportXlsx" class="button" href="/export.xlsx">Excel exportieren</a>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Zeit</th>
                <th>Quelle</th>
                <th>Ziel</th>
                <th>Pfad</th>
                <th>Typ</th>
                <th>GPS</th>
                <th>Kommentar</th>
                <th>Rohpaket</th>
              </tr>
            </thead>
            <tbody id="packetRows"></tbody>
          </table>
        </div>
      </article>

      <article class="panel span-12">
        <div class="label">Dire-Wolf-Journal</div>
        <pre id="logs">lade Logs...</pre>
      </article>
    </section>

    <section id="mapView" class="map-view view" role="tabpanel" aria-labelledby="mapTab" hidden>
      <div class="map-toolbar">
        <div class="period-tabs" role="group" aria-label="Zeitraum">
          <button type="button" data-map-hours="1" aria-pressed="false">1 h</button>
          <button type="button" data-map-hours="24" aria-pressed="true">24 h</button>
          <button type="button" data-map-hours="168" aria-pressed="false">7 d</button>
          <button type="button" data-map-hours="0" aria-pressed="false">Alle</button>
        </div>
        <input id="mapFilter" type="search" placeholder="Rufzeichen filtern">
        <select id="receptionFilter" aria-label="Empfangsart">
          <option value="all">Alle Empfangsarten</option>
          <option value="direct">Direkt empfangen</option>
          <option value="digipeated">Via Digipeater</option>
        </select>
        <label class="track-toggle"><input id="showTrack" type="checkbox" checked> Verlauf anzeigen</label>
      </div>
      <div class="map-stats" aria-live="polite">
        <div class="map-stat"><div class="label">Stationen</div><div id="mapStationCount" class="map-stat-value">-</div></div>
        <div class="map-stat"><div class="label">Positionspakete</div><div id="mapPacketCount" class="map-stat-value">-</div></div>
        <div class="map-stat"><div class="label">Direkt / Digi</div><div id="mapReceptionCount" class="map-stat-value">-</div></div>
        <div class="map-stat"><div class="label">Weiteste Position</div><div id="mapMaxDistance" class="map-stat-value">-</div></div>
      </div>
      <div class="map-layout">
        <div id="stationMap" aria-label="Karte der empfangenen APRS-Stationen"></div>
        <aside class="station-rail" aria-label="Empfangene Stationen">
          <div class="station-rail-head"><span>Station</span><span>Distanz</span></div>
          <div id="stationList" class="station-list"><div class="map-message">Kartendaten werden geladen...</div></div>
        </aside>
      </div>
      <div id="mapUpdated" class="small">Noch nicht geladen</div>
    </section>

    <section id="statusView" class="status-view view" role="tabpanel" aria-labelledby="statusTab" hidden>
      <div class="status-header">
        <h2>Systemstatus</h2>
        <div id="statusUpdated" class="small">Noch nicht geladen</div>
      </div>
      <div id="statusGroups" class="status-grid"></div>
    </section>

    <footer id="updated">Noch nicht aktualisiert</footer>
  </main>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    const els = {
      service: document.getElementById("service"),
      serviceDetail: document.getElementById("serviceDetail"),
      aprsis: document.getElementById("aprsis"),
      server: document.getElementById("server"),
      sdr: document.getElementById("sdr"),
      usb: document.getElementById("usb"),
      temp: document.getElementById("temp"),
      uptime: document.getElementById("uptime"),
      packetCount: document.getElementById("packetCount"),
      packetDetail: document.getElementById("packetDetail"),
      packetFilter: document.getElementById("packetFilter"),
      packetRows: document.getElementById("packetRows"),
      exportXlsx: document.getElementById("exportXlsx"),
      call: document.getElementById("call"),
      freq: document.getElementById("freq"),
      position: document.getElementById("position"),
      beacon: document.getElementById("beacon"),
      events: document.getElementById("events"),
      logs: document.getElementById("logs"),
      updated: document.getElementById("updated"),
      heartbeat: document.getElementById("heartbeat"),
      overviewTab: document.getElementById("overviewTab"),
      mapTab: document.getElementById("mapTab"),
      statusTab: document.getElementById("statusTab"),
      overviewView: document.getElementById("overviewView"),
      mapView: document.getElementById("mapView"),
      statusView: document.getElementById("statusView"),
      statusGroups: document.getElementById("statusGroups"),
      statusUpdated: document.getElementById("statusUpdated"),
      mapFilter: document.getElementById("mapFilter"),
      receptionFilter: document.getElementById("receptionFilter"),
      showTrack: document.getElementById("showTrack"),
      stationList: document.getElementById("stationList"),
      mapUpdated: document.getElementById("mapUpdated"),
      mapStationCount: document.getElementById("mapStationCount"),
      mapPacketCount: document.getElementById("mapPacketCount"),
      mapReceptionCount: document.getElementById("mapReceptionCount"),
      mapMaxDistance: document.getElementById("mapMaxDistance"),
      stationIdentity: document.getElementById("stationIdentity"),
      aprsFiLink: document.getElementById("aprsFiLink")
    };

    const cal = {
      freq: document.getElementById("calFreq"),
      ppm: document.getElementById("calPpm"),
      gain: document.getElementById("calGain"),
      span: document.getElementById("calSpan"),
      measure: document.getElementById("measureCalibration"),
      apply: document.getElementById("applyCalibration"),
      status: document.getElementById("calibrationStatus"),
      current: document.getElementById("calCurrent"),
      peak: document.getElementById("calPeak"),
      offset: document.getElementById("calOffset"),
      suggestion: document.getElementById("calSuggestion")
    };

    let pulse = 0;
    let packetCache = [];
    let lastMeasurement = null;
    let activeView = "overview";
    let diagnosticsLoading = false;
    let mapLoading = false;
    let mapHours = 24;
    let mapData = null;
    let stationMap = null;
    let stationLayer = null;
    let gatewayLayer = null;
    let trackLayer = null;
    let stationMarkers = new Map();
    let selectedStation = "";
    let mapHasFitted = false;
    let mapFilterTimer = null;

    function setClass(el, cls) {
      el.classList.remove("ok", "warn", "bad", "blue", "cyan");
      if (cls) el.classList.add(cls);
    }

    function text(value, fallback = "-") {
      return value === null || value === undefined || value === "" ? fallback : value;
    }

    function formatBytes(value) {
      if (value === null || value === undefined || value === "") return "-";
      const bytes = Number(value);
      if (!Number.isFinite(bytes)) return "-";
      const units = ["B", "KiB", "MiB", "GiB", "TiB"];
      let amount = bytes;
      let unit = 0;
      while (Math.abs(amount) >= 1024 && unit < units.length - 1) {
        amount /= 1024;
        unit += 1;
      }
      return `${amount.toFixed(unit ? 1 : 0)} ${units[unit]}`;
    }

    function statusGroup(title, rows, wide = false) {
      const section = document.createElement("section");
      section.className = "status-group" + (wide ? " wide" : "");
      const heading = document.createElement("h3");
      heading.textContent = title;
      const body = document.createElement("div");
      body.className = "status-kv";
      for (const row of rows) {
        const line = document.createElement("div");
        line.className = "status-row";
        const key = document.createElement("div");
        key.className = "status-key";
        key.textContent = row[0];
        const value = document.createElement("div");
        value.className = "status-value" + (row[2] ? ` ${row[2]}` : "");
        value.textContent = text(row[1]);
        line.append(key, value);
        body.appendChild(line);
      }
      section.append(heading, body);
      els.statusGroups.appendChild(section);
    }

    function statusTable(title, columns, rows) {
      const section = document.createElement("section");
      section.className = "status-group wide";
      const heading = document.createElement("h3");
      heading.textContent = title;
      const wrap = document.createElement("div");
      wrap.className = "status-table-wrap";
      const table = document.createElement("table");
      table.className = "status-table";
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      for (const column of columns) {
        const th = document.createElement("th");
        th.textContent = column;
        headerRow.appendChild(th);
      }
      thead.appendChild(headerRow);
      const tbody = document.createElement("tbody");
      for (const row of rows) {
        const tr = document.createElement("tr");
        for (const value of row) {
          const td = document.createElement("td");
          td.textContent = text(value);
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      table.append(thead, tbody);
      wrap.appendChild(table);
      section.append(heading, wrap);
      els.statusGroups.appendChild(section);
    }

    function renderDiagnostics(data) {
      els.statusGroups.innerHTML = "";
      const system = data.system || {};
      const memory = data.memory || {};
      const disk = data.disk || {};
      const aprsis = data.aprsis || {};
      const sdr = data.sdr || {};
      const config = data.config || {};
      const storage = data.storage || {};

      statusGroup("System", [
        ["Hostname", system.hostname],
        ["Modell", system.model],
        ["Betriebssystem", system.os],
        ["Kernel", system.kernel],
        ["Architektur", system.architecture],
        ["CPU-Kerne", system.cpu_count],
        ["Laufzeit", system.uptime],
        ["Temperatur", system.temperature, system.temp_class]
      ]);
      statusGroup("Versorgung und Last", [
        ["CPU-Last 1 / 5 / 15 min", (system.load || []).join(" / ")],
        ["Core-Spannung", system.core_voltage],
        ["Throttling-Code", system.throttled],
        ["Throttling-Status", (system.throttled_flags || []).join(", ") || "keine Warnung", (system.throttled_flags || []).length ? "warn" : "ok"],
        ["RAM gesamt", formatBytes(memory.total)],
        ["RAM belegt", `${formatBytes(memory.used)} (${text(memory.percent)} %)`],
        ["RAM verfuegbar", formatBytes(memory.available)],
        ["Root-Dateisystem", `${formatBytes(disk.used)} / ${formatBytes(disk.total)} (${text(disk.percent)} %)`],
        ["Root frei", formatBytes(disk.free)]
      ]);
      statusGroup("APRS-IS", [
        ["Zustand", String(aprsis.state || "waiting").toUpperCase(), aprsis.connected ? "ok" : "warn"],
        ["Verbunden", aprsis.connected ? "ja" : "nein"],
        ["Login bestaetigt", aprsis.verified ? "ja" : "nicht mehr im aktuellen Log"],
        ["Konfigurierter Server", aprsis.server],
        ["Aktive Gegenstelle", aprsis.endpoint],
        ["Port", config.igate_port]
      ]);
      statusGroup("SDR und Paketspeicher", [
        ["RTL-SDR", sdr.present ? "vorhanden" : "nicht gefunden", sdr.present ? "ok" : "bad"],
        ["USB-Geraet", sdr.description],
        ["PPM-Korrektur", sdr.ppm],
        ["Gain", sdr.gain === undefined ? "-" : `${sdr.gain} dB`],
        ["Paketdatei", storage.packet_store],
        ["Gespeicherte Pakete", `${text(storage.packet_count)} / ${text(storage.packet_limit)}`],
        ["Dateigroesse", formatBytes(storage.packet_store_bytes)],
        ["Dashboard-Port", storage.dashboard_port]
      ]);
      statusGroup("Dire-Wolf-Konfiguration", [
        ["Rufzeichen", config.callsign],
        ["Frequenz", config.frequency],
        ["Position", config.position],
        ["Beacon", config.beacon],
        ["IGate-Server", config.igate_server],
        ["IGate-Port", config.igate_port]
      ], true);

      statusTable("systemd-Dienste", ["Dienst", "Load", "Aktiv", "Substate", "PID", "Restarts", "RAM", "CPU", "Gestartet"],
        (data.services || []).map(service => [
          service.unit, service.load_state, service.active_state, service.sub_state,
          service.pid, service.restarts, formatBytes(service.memory_bytes),
          service.cpu_seconds === null ? "-" : `${service.cpu_seconds.toFixed(1)} s`, service.started
        ])
      );
      statusTable("Netzwerkschnittstellen", ["Interface", "Typ", "Status", "Verbindung", "MAC", "IPv4", "IPv6", "Treiber", "SSID", "Signal", "Rate", "Power Save"],
        ((data.network || {}).interfaces || []).map(iface => [
          iface.name, iface.type, iface.state, iface.connection, iface.mac,
          (iface.ipv4 || []).join(", "), (iface.ipv6 || []).join(", "), iface.driver,
          iface.ssid, iface.signal_dbm ? `${iface.signal_dbm} dBm` : "-", iface.tx_bitrate,
          iface.power_save
        ])
      );
      statusTable("IP-Routen", ["Ziel", "Gateway", "Interface", "Quelle", "Metrik", "Protokoll"],
        ((data.network || {}).routes || []).map(route => [
          route.destination, route.gateway, route.device, route.source, route.metric, route.protocol
        ])
      );
      statusGroup("USB-Geraete", [["lsusb", ((data.usb || {}).devices || []).join("\n")]], true);
      statusGroup("USB-Topologie", [["lsusb -t", ((data.usb || {}).topology || []).join("\n")]], true);
      els.statusUpdated.textContent = "Aktualisiert: " + new Date(data.generated_at).toLocaleString();
    }

    async function loadDiagnostics() {
      if (diagnosticsLoading) return;
      diagnosticsLoading = true;
      if (!els.statusGroups.childElementCount) {
        els.statusUpdated.textContent = "Status wird geladen...";
      }
      setClass(els.statusUpdated, "");
      try {
        const response = await fetch("/api/diagnostics", {cache: "no-store"});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        renderDiagnostics(await response.json());
      } catch (error) {
        els.statusUpdated.textContent = "Fehler: " + error.message;
        setClass(els.statusUpdated, "bad");
      } finally {
        diagnosticsLoading = false;
      }
    }

    function initializeStationMap() {
      if (stationMap) return true;
      if (typeof L === "undefined") {
        els.stationList.innerHTML = "";
        const message = document.createElement("div");
        message.className = "map-message bad";
        message.textContent = "Kartenbibliothek konnte nicht geladen werden.";
        els.stationList.appendChild(message);
        return false;
      }

      stationMap = L.map("stationMap", {preferCanvas: true, zoomControl: true}).setView([20, 0], 2);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).addTo(stationMap);
      stationLayer = L.layerGroup().addTo(stationMap);
      gatewayLayer = L.layerGroup().addTo(stationMap);
      trackLayer = L.layerGroup().addTo(stationMap);

      const legend = L.control({position: "bottomleft"});
      legend.onAdd = () => {
        const container = L.DomUtil.create("div", "map-legend");
        const entries = [
          ["direct", "Direkt"],
          ["digipeated", "Digipeater"],
          ["track", "Position"],
          ["gateway", "Gateway"]
        ];
        for (const entry of entries) {
          const item = document.createElement("span");
          const dot = document.createElement("i");
          dot.className = "legend-dot " + entry[0];
          const label = document.createElement("b");
          label.textContent = entry[1];
          item.append(dot, label);
          container.appendChild(item);
        }
        L.DomEvent.disableClickPropagation(container);
        return container;
      };
      legend.addTo(stationMap);
      return true;
    }

    function popupRow(label, value) {
      const row = document.createElement("div");
      row.className = "popup-row";
      const key = document.createElement("div");
      key.className = "popup-key";
      key.textContent = label;
      const item = document.createElement("div");
      item.textContent = text(value);
      row.append(key, item);
      return row;
    }

    function stationPopup(properties) {
      const popup = document.createElement("div");
      const callsign = document.createElement("div");
      callsign.className = "popup-call";
      callsign.textContent = properties.callsign;
      popup.appendChild(callsign);
      const reception = properties.reception === "direct" ? "direkt" : "via Digipeater";
      const distance = properties.distance_km === null ? "-" : `${properties.distance_km.toFixed(1)} km / ${properties.bearing} deg`;
      popup.append(
        popupRow("Empfang", reception),
        popupRow("Zuletzt", properties.last_heard_local),
        popupRow("Entfernung", distance),
        popupRow("Pakete", properties.packet_count),
        popupRow("Direkt / Digi", `${properties.direct_count} / ${properties.digipeated_count}`),
        popupRow("Pfad", properties.path || "direkt"),
        popupRow("Kommentar", properties.comment)
      );
      return popup;
    }

    function trackPointPopup(callsign, point) {
      const popup = document.createElement("div");
      const title = document.createElement("div");
      title.className = "popup-call";
      title.textContent = callsign;
      popup.appendChild(title);
      const reception = point.reception === "direct" ? "direkt" : "via Digipeater";
      popup.append(
        popupRow("Empfang", reception),
        popupRow("Gehoert", point.time_local || point.time),
        popupRow("Position", `${Number(point.latitude).toFixed(5)}, ${Number(point.longitude).toFixed(5)}`)
      );
      return popup;
    }

    function sameCoordinatePair(left, right) {
      return Math.abs(Number(left[0]) - Number(right[0])) < 0.000001
        && Math.abs(Number(left[1]) - Number(right[1])) < 0.000001;
    }

    function drawSelectedTrack() {
      if (!trackLayer) return;
      trackLayer.clearLayers();
      if (!selectedStation || !els.showTrack.checked || !mapData) return;
      const points = (mapData.tracks[selectedStation] || []).map(point => [point.latitude, point.longitude]);
      if (points.length < 2) return;
      L.polyline(points, {
        color: "#7ef3e2",
        weight: 3,
        opacity: .8,
        dashArray: "5 7"
      }).addTo(trackLayer);
    }

    function selectStation(callsign, focus = false) {
      selectedStation = callsign;
      for (const item of els.stationList.querySelectorAll(".station-item")) {
        item.classList.toggle("active", item.dataset.callsign === callsign);
      }
      drawSelectedTrack();
      const marker = stationMarkers.get(callsign);
      if (focus && marker) {
        stationMap.panTo(marker.getLatLng());
        marker.openPopup();
      }
    }

    function visibleMapFeatures() {
      if (!mapData) return [];
      const reception = els.receptionFilter.value;
      return mapData.stations.features.filter(feature =>
        reception === "all" || feature.properties.reception === reception
      );
    }

    function renderStationMap(fitBounds = false) {
      if (!mapData || !initializeStationMap()) return;
      stationLayer.clearLayers();
      gatewayLayer.clearLayers();
      trackLayer.clearLayers();
      stationMarkers = new Map();
      els.stationList.innerHTML = "";

      const features = visibleMapFeatures().sort((left, right) =>
        String(right.properties.last_heard).localeCompare(String(left.properties.last_heard))
      );
      const bounds = [];
      const gateway = mapData.gateway || {};
      if (gateway.latitude !== null && gateway.longitude !== null) {
        const position = [gateway.latitude, gateway.longitude];
        bounds.push(position);
        L.circleMarker(position, {
          radius: 9,
          color: "#d7e1ea",
          weight: 2,
          fillColor: "#6ab7ff",
          fillOpacity: .95
        }).bindTooltip(gateway.callsign || "Gateway", {direction: "top"}).addTo(gatewayLayer);
      }

      let packetCount = 0;
      let directCount = 0;
      let digipeatedCount = 0;
      let maxDistance = null;
      for (const feature of features) {
        const properties = feature.properties;
        const coordinates = feature.geometry.coordinates;
        const position = [coordinates[1], coordinates[0]];
        const direct = properties.reception === "direct";
        packetCount += properties.packet_count;
        directCount += direct ? 1 : 0;
        digipeatedCount += direct ? 0 : 1;
        if (properties.distance_km !== null) {
          maxDistance = maxDistance === null ? properties.distance_km : Math.max(maxDistance, properties.distance_km);
        }
        bounds.push(position);
        for (const point of (mapData.tracks[properties.callsign] || [])) {
          const pointCoordinates = [point.longitude, point.latitude];
          if (sameCoordinatePair(pointCoordinates, coordinates)) continue;
          const trackPosition = [point.latitude, point.longitude];
          const trackDirect = point.reception === "direct";
          bounds.push(trackPosition);
          L.circleMarker(trackPosition, {
            radius: 4,
            color: "#081018",
            weight: 1,
            fillColor: trackDirect ? "#7ef3e2" : "#f2bf4d",
            fillOpacity: .55
          }).bindTooltip(properties.callsign, {direction: "top"}).bindPopup(trackPointPopup(properties.callsign, point)).addTo(stationLayer);
        }
        const marker = L.circleMarker(position, {
          radius: 7,
          color: "#081018",
          weight: 2,
          fillColor: direct ? "#7ef3e2" : "#f2bf4d",
          fillOpacity: .95
        }).bindTooltip(properties.callsign, {direction: "top"}).bindPopup(stationPopup(properties));
        marker.on("click", () => selectStation(properties.callsign));
        marker.addTo(stationLayer);
        stationMarkers.set(properties.callsign, marker);

        const button = document.createElement("button");
        button.type = "button";
        button.className = "station-item";
        button.dataset.callsign = properties.callsign;
        const dot = document.createElement("span");
        dot.className = "station-dot" + (direct ? "" : " digipeated");
        const details = document.createElement("span");
        const call = document.createElement("span");
        call.className = "station-call";
        call.textContent = properties.callsign;
        const heard = document.createElement("span");
        heard.className = "station-meta";
        heard.textContent = `${properties.last_heard_local || "-"} / ${properties.packet_count} Pakete`;
        details.append(call, heard);
        const distance = document.createElement("span");
        distance.className = "station-distance";
        distance.textContent = properties.distance_km === null ? "-" : `${properties.distance_km.toFixed(1)} km`;
        button.append(dot, details, distance);
        button.addEventListener("click", () => selectStation(properties.callsign, true));
        els.stationList.appendChild(button);
      }

      if (!features.length) {
        const message = document.createElement("div");
        message.className = "map-message";
        message.textContent = "Keine Stationspositionen fuer diesen Filter gefunden.";
        els.stationList.appendChild(message);
      }
      els.mapStationCount.textContent = String(features.length);
      els.mapPacketCount.textContent = String(packetCount);
      els.mapReceptionCount.textContent = `${directCount} / ${digipeatedCount}`;
      els.mapMaxDistance.textContent = maxDistance === null ? "-" : `${maxDistance.toFixed(1)} km`;

      if (selectedStation && stationMarkers.has(selectedStation)) {
        selectStation(selectedStation);
      } else {
        selectedStation = "";
      }
      if ((fitBounds || !mapHasFitted) && bounds.length) {
        stationMap.fitBounds(bounds, {padding: [28, 28], maxZoom: 13});
        mapHasFitted = true;
      }
    }

    async function loadMapData(fitBounds = false) {
      if (mapLoading) return;
      mapLoading = true;
      if (!mapData) els.mapUpdated.textContent = "Kartendaten werden geladen...";
      setClass(els.mapUpdated, "");
      try {
        const query = new URLSearchParams({hours: String(mapHours)});
        const filter = els.mapFilter.value.trim();
        if (filter) query.set("filter", filter);
        const response = await fetch("/api/map?" + query.toString(), {cache: "no-store"});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        mapData = await response.json();
        renderStationMap(fitBounds);
        els.mapUpdated.textContent = "Aktualisiert: " + new Date(mapData.generated_at).toLocaleString();
      } catch (error) {
        els.mapUpdated.textContent = "Fehler: " + error.message;
        setClass(els.mapUpdated, "bad");
      } finally {
        mapLoading = false;
      }
    }

    function selectView(view) {
      activeView = view;
      els.overviewView.hidden = view !== "overview";
      els.mapView.hidden = view !== "map";
      els.statusView.hidden = view !== "status";
      els.overviewTab.setAttribute("aria-selected", String(view === "overview"));
      els.mapTab.setAttribute("aria-selected", String(view === "map"));
      els.statusTab.setAttribute("aria-selected", String(view === "status"));
      if (view === "map") {
        initializeStationMap();
        setTimeout(() => stationMap && stationMap.invalidateSize(), 0);
        loadMapData(!mapHasFitted);
      }
      if (view === "status") loadDiagnostics();
    }

    function matchesPacket(packet, filter) {
      if (!filter) return true;
      const needle = filter.toUpperCase();
      return [packet.source, packet.destination, packet.path, packet.raw].some(value =>
        String(value || "").toUpperCase().includes(needle)
      );
    }

    function renderPackets() {
      const filter = els.packetFilter.value.trim();
      const packets = packetCache.filter(packet => matchesPacket(packet, filter));
      els.packetRows.innerHTML = "";
      els.packetCount.textContent = String(packets.length);
      els.packetDetail.textContent = packetCache.length
        ? `${packetCache.length} im Journal, ${packets.length} sichtbar`
        : "noch keine decodierten Pakete im Journal";
      els.exportXlsx.href = "/export.xlsx" + (filter ? "?filter=" + encodeURIComponent(filter) : "");

      if (!packets.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 8;
        td.textContent = "Keine passenden Pakete gefunden.";
        tr.appendChild(td);
        els.packetRows.appendChild(tr);
        return;
      }

      for (const packet of packets.slice(0, 120)) {
        const tr = document.createElement("tr");
        const cells = [
          packet.time_local,
          packet.source,
          packet.destination,
          packet.path || "-",
          packet.kind,
          packet.latitude !== null && packet.longitude !== null
            ? `${packet.latitude.toFixed(5)}, ${packet.longitude.toFixed(5)}`
            : "-",
          packet.comment || "-",
          packet.raw
        ];
        cells.forEach((value, index) => {
          const td = document.createElement("td");
          if (index === 7) td.className = "raw";
          td.textContent = value;
          tr.appendChild(td);
        });
        els.packetRows.appendChild(tr);
      }
    }

    function renderCalibration(data) {
      if (!data) return;
      cal.ppm.value = data.ppm;
      cal.gain.value = data.gain;
      cal.current.textContent = `${data.ppm} ppm / ${data.gain} dB`;
      if (data.last_measurement) {
        lastMeasurement = data.last_measurement;
        renderMeasurement(lastMeasurement);
      }
    }

    function renderMeasurement(result) {
      cal.peak.textContent = `${result.measured_mhz.toFixed(6)} MHz / ${result.power_db.toFixed(1)} dB`;
      cal.offset.textContent = `${Math.round(result.offset_hz)} Hz`;
      cal.suggestion.textContent = `${result.suggested_ppm} ppm`;
    }

    function formBody(values) {
      return new URLSearchParams(values).toString();
    }

    async function postCalibration(path, values) {
      const response = await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: formBody(values)
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Kalibrierung fehlgeschlagen");
      return payload;
    }

    async function loadCalibration() {
      try {
        const response = await fetch("/api/calibration", {cache: "no-store"});
        renderCalibration(await response.json());
      } catch (error) {
        cal.status.textContent = error.message;
        setClass(cal.status, "bad");
      }
    }

    async function measureCalibration() {
      cal.measure.disabled = true;
      cal.status.textContent = "Messung laeuft: PTT gedrueckt halten. Dire Wolf wird kurz gestoppt, rtl_power misst den staerksten Peak.";
      setClass(cal.status, "warn");
      try {
        const result = await postCalibration("/api/calibration/measure", {
          frequency_mhz: cal.freq.value,
          ppm: cal.ppm.value,
          gain: cal.gain.value,
          span_khz: cal.span.value
        });
        lastMeasurement = result;
        renderMeasurement(result);
        cal.ppm.value = result.suggested_ppm;
        cal.status.textContent = "Messung fertig. Wenn der Peak vom eigenen kurzen Testsignal stammt, Vorschlag speichern.";
        setClass(cal.status, "ok");
      } catch (error) {
        cal.status.textContent = error.message;
        setClass(cal.status, "bad");
      } finally {
        cal.measure.disabled = false;
      }
    }

    async function applyCalibration() {
      cal.apply.disabled = true;
      cal.status.textContent = "Speichere SDR-Werte und starte Dire Wolf neu.";
      setClass(cal.status, "warn");
      try {
        if (lastMeasurement) {
          cal.ppm.value = lastMeasurement.suggested_ppm;
        }
        const result = await postCalibration("/api/calibration/apply", {
          ppm: cal.ppm.value,
          gain: cal.gain.value
        });
        renderCalibration(result);
        cal.status.textContent = "SDR-Werte gespeichert und Dienst neu gestartet.";
        setClass(cal.status, "ok");
        await loadStatus();
      } catch (error) {
        cal.status.textContent = error.message;
        setClass(cal.status, "bad");
      } finally {
        cal.apply.disabled = false;
      }
    }

    async function loadStatus() {
      try {
        const res = await fetch("/api/status", { cache: "no-store" });
        const data = await res.json();

        els.service.textContent = data.service.active ? "RUNNING" : "DOWN";
        setClass(els.service, data.service.active ? "ok" : "bad");
        els.serviceDetail.textContent = data.service.detail || data.service.state;

        const aprsisState = data.aprsis.state || (data.aprsis.verified ? "verified" : "waiting");
        const aprsisLabels = {
          verified: "VERIFIED",
          connected: "CONNECTED",
          waiting: "WAITING",
        };
        els.aprsis.textContent = aprsisLabels[aprsisState] || aprsisState.toUpperCase();
        setClass(els.aprsis, aprsisState === "waiting" ? "warn" : "ok");
        const serverParts = [data.aprsis.server, data.aprsis.endpoint].filter(Boolean);
        els.server.textContent = serverParts.join(" · ") || "keine aktive APRS-IS-Verbindung";

        els.sdr.textContent = data.sdr.present ? "ONLINE" : "MISSING";
        setClass(els.sdr, data.sdr.present ? "ok" : "bad");
        els.usb.textContent = data.sdr.description || "kein RTL-SDR gefunden";

        els.temp.textContent = data.system.temperature || "-";
        setClass(els.temp, data.system.temp_class || "");
        els.uptime.textContent = data.system.uptime || "-";
        packetCache = data.packets || [];
        renderPackets();

        els.call.textContent = text(data.config.callsign);
        els.freq.textContent = text(data.config.frequency);
        els.position.textContent = text(data.config.position);
        els.beacon.textContent = text(data.config.beacon);
        const callsign = data.config.callsign || "Configured station";
        els.stationIdentity.textContent = `${callsign} / RTL-SDR / Dire Wolf / ${text(data.config.frequency, "APRS")}`;
        els.aprsFiLink.href = data.config.callsign
          ? `https://aprs.fi/${encodeURIComponent(data.config.callsign)}`
          : "https://aprs.fi/";

        els.events.innerHTML = "";
        const events = data.events.length ? data.events : ["Keine aktuellen Dire-Wolf-Ereignisse im Journal."];
        for (const item of events.slice(0, 8)) {
          const div = document.createElement("div");
          div.className = "event";
          div.textContent = item;
          els.events.appendChild(div);
        }

        els.logs.textContent = data.logs.join("\n");
        renderCalibration(data.calibration);
        els.updated.textContent = "Aktualisiert: " + new Date(data.generated_at).toLocaleString();
        pulse = (pulse + 18) % 100;
        els.heartbeat.style.width = (data.service.active ? 55 + pulse / 3 : 8) + "%";
      } catch (err) {
        els.service.textContent = "ERROR";
        setClass(els.service, "bad");
        els.serviceDetail.textContent = err.message;
      }
    }

    document.getElementById("refresh").addEventListener("click", () => {
      if (activeView === "status") loadDiagnostics();
      else if (activeView === "map") loadMapData(false);
      else loadStatus();
    });
    els.overviewTab.addEventListener("click", () => selectView("overview"));
    els.mapTab.addEventListener("click", () => selectView("map"));
    els.statusTab.addEventListener("click", () => selectView("status"));
    document.querySelectorAll("[data-map-hours]").forEach(button => {
      button.addEventListener("click", () => {
        mapHours = Number(button.dataset.mapHours);
        document.querySelectorAll("[data-map-hours]").forEach(item =>
          item.setAttribute("aria-pressed", String(item === button))
        );
        loadMapData(true);
      });
    });
    els.mapFilter.addEventListener("input", () => {
      clearTimeout(mapFilterTimer);
      mapFilterTimer = setTimeout(() => loadMapData(true), 350);
    });
    els.receptionFilter.addEventListener("change", () => renderStationMap(true));
    els.showTrack.addEventListener("change", drawSelectedTrack);
    cal.measure.addEventListener("click", measureCalibration);
    cal.apply.addEventListener("click", applyCalibration);
    els.packetFilter.addEventListener("input", renderPackets);
    loadCalibration();
    loadStatus();
    setInterval(() => {
      if (activeView === "overview") loadStatus();
    }, 5000);
    setInterval(() => {
      if (activeView === "status") loadDiagnostics();
    }, 15000);
    setInterval(() => {
      if (activeView === "map") loadMapData(false);
    }, 30000);
  </script>
</body>
</html>
"""


def run_command(args, timeout=4):
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return "", str(exc), 255
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def helper_payload(args, timeout=30):
    stdout, stderr, code = run_command(["sudo", "-n", SDR_HELPER, *args], timeout=timeout)
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"error": stdout}
    else:
        payload = {}
    if code != 0:
        raise RuntimeError(payload.get("error") or stderr or "SDR helper failed")
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload


def calibration_status():
    try:
        return helper_payload(["status"], timeout=5)
    except Exception as exc:
        return {"ppm": 0, "gain": 35, "error": str(exc)}


def validate_float(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def service_status():
    active, _, _ = run_command(["systemctl", "is-active", SERVICE])
    state, _, _ = run_command(["systemctl", "show", SERVICE, "--property=SubState", "--value"])
    detail, _, _ = run_command(["systemctl", "show", SERVICE, "--property=ExecMainPID", "--value"])
    return {
        "active": active == "active",
        "state": active or "unknown",
        "detail": f"substate={state or 'unknown'}, pid={detail or '-'}",
    }


def journal_lines(count=120):
    stdout, _, _ = run_command(
        ["journalctl", "-u", SERVICE, "-n", str(count), "--no-pager", "-o", "short-iso"],
        timeout=5,
    )
    return [line for line in stdout.splitlines() if line.strip()]


def packet_journal_lines(count=1200):
    stdout, _, _ = run_command(
        ["journalctl", "-u", SERVICE, "-n", str(count), "--no-pager", "-o", "short-iso"],
        timeout=7,
    )
    return [line for line in stdout.splitlines() if line.strip()]


def sdr_status():
    stdout, _, _ = run_command(["lsusb"], timeout=3)
    rtl_lines = [
        line for line in stdout.splitlines()
        if "RTL2838" in line or "RTL2832" in line or "Realtek" in line
    ]
    return {
        "present": bool(rtl_lines),
        "description": rtl_lines[0] if rtl_lines else "",
    }


def system_status():
    uptime, _, _ = run_command(["uptime", "-p"], timeout=3)
    temp_raw = read_file("/sys/class/thermal/thermal_zone0/temp")
    temperature = ""
    temp_class = ""
    if temp_raw.isdigit():
        celsius = int(temp_raw) / 1000
        temperature = f"{celsius:.1f} C"
        temp_class = "ok" if celsius < 65 else "warn" if celsius < 75 else "bad"
    return {
        "uptime": uptime,
        "temperature": temperature,
        "temp_class": temp_class,
    }


def parse_properties(value):
    properties = {}
    for line in value.splitlines():
        key, separator, item = line.partition("=")
        if separator:
            properties[key] = item
    return properties


def integer_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def memory_status():
    values = {}
    for line in read_file("/proc/meminfo").splitlines():
        key, separator, raw = line.partition(":")
        if not separator:
            continue
        match = re.search(r"\d+", raw)
        if match:
            values[key] = int(match.group()) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(0, total - available)
    return {
        "total": total,
        "used": used,
        "available": available,
        "percent": round(used * 100 / total, 1) if total else None,
    }


def disk_status(path="/"):
    try:
        stats = os.statvfs(path)
    except OSError:
        return {"total": 0, "used": 0, "free": 0, "percent": None}
    total = stats.f_blocks * stats.f_frsize
    free = stats.f_bavail * stats.f_frsize
    used = max(0, total - free)
    return {
        "total": total,
        "used": used,
        "free": free,
        "percent": round(used * 100 / total, 1) if total else None,
    }


def decode_throttled(value):
    match = re.search(r"0x([0-9a-fA-F]+)", value or "")
    if not match:
        return []
    flags = int(match.group(1), 16)
    meanings = (
        (0, "Unterspannung aktuell"),
        (1, "CPU-Takt aktuell begrenzt"),
        (2, "Throttling aktuell"),
        (3, "Temperaturlimit aktuell"),
        (16, "Unterspannung seit Start"),
        (17, "CPU-Takt seit Start begrenzt"),
        (18, "Throttling seit Start"),
        (19, "Temperaturlimit seit Start"),
    )
    return [label for bit, label in meanings if flags & (1 << bit)]


def os_description():
    properties = parse_properties(read_file("/etc/os-release"))
    return properties.get("PRETTY_NAME", "").strip('"')


def system_diagnostics():
    summary = system_status()
    hostname, _, _ = run_command(["hostname"], timeout=2)
    kernel, _, _ = run_command(["uname", "-sr"], timeout=2)
    architecture, _, _ = run_command(["uname", "-m"], timeout=2)
    voltage, _, _ = run_command(["vcgencmd", "measure_volts", "core"], timeout=2)
    throttled, _, _ = run_command(["vcgencmd", "get_throttled"], timeout=2)
    load_parts = read_file("/proc/loadavg").split()
    return {
        **summary,
        "hostname": hostname,
        "model": read_file("/sys/firmware/devicetree/base/model").rstrip("\x00"),
        "os": os_description(),
        "kernel": kernel,
        "architecture": architecture,
        "cpu_count": os.cpu_count(),
        "load": load_parts[:3],
        "core_voltage": voltage.partition("=")[2] or voltage,
        "throttled": throttled.partition("=")[2] or throttled or "unbekannt",
        "throttled_flags": decode_throttled(throttled),
    }


def service_diagnostics(unit):
    properties = (
        "LoadState,ActiveState,SubState,MainPID,NRestarts,MemoryCurrent,"
        "CPUUsageNSec,ExecMainStartTimestamp"
    )
    stdout, _, _ = run_command(
        ["systemctl", "show", unit, f"--property={properties}", "--no-pager"],
        timeout=4,
    )
    values = parse_properties(stdout)
    cpu_ns = integer_or_none(values.get("CPUUsageNSec"))
    return {
        "unit": unit,
        "load_state": values.get("LoadState", "unknown"),
        "active_state": values.get("ActiveState", "unknown"),
        "sub_state": values.get("SubState", "unknown"),
        "pid": integer_or_none(values.get("MainPID")),
        "restarts": integer_or_none(values.get("NRestarts")),
        "memory_bytes": integer_or_none(values.get("MemoryCurrent")),
        "cpu_seconds": round(cpu_ns / 1_000_000_000, 3) if cpu_ns is not None else None,
        "started": values.get("ExecMainStartTimestamp", ""),
    }


def split_nmcli_line(line):
    fields = []
    current = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def parse_nmcli_devices(value):
    devices = {}
    for line in value.splitlines():
        fields = split_nmcli_line(line)
        if len(fields) < 4:
            continue
        devices[fields[0]] = {
            "type": fields[1],
            "state": fields[2],
            "connection": ":".join(fields[3:]),
        }
    return devices


def parse_iw_link(value):
    data = {"ssid": "", "signal_dbm": "", "tx_bitrate": "", "frequency": ""}
    patterns = {
        "ssid": r"^\s*SSID:\s*(.+)$",
        "signal_dbm": r"^\s*signal:\s*(-?[0-9.]+)\s*dBm",
        "tx_bitrate": r"^\s*tx bitrate:\s*(.+)$",
        "frequency": r"^\s*freq:\s*(.+)$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, value, re.MULTILINE | re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()
    return data


def network_diagnostics():
    nmcli_output, _, _ = run_command(
        ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
        timeout=5,
    )
    nmcli_devices = parse_nmcli_devices(nmcli_output)
    address_output, _, _ = run_command(["ip", "-j", "address", "show"], timeout=4)
    try:
        address_data = json.loads(address_output)
    except (TypeError, json.JSONDecodeError):
        address_data = []

    interfaces = []
    for item in address_data:
        name = item.get("ifname", "")
        nmcli = nmcli_devices.get(name, {})
        addresses = item.get("addr_info", [])
        driver_path = os.path.realpath(f"/sys/class/net/{name}/device/driver")
        driver = os.path.basename(driver_path) if os.path.exists(driver_path) else ""
        link = {}
        power_save = ""
        if nmcli.get("type") == "wifi" or name.startswith("wlan"):
            iw_output, _, _ = run_command(["iw", "dev", name, "link"], timeout=3)
            link = parse_iw_link(iw_output)
            power_output, _, _ = run_command(["iw", "dev", name, "get", "power_save"], timeout=3)
            power_save = power_output.partition(":")[2].strip() or power_output
        interfaces.append({
            "name": name,
            "type": nmcli.get("type", item.get("link_type", "")),
            "state": nmcli.get("state", item.get("operstate", "")),
            "connection": nmcli.get("connection", ""),
            "mac": item.get("address", ""),
            "mtu": item.get("mtu"),
            "ipv4": [
                f'{address.get("local")}/{address.get("prefixlen")}'
                for address in addresses if address.get("family") == "inet"
            ],
            "ipv6": [
                f'{address.get("local")}/{address.get("prefixlen")}'
                for address in addresses if address.get("family") == "inet6"
            ],
            "driver": driver,
            **link,
            "power_save": power_save,
        })

    route_output, _, _ = run_command(["ip", "-j", "route", "show"], timeout=4)
    try:
        route_data = json.loads(route_output)
    except (TypeError, json.JSONDecodeError):
        route_data = []
    routes = [{
        "destination": route.get("dst", "default"),
        "gateway": route.get("gateway", ""),
        "device": route.get("dev", ""),
        "source": route.get("prefsrc", ""),
        "metric": route.get("metric", ""),
        "protocol": route.get("protocol", ""),
    } for route in route_data]
    return {"interfaces": interfaces, "routes": routes}


def usb_diagnostics():
    devices, _, _ = run_command(["lsusb"], timeout=4)
    topology, _, _ = run_command(["lsusb", "-t"], timeout=4)
    return {
        "devices": [line for line in devices.splitlines() if line.strip()],
        "topology": [line for line in topology.splitlines() if line.strip()],
    }


def packet_store_count():
    count = 0
    try:
        with open(PACKET_STORE, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                count += chunk.count(b"\n")
    except OSError:
        return 0
    return count


def parse_config():
    config = read_file("/etc/direwolf-sdr.conf")
    data = {
        "callsign": "",
        "frequency": "144.800 MHz",
        "position": "",
        "beacon": "",
        "igate_server": "",
        "igate_port": 14580,
    }
    for line in config.splitlines():
        stripped = line.strip()
        if stripped.startswith("MYCALL "):
            data["callsign"] = stripped.split(None, 1)[1]
        elif stripped.startswith("IGSERVER "):
            parts = stripped.split()
            data["igate_server"] = parts[1]
            if len(parts) >= 3 and parts[2].isdigit():
                data["igate_port"] = int(parts[2])
        elif stripped.startswith("PBEACON "):
            lat = re.search(r"\blat=([^ ]+)", stripped)
            lon = re.search(r"\blong=([^ ]+)", stripped)
            comment = re.search(r"\bcomment=([^ ]+)", stripped)
            every = re.search(r"\bevery=([^ ]+)", stripped)
            if lat and lon:
                data["position"] = f"{lat.group(1)} {lon.group(1)}"
            if every:
                data["beacon"] = f"APRS-IS alle {every.group(1)}"
            if comment:
                data["beacon"] = (data["beacon"] + f" / {comment.group(1)}").strip(" /")
    return data


def active_aprsis_socket(port=14580):
    stdout, _, _ = run_command(["ss", "-H", "-tn", "state", "established"], timeout=3)
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        endpoint = fields[-1]
        _, separator, endpoint_port = endpoint.rpartition(":")
        if separator and endpoint_port == str(port):
            return endpoint
    return ""


def parse_aprsis(lines, configured_server="", socket_endpoint=""):
    log_verified = False
    log_server = ""
    for line in lines:
        if "Now connected to IGate server" in line:
            log_server = line.split("Now connected to IGate server", 1)[1].strip()
        if "logresp" in line and "verified" in line:
            log_verified = True
            server_match = re.search(r"server\s+([A-Za-z0-9_-]+)", line)
            if server_match:
                log_server = server_match.group(1)

    connected = bool(socket_endpoint)
    verified = connected and log_verified
    state = "verified" if verified else "connected" if connected else "waiting"
    server = log_server if verified else configured_server or log_server
    return {
        "connected": connected,
        "verified": verified,
        "state": state,
        "server": server,
        "endpoint": socket_endpoint,
    }


def interesting_events(lines):
    patterns = (
        "logresp",
        "Now connected",
        "Config file:",
        "Failed",
        "error",
        "Error",
        "Ready to accept",
        "[ig]",
    )
    events = [line for line in lines if any(pattern in line for pattern in patterns)]
    return events[-12:][::-1]


def syslog_message(line):
    match = re.match(r"^(\S+)\s+\S+\s+[^:]+:\s+(.*)$", line)
    if not match:
        return "", line
    return match.group(1), match.group(2)


def aprs_coordinate_to_decimal(value, direction):
    if direction in ("N", "S"):
        degrees = int(value[:2])
        minutes = float(value[2:])
    else:
        degrees = int(value[:3])
        minutes = float(value[3:])
    decimal = degrees + minutes / 60
    if direction in ("S", "W"):
        decimal *= -1
    return decimal


def parse_position(info):
    candidates = []
    if info[:1] in ("!", "="):
        candidates.append(info[1:])
    if info[:1] in ("/", "@") and len(info) > 8:
        candidates.append(info[8:])
    candidates.append(info)

    for candidate in candidates:
        match = re.search(r"(\d{4}\.\d{2})([NS])(.)(\d{5}\.\d{2})([EW])(.)(.*)", candidate)
        if not match:
            continue
        lat = aprs_coordinate_to_decimal(match.group(1), match.group(2))
        lon = aprs_coordinate_to_decimal(match.group(4), match.group(5))
        return {
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "symbol_table": match.group(3),
            "symbol": match.group(6),
            "comment": match.group(7).strip(),
        }
    return {
        "latitude": None,
        "longitude": None,
        "symbol_table": "",
        "symbol": "",
        "comment": "",
    }


def packet_kind(info, position):
    if position["latitude"] is not None:
        return "position"
    if info.startswith(":"):
        return "message"
    if info.startswith(">"):
        return "status"
    if info.startswith(";"):
        return "object"
    if info.startswith("T#"):
        return "telemetry"
    return "packet"


def normalize_packet_message(message):
    if message.startswith("[ig] "):
        message = message[5:]
    match = re.match(r"^\[[0-9.]+\]\s+(.+)$", message)
    if match:
        message = match.group(1)
    return message


def parse_packets(lines):
    packets = []
    seen = set()
    for line in lines:
        timestamp, message = syslog_message(line)
        message = normalize_packet_message(message)
        if message.startswith("#"):
            continue
        match = re.match(
            r"^([A-Z0-9]{1,6}(?:-\d{1,2})?)>([^:,]+)((?:,[^:]+)*):(.*)$",
            message,
        )
        if not match:
            continue
        raw = message.strip()
        key = (timestamp, raw)
        if key in seen:
            continue
        seen.add(key)
        source = match.group(1)
        destination = match.group(2)
        path = match.group(3).lstrip(",")
        info = match.group(4)
        position = parse_position(info)
        packets.append({
            "time": timestamp,
            "time_local": timestamp.replace("T", " ")[:19] if timestamp else "",
            "source": source,
            "destination": destination,
            "path": path,
            "kind": packet_kind(info, position),
            "latitude": position["latitude"],
            "longitude": position["longitude"],
            "symbol_table": position["symbol_table"],
            "symbol": position["symbol"],
            "comment": position["comment"],
            "info": info,
            "raw": raw,
        })
    return packets[::-1]


def packet_key(packet):
    return (packet.get("time", ""), packet.get("raw", ""))


def read_stored_packets():
    packets = []
    try:
        with open(PACKET_STORE, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    packets.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return packets


def write_stored_packets(packets):
    directory = os.path.dirname(PACKET_STORE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{PACKET_STORE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        for packet in packets[-MAX_STORED_PACKETS:]:
            handle.write(json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp_path, PACKET_STORE)


def stored_packets_with_latest():
    stored = read_stored_packets()
    known = {packet_key(packet) for packet in stored}
    added = False
    latest = parse_packets(packet_journal_lines())
    for packet in reversed(latest):
        key = packet_key(packet)
        if key in known:
            continue
        stored.append(packet)
        known.add(key)
        added = True
    if added:
        write_stored_packets(stored)
    return stored[-MAX_STORED_PACKETS:][::-1]


def filtered_packets(filter_text=""):
    packets = stored_packets_with_latest()
    if not filter_text:
        return packets
    needle = filter_text.upper()
    return [
        packet for packet in packets
        if any(needle in str(packet.get(key, "")).upper() for key in (
            "source", "destination", "path", "raw", "comment"
        ))
    ]


def config_position_decimal(position):
    matches = re.findall(r"(\d{2,3})\D(\d{2}\.\d+)([NSEW])", position or "", re.IGNORECASE)
    coordinates = {}
    for degrees, minutes, direction in matches:
        decimal = int(degrees) + float(minutes) / 60
        direction = direction.upper()
        if direction in ("S", "W"):
            decimal *= -1
        coordinates["latitude" if direction in ("N", "S") else "longitude"] = decimal
    if "latitude" not in coordinates or "longitude" not in coordinates:
        return None, None
    return round(coordinates["latitude"], 6), round(coordinates["longitude"], 6)


def packet_datetime(packet):
    value = str(packet.get("time", "")).strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def distance_and_bearing(latitude, longitude, target_latitude, target_longitude):
    earth_radius_km = 6371.0088
    lat1 = math.radians(latitude)
    lat2 = math.radians(target_latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(target_longitude - longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    distance = earth_radius_km * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    return round(distance, 1), round(bearing)


def packet_is_direct(packet):
    return "*" not in str(packet.get("path", ""))


def map_payload(hours=24, filter_text="", now=None):
    config = parse_config()
    gateway_latitude, gateway_longitude = config_position_decimal(config["position"])
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours) if hours else None
    needle = filter_text.strip().upper()
    stations = {}
    positioned_packets = 0

    for packet in stored_packets_with_latest():
        source = str(packet.get("source", ""))
        if not source or source == config["callsign"]:
            continue
        if needle and needle not in source.upper():
            continue
        latitude = packet.get("latitude")
        longitude = packet.get("longitude")
        if latitude is None or longitude is None:
            continue
        received_at = packet_datetime(packet)
        if cutoff and (received_at is None or received_at < cutoff):
            continue

        positioned_packets += 1
        station = stations.setdefault(source, {
            "latest": packet,
            "packet_count": 0,
            "direct_count": 0,
            "digipeated_count": 0,
            "track": [],
        })
        station["packet_count"] += 1
        if packet_is_direct(packet):
            station["direct_count"] += 1
        else:
            station["digipeated_count"] += 1
        station["track"].append({
            "latitude": latitude,
            "longitude": longitude,
            "time": packet.get("time", ""),
            "time_local": packet.get("time_local", ""),
            "reception": "direct" if packet_is_direct(packet) else "digipeated",
        })

    features = []
    tracks = {}
    max_distance = None
    direct_stations = 0
    digipeated_stations = 0
    for source, station in sorted(stations.items()):
        latest = station["latest"]
        latitude = float(latest["latitude"])
        longitude = float(latest["longitude"])
        is_direct = packet_is_direct(latest)
        if is_direct:
            direct_stations += 1
        else:
            digipeated_stations += 1
        distance_km = None
        bearing = None
        if gateway_latitude is not None and gateway_longitude is not None:
            distance_km, bearing = distance_and_bearing(
                gateway_latitude,
                gateway_longitude,
                latitude,
                longitude,
            )
            max_distance = distance_km if max_distance is None else max(max_distance, distance_km)

        ordered_track = list(reversed(station["track"]))
        compact_track = []
        for point in ordered_track:
            coordinates = [point["longitude"], point["latitude"]]
            if compact_track and compact_track[-1]["coordinates"] == coordinates:
                compact_track[-1] = {**point, "coordinates": coordinates}
            else:
                compact_track.append({**point, "coordinates": coordinates})
        tracks[source] = compact_track[-300:]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": {
                "callsign": source,
                "last_heard": latest.get("time", ""),
                "last_heard_local": latest.get("time_local", ""),
                "path": latest.get("path", ""),
                "comment": latest.get("comment", ""),
                "symbol": f'{latest.get("symbol_table", "")}{latest.get("symbol", "")}',
                "packet_count": station["packet_count"],
                "direct_count": station["direct_count"],
                "digipeated_count": station["digipeated_count"],
                "reception": "direct" if is_direct else "digipeated",
                "distance_km": distance_km,
                "bearing": bearing,
            },
        })

    return {
        "generated_at": now.isoformat(),
        "period_hours": hours,
        "gateway": {
            "callsign": config["callsign"],
            "latitude": gateway_latitude,
            "longitude": gateway_longitude,
        },
        "stations": {"type": "FeatureCollection", "features": features},
        "tracks": tracks,
        "summary": {
            "station_count": len(features),
            "position_packet_count": positioned_packets,
            "direct_station_count": direct_stations,
            "digipeated_station_count": digipeated_stations,
            "max_distance_km": max_distance,
        },
    }


def excel_cell(value):
    if value is None:
        return '<c t="inlineStr"><is><t></t></is></c>'
    text = escape(str(value), quote=False)
    return f'<c t="inlineStr"><is><t>{text}</t></is></c>'


def build_xlsx(packets):
    headers = [
        "Zeit", "Quelle", "Ziel", "Pfad", "Typ", "Latitude", "Longitude",
        "Symbol", "Kommentar", "Info", "Rohpaket",
    ]
    rows = [headers]
    for packet in packets:
        rows.append([
            packet["time_local"],
            packet["source"],
            packet["destination"],
            packet["path"],
            packet["kind"],
            packet["latitude"],
            packet["longitude"],
            f'{packet["symbol_table"]}{packet["symbol"]}'.strip(),
            packet["comment"],
            packet["info"],
            packet["raw"],
        ])

    sheet_rows = []
    for index, row in enumerate(rows, start=1):
        cells = "".join(excel_cell(value) for value in row)
        sheet_rows.append(f'<row r="{index}">{cells}</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        '</worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="APRS Pakete" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )

    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


def status_payload():
    lines = journal_lines()
    packets = stored_packets_with_latest()
    config = parse_config()
    socket_endpoint = active_aprsis_socket(config["igate_port"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "service": service_status(),
        "aprsis": parse_aprsis(lines, config["igate_server"], socket_endpoint),
        "sdr": sdr_status(),
        "system": system_status(),
        "config": config,
        "calibration": calibration_status(),
        "packets": packets,
        "events": interesting_events(lines),
        "logs": lines[-80:],
    }


def diagnostics_payload():
    config = parse_config()
    lines = journal_lines()
    calibration = calibration_status()
    sdr = sdr_status()
    try:
        packet_store_bytes = os.path.getsize(PACKET_STORE)
    except OSError:
        packet_store_bytes = 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system": system_diagnostics(),
        "memory": memory_status(),
        "disk": disk_status(),
        "services": [service_diagnostics(unit) for unit in DIAGNOSTIC_SERVICES],
        "aprsis": parse_aprsis(
            lines,
            config["igate_server"],
            active_aprsis_socket(config["igate_port"]),
        ),
        "sdr": {
            **sdr,
            "ppm": calibration.get("ppm"),
            "gain": calibration.get("gain"),
        },
        "config": config,
        "network": network_diagnostics(),
        "usb": usb_diagnostics(),
        "storage": {
            "packet_store": PACKET_STORE,
            "packet_count": packet_store_count(),
            "packet_limit": MAX_STORED_PACKETS,
            "packet_store_bytes": packet_store_bytes,
            "dashboard_port": PORT,
        },
    }


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

    def send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(body, "application/json; charset=utf-8")

    def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
        body = json.dumps({"error": str(message)}, ensure_ascii=False).encode("utf-8")
        self.send_bytes(body, "application/json; charset=utf-8", status)

    def send_xlsx(self, body, filename):
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self.send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/status":
            self.send_json(status_payload())
        elif path == "/api/diagnostics":
            self.send_json(diagnostics_payload())
        elif path == "/api/map":
            query = parse_qs(parsed.query)
            try:
                hours = int(query.get("hours", ["24"])[0])
            except ValueError:
                hours = 24
            if hours not in (0, 1, 24, 168):
                hours = 24
            filter_text = query.get("filter", [""])[0][:40]
            self.send_json(map_payload(hours, filter_text))
        elif path == "/api/calibration":
            self.send_json(calibration_status())
        elif path == "/export.xlsx":
            query = parse_qs(parsed.query)
            filter_text = query.get("filter", [""])[0]
            body = build_xlsx(filtered_packets(filter_text))
            self.send_xlsx(body, "aprsgate-packets.xlsx")
        elif path == "/healthz":
            self.send_json({"ok": True})
        else:
            self.send_bytes(
                json.dumps({"error": "not found"}).encode("utf-8"),
                "application/json; charset=utf-8",
                HTTPStatus.NOT_FOUND,
            )

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0"))
        fields = parse_qs(self.rfile.read(length).decode("utf-8"))
        try:
            if path == "/api/calibration/measure":
                frequency_mhz = validate_float(fields.get("frequency_mhz", ["145.5"])[0], 145.5, 24, 1766)
                ppm = validate_float(fields.get("ppm", ["0"])[0], 0, -200, 200)
                gain = validate_float(fields.get("gain", ["35"])[0], 35, 0, 50)
                span_khz = validate_float(fields.get("span_khz", ["120"])[0], 120, 20, 500)
                self.send_json(helper_payload([
                    "measure",
                    "--frequency-mhz", f"{frequency_mhz:g}",
                    "--ppm", f"{ppm:g}",
                    "--gain", f"{gain:g}",
                    "--span-khz", f"{span_khz:g}",
                ], timeout=25))
            elif path == "/api/calibration/apply":
                ppm = validate_float(fields.get("ppm", ["0"])[0], 0, -200, 200)
                gain = validate_float(fields.get("gain", ["35"])[0], 35, 0, 50)
                self.send_json(helper_payload([
                    "apply",
                    "--ppm", f"{ppm:g}",
                    "--gain", f"{gain:g}",
                ], timeout=20))
            else:
                self.send_error_json("not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_error_json(exc, HTTPStatus.INTERNAL_SERVER_ERROR)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"aprsgate dashboard listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
