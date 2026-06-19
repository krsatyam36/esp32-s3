#!/usr/bin/env python3
"""
Auto-discover the ESP32 on the network.

Discovery methods (in order):
  1. mDNS resolution of xiao-esp32s3-cam.local
  2. Scan the serial port for "Stream Ready at:" message
  3. Scan the local subnet for the ESP32 HTTP endpoint

Usage:
    python src/discover_esp32.py                  # print IP to stdout
    python src/discover_esp32.py --write-config    # write to src/config.py
    python src/discover_esp32.py --watch           # watch serial until IP found
"""

# ─── Standard Library ───────────────────────────────
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOSTNAME = "xiao-esp32s3-cam"
DISCOVERED_IP: str | None = None


def find_pio_serial_port() -> str | None:
    """Find the serial port used by PlatformIO for the ESP32."""
    try:
        result = subprocess.run(
            ["pio", "device", "list", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            devices = json.loads(result.stdout)
            for dev in devices:
                port = dev.get("port", "")
                desc = dev.get("description", "").lower()
                hwid = str(dev.get("hardware_id", "")).lower()
                if "esp32" in hwid or "esp32" in desc or "USB JTAG" in desc:
                    return port
    except Exception:
        pass
    # Fallback: common paths
    for p in [f"/dev/ttyACM{i}" for i in range(4)] + [f"/dev/ttyUSB{i}" for i in range(4)]:
        if os.path.exists(p):
            return p
    return None  # no result


def discover_via_serial(timeout: float = 15) -> str | None:
    """Read ESP32 serial output and extract the IP from 'Stream Ready at:'."""
    port = find_pio_serial_port()
    if port is None:
        return None

    import serial

    pattern = re.compile(r"http://(\d+\.\d+\.\d+\.\d+)/")
    try:
        ser = serial.Serial(port, 115200, timeout=1)
        deadline = time.time() + timeout
        buf = ""
        while time.time() < deadline:
            try:
                data = ser.read(1024).decode("utf-8", errors="replace")
                if not data:
                    continue
                buf += data
                m = pattern.search(buf)
                if m:
                    ip = m.group(1)
                    return ip
            except serial.SerialException:
                break
        ser.close()
    except Exception:
        pass
    return None


def discover_via_mdns() -> str | None:
    """Try to resolve the ESP32's mDNS hostname."""
    candidates = [
        f"{HOSTNAME}.local",
        f"{HOSTNAME}",
    ]
    for name in candidates:
        try:
            ip = socket.gethostbyname(name)
            # Verify it responds
            req = urllib.request.Request(f"http://{ip}/ping", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return ip
        except Exception:
            continue
    return None


def discover_via_arp_scan() -> str | None:
    """Scan local subnet for the ESP32 HTTP endpoint."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        return None

    # Determine subnet
    parts = local_ip.split(".")
    if len(parts) != 4:
        return None
    subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

    print(f"  Scanning subnet {subnet}...", file=sys.stderr)
    for ip_int in range(1, 255):
        ip = f"{parts[0]}.{parts[1]}.{parts[2]}.{ip_int}"
        if ip == local_ip:
            continue
        try:
            req = urllib.request.Request(f"http://{ip}/ping", method="GET")
            with urllib.request.urlopen(req, timeout=0.3) as resp:
                if resp.status == 200:
                    body = resp.read().decode("utf-8")
                    if HOSTNAME in body or "fw" in body or "esp32" in body.lower():
                        return ip
        except Exception:
            continue
    return None


def discover(timeout: float = 15) -> str | None:
    """Try all discovery methods and return IP or None."""
    global DISCOVERED_IP
    if DISCOVERED_IP:
        return DISCOVERED_IP

    print("🔍 Auto-discovering ESP32...", file=sys.stderr)

    # Method 1: mDNS
    print("  1. Trying mDNS...", file=sys.stderr)
    ip = discover_via_mdns()
    if ip:
        print(f"  ✅ Found via mDNS: {ip}", file=sys.stderr)
        DISCOVERED_IP = ip
        return ip

    # Method 2: Serial monitor
    port = find_pio_serial_port()
    if port:
        print(f"  2. Checking serial port {port}...", file=sys.stderr)
        ip = discover_via_serial(timeout=timeout)
        if ip:
            print(f"  ✅ Found via serial: {ip}", file=sys.stderr)
            DISCOVERED_IP = ip
            return ip
    else:
        print("  2. No serial port found", file=sys.stderr)

    # Method 3: Network scan
    print("  3. Scanning network...", file=sys.stderr)
    ip = discover_via_arp_scan()
    if ip:
        print(f"  ✅ Found via network scan: {ip}", file=sys.stderr)
        DISCOVERED_IP = ip
        return ip

    print("  ❌ ESP32 not found", file=sys.stderr)
    return None


def write_config(ip: str) -> None:
    """Write the discovered IP to src/config.py."""
    config_path = os.path.join(os.path.dirname(__file__), "config.py")
    with open(config_path, "w") as f:
        f.write(f'ESP32_IP = "http://{ip}/"\n')
    print(f"  ✏️  Written to {config_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Discover ESP32 on network")
    parser.add_argument("--write-config", action="store_true", help="Write IP to src/config.py")
    parser.add_argument("--watch", action="store_true", help="Watch serial port for IP")
    parser.add_argument("--timeout", type=float, default=15, help="Timeout in seconds")
    parser.add_argument("--quiet", action="store_true", help="Only print IP, no stderr")
    args = parser.parse_args()

    if args.quiet:
        # Redirect stderr to devnull
        sys.stderr = open(os.devnull, "w")

    if args.watch:
        ip = discover_via_serial(timeout=args.timeout)
    else:
        ip = discover(timeout=args.timeout)

    if ip:
        if args.write_config:
            write_config(ip)
        print(ip)
        return 0
    if not args.quiet:
        print("ESP32 not found. Make sure it's powered on and connected.", file=sys.stderr)
        print("Try: pio device monitor to check the serial output.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
