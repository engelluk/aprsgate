# RTL-SDR calibration

The dashboard includes controls for measuring a known RF signal and updating
the RTL-SDR frequency correction and tuner gain.

## Procedure

1. Select a permitted, unused VHF test frequency.
2. Enter that frequency in the dashboard.
3. Transmit a stable test carrier from suitable equipment.
4. Select **Measure peak** while the carrier is present.
5. Confirm that the detected peak belongs to the intended signal.
6. Apply the suggested PPM correction and desired gain.

The measurement temporarily stops `direwolf-sdr.service` because `rtl_power`
needs exclusive access to the receiver. The helper starts the service again
after measurement or failure.

Follow the amateur-radio regulations and band plan applicable to your location.

## Configuration

`direwolf-sdr.service` reads `/etc/default/aprsgate-sdr`. The reference file is
`systemd/aprsgate-sdr.defaults`:

```text
RTL_PPM=0
RTL_GAIN=35
RTL_FREQUENCY=144.800M
RTL_SAMPLE_RATE=24000
RTL_DEVICE=0
RTL_BIAS_T=0
```

- `RTL_DEVICE` selects the RTL-SDR device index.
- `RTL_BIAS_T` enables the receiver bias-T only when set to `1`.
- `RTL_GAIN` requests tuner gain in dB; the driver selects a supported step.
- `RTL_FREQUENCY` and `RTL_SAMPLE_RATE` feed both `rtl_fm` and Dire Wolf.

The installer creates `/etc/default/aprsgate-sdr` only when it does not already
exist, preserving existing calibration values.

## Installed files

```text
/opt/aprsgate-dashboard/app.py
/usr/local/sbin/aprsgate-sdr-helper
/etc/default/aprsgate-sdr
/etc/sudoers.d/aprsgate-sdr-helper
/etc/systemd/system/aprsgate-dashboard.service
/etc/systemd/system/direwolf-sdr.service
```

The restricted sudo rule allows the `aprsgate` service account to call only the
calibration helper. The helper validates all accepted commands and numeric
ranges before changing configuration or restarting the receiver.

## API

```text
GET  /api/calibration
POST /api/calibration/measure
POST /api/calibration/apply
```

These endpoints have no application authentication and are intended for a
trusted local network. Do not expose the dashboard directly to the internet.
