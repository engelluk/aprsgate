# Security policy

## Supported versions

Security fixes are applied to the latest release on the default branch.

## Deployment boundary

The dashboard and Wi-Fi provisioning portal are designed for a trusted local
network. They do not provide application authentication or TLS. Do not expose
ports `8080` or `8088` directly to the internet. Use a firewall and an
authenticated reverse proxy for access beyond the local network.

The SDR calibration API can restart the receiver through a restricted sudo
helper. Review the supplied sudoers rule and service user before installation.

Never commit active Dire Wolf configuration, APRS-IS passcodes, station
coordinates, Wi-Fi credentials, host inventories, or deployment logs.

## Reporting a vulnerability

Do not disclose an unpatched vulnerability in a public issue. Contact the
repository owner privately through the security-reporting method configured on
the hosting platform.
