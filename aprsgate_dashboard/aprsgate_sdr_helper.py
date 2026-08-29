#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time


SERVICE = "direwolf-sdr.service"
DEFAULTS_FILE = "/etc/default/aprsgate-sdr"
LAST_MEASUREMENT_FILE = "/var/lib/aprsgate-sdr/last-measurement.json"
RTL_FREQUENCY = "144.800M"
SAMPLE_RATE = "24000"


def run(args, check=True, timeout=None):
    result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    return result


def read_defaults():
    values = {"RTL_PPM": "0", "RTL_GAIN": "35"}
    try:
        with open(DEFAULTS_FILE, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return values


def write_defaults(ppm, gain):
    body = (
        "# APRSgate RTL-SDR calibration\n"
        f"RTL_PPM={ppm}\n"
        f"RTL_GAIN={gain}\n"
        f"RTL_FREQUENCY={RTL_FREQUENCY}\n"
        f"RTL_SAMPLE_RATE={SAMPLE_RATE}\n"
    )
    with open(DEFAULTS_FILE, "w", encoding="utf-8") as handle:
        handle.write(body)


def read_last_measurement():
    try:
        with open(LAST_MEASUREMENT_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def write_last_measurement(payload):
    os.makedirs(os.path.dirname(LAST_MEASUREMENT_FILE), exist_ok=True)
    with open(LAST_MEASUREMENT_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def status():
    values = read_defaults()
    payload = {
        "ppm": int(float(values.get("RTL_PPM", "0"))),
        "gain": float(values.get("RTL_GAIN", "35")),
    }
    payload["last_measurement"] = read_last_measurement()
    return payload


def apply(ppm, gain):
    ppm = int(round(float(ppm)))
    gain = float(gain)
    if not -200 <= ppm <= 200:
        raise ValueError("PPM muss zwischen -200 und 200 liegen")
    if not 0 <= gain <= 50:
        raise ValueError("Gain muss zwischen 0 und 50 dB liegen")
    write_defaults(ppm, gain)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "restart", SERVICE])
    return status()


def parse_power_csv(stdout):
    best = None
    for line in stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            low = float(parts[2])
            step = float(parts[4])
            powers = [float(value) for value in parts[6:] if value.strip()]
        except ValueError:
            continue
        for index, power in enumerate(powers):
            frequency = low + (index * step) + (step / 2)
            if best is None or power > best["power_db"]:
                best = {"frequency_hz": frequency, "power_db": power}
    if best is None:
        raise RuntimeError("rtl_power hat keinen Peak geliefert")
    return best


def measure(frequency_mhz, ppm, gain, span_khz):
    frequency_mhz = float(frequency_mhz)
    ppm = int(round(float(ppm)))
    gain = float(gain)
    span_khz = float(span_khz)
    if not 24 <= frequency_mhz <= 1766:
        raise ValueError("Frequenz ausserhalb des RTL-SDR-Bereichs")
    if not -200 <= ppm <= 200:
        raise ValueError("PPM muss zwischen -200 und 200 liegen")
    if not 0 <= gain <= 50:
        raise ValueError("Gain muss zwischen 0 und 50 dB liegen")
    if not 20 <= span_khz <= 500:
        raise ValueError("Scan-Breite muss zwischen 20 und 500 kHz liegen")

    target_hz = frequency_mhz * 1_000_000
    half_span_hz = span_khz * 500
    low_hz = int(target_hz - half_span_hz)
    high_hz = int(target_hz + half_span_hz)
    bin_hz = 1000

    was_active = run(["systemctl", "is-active", SERVICE], check=False).stdout.strip() == "active"
    run(["systemctl", "stop", SERVICE], check=False)
    time.sleep(1)
    try:
        result = run(
            [
                "rtl_power",
                "-f", f"{low_hz}:{high_hz}:{bin_hz}",
                "-i", "5",
                "-1",
                "-p", str(ppm),
                "-g", f"{gain:g}",
                "-c", "0.2",
                "-w", "blackman",
                "-",
            ],
            timeout=15,
        )
        peak = parse_power_csv(result.stdout)
    finally:
        if was_active:
            run(["systemctl", "start", SERVICE], check=False)

    offset_hz = peak["frequency_hz"] - target_hz
    suggested_ppm = int(round(ppm - (offset_hz / frequency_mhz)))
    suggested_ppm = max(-200, min(200, suggested_ppm))
    return {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_mhz": frequency_mhz,
        "measured_mhz": peak["frequency_hz"] / 1_000_000,
        "offset_hz": offset_hz,
        "power_db": peak["power_db"],
        "current_ppm": ppm,
        "suggested_ppm": suggested_ppm,
        "gain": gain,
        "span_khz": span_khz,
    }


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--ppm", required=True)
    apply_parser.add_argument("--gain", required=True)

    measure_parser = subparsers.add_parser("measure")
    measure_parser.add_argument("--frequency-mhz", required=True)
    measure_parser.add_argument("--ppm", required=True)
    measure_parser.add_argument("--gain", required=True)
    measure_parser.add_argument("--span-khz", required=True)

    args = parser.parse_args()
    try:
        if args.command == "status":
            payload = status()
        elif args.command == "apply":
            payload = apply(args.ppm, args.gain)
        else:
            payload = measure(args.frequency_mhz, args.ppm, args.gain, args.span_khz)
            write_last_measurement(payload)
        print(json.dumps(payload))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
