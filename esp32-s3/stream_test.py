"""Simple ESP32-S3 stream connectivity test."""
import urllib.request
import sys

def test_connection(base_url: str) -> bool:
    endpoints = [
        ("/", "MJPEG stream"),
        ("/snapshot", "Snapshot"),
        ("/telemetry", "Telemetry"),
        ("/ping", "Health ping"),
    ]
    all_ok = True
    for path, name in endpoints:
        try:
            resp = urllib.request.urlopen(f"{base_url}{path}", timeout=3)
            print(f"  ✓ {name} ({resp.status})")
        except Exception as e:
            print(f"  ✗ {name} - {e}")
            all_ok = False
    return all_ok

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.1.100/"
    print(f"Testing ESP32-S3 at {url}...")
    ok = test_connection(url.rstrip("/"))
    print(f"\n{'All tests passed!' if ok else 'Some tests failed.'}")
    sys.exit(0 if ok else 1)
