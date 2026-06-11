"""
ESP32-S3 Stream Connectivity Test.
Tests /, /snapshot, /telemetry, and /ping endpoints.
Usage:
    python stream_test.py http://192.168.1.X/
"""

import json
import sys
import urllib.error
import urllib.request


import time as _time

def test_endpoint(base_url: str, name: str, path: str, expect_json=False) -> tuple[bool, float]:
    url = base_url.rstrip("/") + path
    start = _time.time()
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        elapsed = (_time.time() - start) * 1000
        if resp.status == 200:
            if expect_json:
                data = json.loads(resp.read().decode())
                print(f"  [OK] {name} ({url}) -> {json.dumps(data, indent=2)} [{elapsed:.0f}ms]")
            else:
                body = resp.read()
                print(f"  [OK] {name} ({url}) -> {len(body)} bytes [{elapsed:.0f}ms]")
            return True, elapsed
        print(f"  [FAIL] {name} -> HTTP {resp.status} [{elapsed:.0f}ms]")
        return False, elapsed
    except Exception as e:
        elapsed = (_time.time() - start) * 1000
        print(f"  [FAIL] {name} -> {e} [{elapsed:.0f}ms]")
        return False, elapsed


def main():
    if len(sys.argv) < 2:
        print("Usage: python stream_test.py http://ESP32_IP/")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    use_json = "--json" in sys.argv

    print("\n=== ESP32-S3 Connectivity Test ===\n")
    print(f"Target: {base_url}\n")

    endpoints = [
        ("Stream (/)", "/", False),
        ("Snapshot", "/snapshot", False),
        ("Telemetry", "/telemetry", True),
        ("Ping", "/ping", True),
        ("Diag", "/diag", True),
    ]

    results = []
    latencies = []
    for name, path, expect_json in endpoints:
        ok, lat = test_endpoint(base_url, name, path, expect_json=expect_json)
        results.append(ok)
        latencies.append(lat)

    print("\n--- Results ---")
    passed = sum(results)
    total = len(results)
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    print(f"{passed}/{total} endpoints passed")
    print(f"Avg latency: {avg_lat:.0f}ms (min={min(latencies):.0f}ms, max={max(latencies):.0f}ms)")
    if passed == total:
        print("All checks passed!")
    else:
        print(f"{total - passed} endpoint(s) failed")
        sys.exit(1)

    if use_json:
        import json as _json
        output = {
            "target": base_url,
            "timestamp": _time.time(),
            "results": [
                {"name": n, "passed": r, "latency_ms": l}
                for (n, _, _), r, l in zip(endpoints, results, latencies)
            ],
            "summary": {"passed": passed, "total": total, "avg_latency_ms": round(avg_lat, 1)},
        }
        print(_json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
