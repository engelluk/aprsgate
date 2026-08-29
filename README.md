# APRSgate

APRSgate is a receive-only VHF APRS iGate and local monitoring dashboard built
for a Raspberry Pi, an RTL-SDR receiver, Dire Wolf, and an optional external
USB Wi-Fi adapter.

The project receives 1200 baud APRS traffic on 144.800 MHz, decodes it with
Dire Wolf, forwards eligible packets to APRS-IS, and presents the local radio
activity in a browser. The dashboard includes received packets, station
positions, system diagnostics, Wi-Fi state, and RTL-SDR calibration controls.

## Features

- Receive-only APRS iGate for the European 2 m APRS frequency, 144.800 MHz
- RTL-SDR input through `rtl_fm` and Dire Wolf
- APRS-IS connection state with `VERIFIED`, `CONNECTED`, and `WAITING` states
- Persistent local packet history with callsign filtering and XLSX export
- Interactive received-station map using Leaflet and OpenStreetMap
- Direct versus digipeated reception classification from the APRS path
- Station distance, bearing, packet count, and optional position track
- Raspberry Pi temperature, load, voltage, throttling, memory, and disk status
- systemd service, USB topology, network interface, route, and Wi-Fi diagnostics
- RTL-SDR PPM and gain calibration workflow
- Optional external-Wi-Fi-first failover to the Raspberry Pi internal adapter
- Local Wi-Fi provisioning access point when no configured network is available
- Responsive browser interface for desktop and mobile devices

## Hardware

The current installation uses the following hardware. Equivalent components
can be used after adapting device identifiers and interface names.

| Component | Current hardware | Purpose |
| --- | --- | --- |
| Single-board computer | Raspberry Pi Zero 2 W | Runs the receiver pipeline, services, and dashboard |
| SDR receiver | RTL-SDR Blog V3-class USB receiver | Receives the 144.800 MHz APRS channel |
| VHF antenna | 2 m antenna suitable for 144.800 MHz | APRS RF reception |
| External Wi-Fi | RTL8188FTV USB adapter | Primary network connection with an external antenna |
| Internal Wi-Fi | Raspberry Pi onboard Wi-Fi | Automatic fallback connection |
| USB connectivity | Powered USB hub recommended | Connects the SDR and Wi-Fi adapter without overloading the Pi |
| Storage | Raspberry Pi-compatible microSD card | Operating system, packet history, and logs |
| Power | Stable 5 V supply sized for the Pi and USB devices | Prevents USB resets and undervoltage throttling |

The USB vendor/product IDs and network interface names are configurable in the
systemd service templates. They must be checked on every target system with
`lsusb`, `ip link`, and `nmcli device status`.

## Software

The project is designed for a systemd-based Raspberry Pi Linux installation.
The current device runs Debian 13 on a 64-bit Raspberry Pi kernel.

Required components:

- Python 3
- Dire Wolf
- `rtl-sdr` utilities, including `rtl_fm`, `rtl_power`, and `rtl_test`
- NetworkManager and `nmcli`
- systemd
- `iproute2`, `iw`, and `usbutils`
- A modern browser with JavaScript enabled

The application itself uses only the Python standard library. The station map
loads Leaflet 1.9.4 from `unpkg.com` with Subresource Integrity and displays
tiles from `tile.openstreetmap.org`. The browser viewing the dashboard therefore
needs internet access for the map.

## Architecture

```text
2 m antenna
    |
RTL-SDR
    |
rtl_fm (144.800 MHz FM, 24 kHz audio)
    |
Dire Wolf (1200 baud AFSK / AX.25 / APRS)
    |                         |
    |                         +--> APRS-IS
    |
systemd journal
    |
APRSgate dashboard
    |-- packet store (JSON Lines)
    |-- status and diagnostics APIs
    |-- received-station GeoJSON API
    +-- local web UI and XLSX export
```

The Wi-Fi subsystem is independent of the receiver pipeline:

```text
external USB Wi-Fi (primary) --> internal Wi-Fi (fallback)
               |
        NetworkManager
               |
     provisioning access point
```

## Repository layout

```text
aprsgate_dashboard/
  app.py                         Dashboard, APIs, packet store, map, and export
  wifi_portal.py                 Local Wi-Fi provisioning portal
  aprsgate_wifi_failover.sh      External/internal Wi-Fi failover loop
  aprsgate_sdr_helper.py         Privileged SDR calibration helper
  install_wifi_portal.sh         Wi-Fi portal and failover installer
  install_sdr_calibration.sh     SDR helper and service installer
  deploy_wifi_portal.ps1         Windows-to-Pi deployment helper
  systemd/                       Service units, defaults, and sudoers template
  SDR_CALIBRATION.md              SDR calibration notes
  WIFI_PORTAL.md                  Wi-Fi provisioning notes
tests/
  test_app.py                     Status, diagnostics, and map unit tests
config/
  aprsgate-dashboard.env.example Optional dashboard environment
  aprsgate-wifi.env.example      Wi-Fi and setup-AP configuration template
  direwolf-sdr.conf.example      Receive-only Dire Wolf configuration template
```

## Configuration

### Dire Wolf

The runtime expects a Dire Wolf configuration at:

```text
/etc/direwolf-sdr.conf
```

Start with `config/direwolf-sdr.conf.example`. The active file is intentionally
not included because a real installation normally contains a callsign, APRS-IS
passcode, and precise station coordinates. At a minimum, configure:

- `MYCALL`
- `IGSERVER`
- `IGLOGIN`
- `PBEACON` with your own position and comment

Use the APRS frequency and operating rules applicable to your country. Do not
copy another operator's callsign, passcode, or position.

### RTL-SDR

`aprsgate_dashboard/systemd/aprsgate-sdr.defaults` provides the reference
environment variables used by `direwolf-sdr.service`:

| Variable | Meaning |
| --- | --- |
| `RTL_DEVICE` | RTL-SDR device index |
| `RTL_FREQUENCY` | Receive frequency |
| `RTL_SAMPLE_RATE` | Audio sample rate passed to Dire Wolf |
| `RTL_PPM` | Frequency correction |
| `RTL_GAIN` | Tuner gain in dB |
| `RTL_BIAS_T` | Bias-T state, if supported by the receiver |

The active file on the Raspberry Pi is `/etc/default/aprsgate-sdr`. The
installer does not overwrite an existing calibration file.

### Wi-Fi

Copy `config/aprsgate-wifi.env.example` to `/etc/default/aprsgate-wifi` and
configure it before installing either Wi-Fi service. The units use that file
for interface names, NetworkManager connection names, USB IDs, setup SSID,
setup password, and retry intervals. Review both service files as well:

```text
aprsgate_dashboard/systemd/aprsgate-wifi-portal.service
aprsgate_dashboard/systemd/aprsgate-wifi-failover.service
```

`APRSGATE_SETUP_PASSWORD` has no default. The portal refuses to start until it
contains a valid WPA passphrase or key.

## Installation notes

This repository provides installation templates rather than a preconfigured
Raspberry Pi image. Before using the supplied units and installers:

1. Install the required operating-system packages.
2. Create `/etc/direwolf-sdr.conf` for your own licensed station.
3. Create the `aprsgate` system user used by the dashboard, or run the SDR
   installer, which creates it when necessary.
4. Review every file in `aprsgate_dashboard/systemd/`.
5. Configure Wi-Fi profiles, optional USB IDs, and a unique setup credential.
6. Install the dashboard under `/opt/aprsgate-dashboard/`.
7. Install and enable only the services required by your hardware.
8. Verify the services and APIs locally before allowing network access.

The supplied installer scripts assume specific paths and should be treated as
reviewable deployment templates, not as unattended universal installers.

## Web interfaces

| Interface | Default port | Description |
| --- | ---: | --- |
| Dashboard | `8080` | APRS packets, station map, diagnostics, logs, and SDR calibration |
| Wi-Fi setup portal | `8088` | Local NetworkManager provisioning interface |
| Setup access point portal | `10.42.0.1:8088` | Available only while the fallback AP is active |

Useful local endpoints include:

```text
/healthz
/api/status
/api/diagnostics
/api/map?hours=24
/api/calibration
/export.xlsx
```

## Testing

Run the unit test suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover APRS-IS state detection, NetworkManager and `iw` parsing,
Raspberry Pi throttling flags, gateway coordinate conversion, station-map
aggregation, time filtering, and callsign filtering.

## Security and privacy

The dashboard and Wi-Fi portal do not currently implement application-level
authentication or TLS. They are intended for a trusted local network only.
Do not expose ports `8080` or `8088` directly to the internet.

Important considerations:

- The calibration API can restart the receiver service through a restricted
  sudo helper.
- The dashboard exposes packet contents, station positions, local network
  details, service state, and logs to anyone who can access it.
- The station map sends browser requests to the Leaflet CDN and OpenStreetMap
  tile service.
- APRS callsigns and precise coordinates can identify an operator and station
  location even when they are not passwords.
- Wi-Fi credentials submitted to the provisioning portal are passed to
  NetworkManager and must never be logged or committed.
- The setup access point must use a unique password for every installation.

Place the service behind a firewall or authenticated reverse proxy if it must
be reachable outside a trusted LAN.

## Public and private repositories

Keep this repository limited to reusable source code, templates, tests, and
public documentation. Store the active Dire Wolf configuration, Wi-Fi settings,
station coordinates, credentials, host inventory, and deployment notes in a
separate private repository.

The private deployment repository can include this project as a Git submodule.
That keeps application development here while the private repository records
the exact public revision deployed to each gateway.

## License

APRSgate is released under the [MIT License](LICENSE).

## Upstream projects and services

- [Dire Wolf](https://github.com/wb2osz/direwolf)
- [RTL-SDR](https://osmocom.org/projects/rtl-sdr/wiki)
- [Leaflet](https://leafletjs.com/)
- [OpenStreetMap](https://www.openstreetmap.org/)
- [APRS-IS](https://www.aprs-is.net/)

OpenStreetMap attribution is displayed on the map. Deployments must also follow
the OpenStreetMap tile usage policy and the terms of every external service they
use.
