"""
ESP32-S3 Stream Connectivity Test.
Tests /, /snapshot, /telemetry, and /ping endpoints.
Usage:
    python stream_test.py http://192.168.1.X/
"""

import sys
import urllib.request
import urllib.error
import json
import time


def test_endpoint(base_url: str, name: str, path: str, expect_json=False) -> bool:
    url = base_url.rstrip("/") + path
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        if resp.status == 200:
            if expect_json:
                data = json.loads(resp.read().decode())
                print(f"  [OK] {name} ({url}) -> {json.dumps(data, indent=2)}")
            else:
                body = resp.read()
                print(f"  [OK] {name} ({url}) -> {len(body)} bytes")
            return True
        else:
            print(f"  [FAIL] {name} -> HTTP {resp.status}")
            return False
    except Exception as e:
        print(f"  [FAIL] {name} -> {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python stream_test.py http://ESP32_IP/")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    print(f"\n=== ESP32-S3 Connectivity Test ===\n")
    print(f"Target: {base_url}\n")

    results = []
    results.append(test_endpoint(base_url, "Stream (/)", "/", expect_json=False))
    results.append(test_endpoint(base_url, "Snapshot", "/snapshot", expect_json=False))
    results.append(test_endpoint(base_url, "Telemetry", "/telemetry", expect_json=True))
    results.append(test_endpoint(base_url, "Ping", "/ping", expect_json=True))

    print(f"\n--- Results ---")
    passed = sum(results)
    total = len(results)
    print(f"{passed}/{total} endpoints passed")
    if passed == total:
        print("All checks passed!")
    else:
        print(f"{total - passed} endpoint(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()