#!/usr/bin/env python3
"""ESP32-S3 camera relay: one upstream MJPEG connection, many browser clients.

Upstream: http://192.168.1.12/  (multipart/x-mixed-replace, chunked)
Serves on 127.0.0.1:8090:
  /              HTML viewer
  /stream        fan-out MJPEG
  /snapshot.jpg  latest frame
  /health        JSON status

Stdlib only. Run: python3 esp32_relay.py [--port 8090]
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ESP_HOST = "192.168.1.12"
ESP_PORT = 80
BOUNDARY = b"123456789000000000000987654321"


def jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            return w, h
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        seg = (data[i + 2] << 8) | data[i + 3]
        if seg <= 0:
            break
        i += 2 + seg
    return 0, 0


class Hub:
    def __init__(self):
        self.cond = threading.Condition()
        self.seq = 0
        self.frame: bytes | None = None
        self.width = 0
        self.height = 0
        self.connected = False
        self.last_frame_ts = 0.0
        self.start_ts = time.time()
        self.times: deque[float] = deque(maxlen=40)
        self.errors = 0
        self.frames_total = 0

    def publish(self, frame: bytes):
        with self.cond:
            if not self.frame:
                self.width, self.height = jpeg_size(frame)
            self.frame = frame
            self.seq += 1
            self.frames_total += 1
            now = time.time()
            self.last_frame_ts = now
            self.times.append(now)
            self.connected = True
            self.cond.notify_all()

    def set_connected(self, value: bool):
        with self.cond:
            self.connected = value

    def next_frame(self, last_seq: int, timeout: float = 10.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout)
            return self.seq, self.frame

    def fps(self) -> float:
        with self.cond:
            t = list(self.times)
        if len(t) < 2:
            return 0.0
        span = t[-1] - t[0]
        v = (len(t) - 1) / span if span > 0 else 0.0
        return min(v, 60.0)

    def health(self) -> dict:
        with self.cond:
            return {
                "connected": self.connected,
                "source": f"http://{ESP_HOST}/",
                "width": self.width,
                "height": self.height,
                "fps": round(self.fps(), 2),
                "frames_total": self.frames_total,
                "last_frame_age_s": round(time.time() - self.last_frame_ts, 2)
                if self.last_frame_ts
                else None,
                "uptime_s": round(time.time() - self.start_ts, 1),
                "errors": self.errors,
            }


HUB = Hub()


def upstream_loop():
    """Maintain one connection to the ESP32 and parse multipart JPEG frames."""
    while True:
        conn = None
        try:
            conn = http.client.HTTPConnection(ESP_HOST, ESP_PORT, timeout=10)
            conn.request("GET", "/", headers={"User-Agent": "jetson-esp32-relay/1.0"})
            resp = conn.getresponse()
            if resp.status != 200:
                raise RuntimeError(f"upstream HTTP {resp.status}")
            HUB.set_connected(True)
            buf = b""
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    raise ConnectionError("upstream closed")
                buf += chunk
                if len(buf) > 8 * 1024 * 1024:  # safety
                    buf = buf[-1024 * 1024:]
                while True:
                    idx = buf.find(BOUNDARY)
                    if idx == -1:
                        if len(buf) > 64 * 1024:
                            buf = buf[-BOUNDARY_LEN_SAFE:]
                        break
                    hdr_end = buf.find(b"\r\n\r\n", idx)
                    if hdr_end == -1:
                        break
                    headers = buf[idx:hdr_end].decode("latin-1", "ignore")
                    m = re.search(r"Content-Length:\s*(\d+)", headers, re.I)
                    if m:
                        length = int(m.group(1))
                        start = hdr_end + 4
                        end = start + length
                        if len(buf) < end:
                            break
                        frame = buf[start:end]
                        buf = buf[end:]
                    else:
                        nxt = buf.find(BOUNDARY, hdr_end + 4)
                        if nxt == -1:
                            break
                        frame = buf[hdr_end + 4:nxt].rstrip(b"\r\n")
                        buf = buf[nxt:]
                    if frame.startswith(b"\xff\xd8"):
                        HUB.publish(frame)
        except Exception as exc:
            HUB.set_connected(False)
            HUB.errors += 1
            print(f"[relay] upstream error: {exc}", flush=True)
            time.sleep(1.0)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


BOUNDARY_LEN_SAFE = len(BOUNDARY) + 4


VIEWER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32-S3 Camera</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; background:#0b0d10; color:#dfe6ee;
         font:14px/1.4 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         display:flex; flex-direction:column; }
  header { display:flex; align-items:center; gap:12px; padding:12px 18px;
           border-bottom:1px solid #1e242c; background:#11151a; }
  header h1 { font-size:15px; font-weight:600; margin:0; letter-spacing:.3px; }
  .badge { font-size:11px; font-weight:700; letter-spacing:.8px; padding:3px 9px;
           border-radius:999px; background:#3a2222; color:#ff9a9a; }
  .badge.live { background:#12321f; color:#5df08c; }
  .meta { margin-left:auto; color:#8b98a6; font-variant-numeric:tabular-nums;
          display:flex; gap:16px; flex-wrap:wrap; }
  main { flex:1; display:flex; align-items:center; justify-content:center;
         padding:16px; min-height:0; }
  .wrap { position:relative; max-width:100%; max-height:100%; }
  #cam { display:block; max-width:100%; max-height:calc(100vh - 130px);
         border-radius:10px; background:#000; box-shadow:0 10px 40px #0008;
         transition:transform .15s ease; }
  #cam.flip { transform: rotate(180deg); }
  .overlay { position:absolute; inset:0; display:none; align-items:center;
             justify-content:center; background:#000b; border-radius:10px;
             color:#ffb4b4; font-size:16px; text-align:center; padding:20px; }
  .overlay.show { display:flex; }
  footer { display:flex; gap:10px; padding:10px 18px; border-top:1px solid #1e242c;
           background:#11151a; align-items:center; }
  button, a.btn { appearance:none; border:1px solid #2b3542; background:#1a212a;
        color:#dfe6ee; padding:7px 14px; border-radius:8px; font:inherit;
        cursor:pointer; text-decoration:none; }
  button:hover, a.btn:hover { background:#232c37; }
  #err { color:#ff9a9a; font-size:12px; margin-left:auto; }
</style>
</head>
<body>
<header>
  <h1>ESP32-S3 Camera</h1>
  <span id="badge" class="badge">CONNECTING</span>
  <div class="meta">
    <span id="res">--</span>
    <span id="fps">-- fps</span>
    <span id="src">192.168.1.12</span>
  </div>
</header>
<main>
  <div class="wrap">
    <img id="cam" src="/stream" alt="ESP32 camera stream">
    <div id="overlay" class="overlay show">Connecting to camera stream…</div>
  </div>
</main>
<footer>
  <button id="reload">Reconnect</button>
  <a class="btn" id="snap" href="/snapshot.jpg" target="_blank" rel="noopener">Snapshot</a>
  <button id="rot">Rotate 180°</button>
  <button id="fs">Fullscreen</button>
  <span id="err"></span>
</footer>
<script>
(() => {
  const cam = document.getElementById('cam');
  const badge = document.getElementById('badge');
  const overlay = document.getElementById('overlay');
  const res = document.getElementById('res');
  const fps = document.getElementById('fps');
  const err = document.getElementById('err');
  let retry = null, failures = 0;

  function reconnect() {
    clearTimeout(retry);
    cam.src = '/stream?t=' + Date.now();
  }
  cam.addEventListener('load', () => {
    failures = 0;
    overlay.classList.remove('show');
    err.textContent = '';
  });
  cam.addEventListener('error', () => {
    failures++;
    overlay.textContent = 'Stream interrupted — retrying…';
    overlay.classList.add('show');
    retry = setTimeout(reconnect, Math.min(5000, 500 * failures));
  });
  document.getElementById('reload').onclick = reconnect;
  document.getElementById('fs').onclick = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.querySelector('main').requestFullscreen();
  };
  // Camera is mounted upside down; default to 180°, remember the choice.
  const rot = document.getElementById('rot');
  let flipped = localStorage.getItem('camFlip') !== '0';
  function applyRot(on) {
    cam.classList.toggle('flip', on);
    rot.textContent = on ? 'Upright ✓' : 'Rotate 180°';
  }
  applyRot(flipped);
  rot.onclick = () => {
    flipped = !flipped;
    localStorage.setItem('camFlip', flipped ? '1' : '0');
    applyRot(flipped);
  };

  async function poll() {
    try {
      const r = await fetch('/health', {cache: 'no-store'});
      const h = await r.json();
      const live = h.connected && h.last_frame_age_s !== null && h.last_frame_age_s < 3;
      badge.textContent = live ? 'LIVE' : 'RECONNECTING';
      badge.classList.toggle('live', live);
      res.textContent = h.width ? h.width + '×' + h.height : '--';
      fps.textContent = (h.fps || 0).toFixed(1) + ' fps';
      if (h.connected) {
        overlay.classList.remove('show');
      } else {
        overlay.textContent = 'Camera offline — retrying…';
        overlay.classList.add('show');
      }
    } catch (e) {
      badge.textContent = 'OFFLINE';
      badge.classList.remove('live');
    }
  }
  poll();
  setInterval(poll, 2000);
})();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, ctype: str, body: bytes, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, "text/html; charset=utf-8", VIEWER.encode())
        elif path == "/health":
            self._send(200, "application/json", json.dumps(HUB.health()).encode())
        elif path in ("/snapshot.jpg", "/snapshot"):
            with HUB.cond:
                frame = HUB.frame
            if not frame:
                self._send(503, "text/plain", b"no frame yet\n")
            else:
                self._send(200, "image/jpeg", frame)
        elif path == "/stream":
            self._stream()
        else:
            self._send(404, "text/plain", b"not found\n")

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        last = 0
        try:
            while True:
                seq, frame = HUB.next_frame(last, timeout=10)
                if frame is None or seq == last:
                    continue
                last = seq
                self.wfile.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(frame)).encode()
                    + b"\r\n\r\n"
                )
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    threading.Thread(target=upstream_loop, daemon=True, name="upstream").start()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    print(f"[relay] viewer on http://{args.host}:{args.port}/  (upstream {ESP_HOST})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
