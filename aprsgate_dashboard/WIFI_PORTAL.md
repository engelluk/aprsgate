# Wi-Fi provisioning and failover

APRSgate can prefer an external USB Wi-Fi adapter, fall back to the Raspberry
Pi internal adapter, and provide a temporary setup access point when no saved
network is reachable.

## Requirements

- NetworkManager and `nmcli`
- Two configured NetworkManager connection profiles for failover
- An external adapter if primary/fallback operation is required

Check the target before installation:

```bash
nmcli --version
nmcli device status
nmcli connection show
ip link
lsusb
```

## Configuration

Copy and edit the example file:

```bash
sudo cp config/aprsgate-wifi.env.example /etc/default/aprsgate-wifi
sudo editor /etc/default/aprsgate-wifi
```

Set a unique `APRSGATE_SETUP_PASSWORD`. The portal rejects an empty or invalid
WPA passphrase. Also set the exact NetworkManager profile names used by the
primary and fallback interfaces.

The optional `APRSGATE_PRIMARY_USB_VENDOR` and
`APRSGATE_PRIMARY_USB_PRODUCT` values enable driver rebinding when an external
adapter fails to initialize after a shared USB startup. Leave both empty when
that workaround is not needed.

## Installation

From the `aprsgate_dashboard` directory on the Pi:

```bash
sudo ./install_wifi_portal.sh
```

From Windows, the helper can copy the files and run the installer over SSH:

```powershell
.\deploy_wifi_portal.ps1 user@gateway-host
```

The remote host must already contain a configured
`/etc/default/aprsgate-wifi`; credentials are deliberately not deployed from
this repository.

## Operation

When no known network is reachable and the configured portal interface is
available, NetworkManager starts the setup SSID. Connect with the locally
configured password and open:

```text
http://10.42.0.1:8088/
```

After a successful connection, NetworkManager retains the profile. The
failover service periodically tries the primary profile and disables the
fallback route once the primary interface is healthy.

## Diagnostics

```bash
systemctl status aprsgate-wifi-portal.service
systemctl status aprsgate-wifi-failover.service
journalctl -u aprsgate-wifi-failover.service -f
journalctl -u aprsgate-wifi-portal.service -f
nmcli connection show
nmcli device status
ip route
```

The portal has no application authentication or TLS and is intended only for a
trusted local network or the isolated setup access point. Do not expose port
`8088` to the internet.
