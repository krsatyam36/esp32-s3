import argparse
import http.client
import json
import logging
import os
import sys

import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("raw_view")

parser = argparse.ArgumentParser(description="ESP32-S3 Camera Viewer")
parser.add_argument("--ip", type=str, default=None, help="ESP32 IP address (overrides config.py)")
parser.add_argument("--format", type=str, default="avi", choices=["avi", "mp4"], help="Recording format (avi or mp4)")
parser.add_argument("--multi-ip", type=str, default=None, nargs="+", help="Multiple ESP32 IPs for multi-camera view")
args, _ = parser.parse_known_args()
RECORDING_FORMAT = args.format
MULTI_IPS = args.multi_ip

def _auto_discover() -> str:
    """Auto-discover ESP32 IP via mDNS or network scan."""
    from discover_esp32 import discover
    ip = discover(timeout=10)
    if ip:
        return f"http://{ip}"
    print("ERROR: Could not auto-discover ESP32.")
    print("Make sure the board is powered on and connected to WiFi.")
    print("Or provide the IP manually: python raw_view.py --ip http://192.168.1.X/")
    sys.exit(1)


if args.ip:
    BASE_URL = args.ip.rstrip("/")
else:
    _env_ip = os.environ.get("ESP32_IP", "").strip()
    if _env_ip:
        BASE_URL = _env_ip.rstrip("/")
    else:
        try:
            from config import ESP32_IP
            BASE_URL = ESP32_IP.rstrip("/")
            # If still the default placeholder, auto-discover
            if "192.168.1.X" in BASE_URL:
                print("Default IP in config.py — auto-discovering...")
                BASE_URL = _auto_discover()
        except ImportError:
            print("No config.py found — auto-discovering...")
            BASE_URL = _auto_discover()
SNAPSHOT_DIR = "snapshots"
RECORDING_DIR = "recordings"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

# ============================================================
#  ESP32 HTTP CLIENT
# ============================================================


class ESP32Client:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def send_command(self, endpoint: str) -> dict:
        try:
            resp = urllib.request.urlopen(f"{self.base_url}{endpoint}", timeout=5)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"success": False, "error": str(e)}

    def toggle_led(self, state: str):
        return self.send_command(f"/led?state={state}")

    def flash_led(self, count: int = 5):
        return self.send_command(f"/flash?count={count}")

    def set_resolution(self, val: str):
        return self.send_command(f"/res?val={val}")

    def get_telemetry(self) -> dict:
        return self.send_command("/telemetry")

    def get_snapshot(self) -> bytes | None:
        try:
            resp = urllib.request.urlopen(f"{self.base_url}/snapshot", timeout=5)
            return resp.read()
        except Exception:
            return None

    def get_stream(self):
        # Fail-fast 1.5s timeout prevents the background thread from hanging
        return urllib.request.urlopen(self.base_url + "/", timeout=1.5)


# ============================================================
#  STREAM BUFFER (Self-Healing)
# ============================================================


class StreamBuffer:
    def __init__(self):
        self.buffer = b""

    def feed(self, data: bytes):
        self.buffer += data

    def get_frame(self) -> np.ndarray | None:
        a = self.buffer.find(b"\xff\xd8")  # Start marker
        b = self.buffer.find(b"\xff\xd9")  # End marker

        if a != -1 and b != -1:
            if a < b:
                # Perfect frame found! Extract it.
                jpg = self.buffer[a : b + 2]
                self.buffer = self.buffer[b + 2 :]
                img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                return img
            # CORRUPTION DETECTED: An 'End' came before a 'Start'.
            # Delete the corrupted data so the buffer doesn't jam.
            self.buffer = self.buffer[a:]

        return None


# ============================================================
#  FRAME ANALYZER (face, QR, motion)
# ============================================================


class FrameAnalyzer:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.qr_detector = cv2.QRCodeDetector()
        self.prev_gray = None
        self.motion_threshold = 5000
        self.trail_points: list[tuple[int, int]] = []
        self.max_trail = 30
        self.trail_enabled = True

    def detect_faces(self, frame: np.ndarray) -> list:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
        return faces

    def read_qr(self, frame: np.ndarray) -> str | None:
        data, points, _ = self.qr_detector.detectAndDecode(frame)
        if data:
            return data
        return None

    def detect_motion(self, frame: np.ndarray) -> tuple[bool, np.ndarray | None]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        if self.prev_gray is None:
            self.prev_gray = gray
            return False, None

        delta = cv2.absdiff(self.prev_gray, gray)
        thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self.prev_gray = gray

        motion = False
        for c in contours:
            if cv2.contourArea(c) > self.motion_threshold:
                motion = True
                break
        return motion, thresh if motion else None

    def draw_face_boxes(self, frame: np.ndarray, faces: list):
        for x, y, w, h in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, "Face", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    def draw_motion_contours(self, frame: np.ndarray, thresh: np.ndarray):
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        centers = []
        for c in contours:
            if cv2.contourArea(c) > self.motion_threshold:
                x, y, w, h = cv2.boundingRect(c)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                centers.append((x + w // 2, y + h // 2))

        if self.trail_enabled and centers:
            cx = int(sum(p[0] for p in centers) / len(centers))
            cy = int(sum(p[1] for p in centers) / len(centers))
            self.trail_points.append((cx, cy))
            if len(self.trail_points) > self.max_trail:
                self.trail_points.pop(0)

        if self.trail_enabled and len(self.trail_points) > 1:
            for i in range(1, len(self.trail_points)):
                alpha = i / len(self.trail_points)
                thickness = max(1, int(alpha * 3))
                color = (0, int(255 * alpha), int(255 * (1 - alpha)))
                cv2.line(
                    frame,
                    self.trail_points[i - 1],
                    self.trail_points[i],
                    color,
                    thickness,
                    cv2.LINE_AA,
                )
            cv2.circle(frame, self.trail_points[-1], 4, (0, 255, 255), -1)

# ============================================================
#  RECORDER
# ============================================================


class Recorder:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.recording = False
        self.writer = None
        self.filename = None

    def start(self, frame: np.ndarray):
        if self.recording:
            return
        ext = RECORDING_FORMAT
        codec = "XVID" if ext == "avi" else "avc1"
        if ext == "mp4":
            try:
                fourcc = cv2.VideoWriter_fourcc(*codec)
                test = cv2.VideoWriter()
                if not test.isOpened():
                    codec = "mp4v"
            except Exception:
                codec = "mp4v"
        self.filename = os.path.join(
            self.output_dir,
            f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}",
        )
        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*codec)
        self.writer = cv2.VideoWriter(self.filename, fourcc, 20.0, (w, h))
        self.recording = True
        print(f"Recording started: {self.filename}")

    def write_frame(self, frame: np.ndarray):
        if self.recording and self.writer:
            self.writer.write(frame)

    def stop(self):
        if self.writer:
            self.writer.release()
            self.writer = None
        self.recording = False
        if self.filename:
            print(f"Recording saved: {self.filename}")
        self.filename = None


# ============================================================
#  FPS COUNTER
# ============================================================


class FPSCounter:
    def __init__(self):
        self.prev_time = 0
        self.smooth_fps = 0

    def update(self) -> float:
        now = time.time()
        dt = now - self.prev_time if self.prev_time > 0 else 0.001
        fps = 1.0 / dt
        self.prev_time = now
        self.smooth_fps = (self.smooth_fps * 0.9) + (fps * 0.1)
        return self.smooth_fps


# ============================================================
#  TELEMETRY DISPLAY
# ============================================================


class TelemetryOverlay:
    def __init__(self, client: ESP32Client):
        self.client = client
        self.data: dict = {}
        self.last_fetch = 0

    def update(self):
        now = time.time()
        if now - self.last_fetch < 2:
            return
        self.last_fetch = now
        try:
            self.data = self.client.get_telemetry()
        except Exception:
            pass

    def draw(self, frame: np.ndarray):
        if not self.data:
            return
        items = [
            (f"HEAP: {self.data.get('heap', '--')}", (255, 255, 0)),
            (f"Up: {self.data.get('uptime', '--')}s", (255, 255, 0)),
            (f"RSSI: {self.data.get('rssi', '--')} dBm", (255, 255, 0)),
            (f"Res: {self.data.get('resolution', '--')}", (255, 255, 0)),
            (f"PSRAM: {self.data.get('free_psram', '--')}", (255, 255, 0)),
            (f"Temp: {self.data.get('temperature', '--')} C", (255, 255, 0)),
        ]
        y = 48
        line_h = 18
        total_h = len(items) * line_h + 6
        ModernHUD.panel(frame, 8, y - 4, 200, total_h, alpha=0.5)
        cy = y + 2
        for text, color in items:
            ModernHUD.text_sm(frame, text, 14, cy + 10, color, 0.45, 1)
            cy += line_h


# ============================================================
#  MODERN HUD OVERLAY
# ============================================================


class ModernHUD:
    """Production-grade HUD overlay with dark panels and text shadows."""

    FONT = cv2.FONT_HERSHEY_DUPLEX
    FONT_SM = cv2.FONT_HERSHEY_SIMPLEX
    BG_ALPHA = 0.55
    PANEL_PAD = 8

    @staticmethod
    def text(frame, text, x, y, color=(255, 255, 255), scale=0.5, thick=1):
        cv2.putText(
            frame, text, (x + 1, y + 1), ModernHUD.FONT, scale, (0, 0, 0), thick + 1, cv2.LINE_AA
        )
        cv2.putText(frame, text, (x, y), ModernHUD.FONT, scale, color, thick, cv2.LINE_AA)

    @staticmethod
    def text_sm(frame, text, x, y, color=(255, 255, 255), scale=0.45, thick=1):
        cv2.putText(
            frame, text, (x + 1, y + 1), ModernHUD.FONT_SM, scale, (0, 0, 0), thick + 1, cv2.LINE_AA
        )
        cv2.putText(frame, text, (x, y), ModernHUD.FONT_SM, scale, color, thick, cv2.LINE_AA)

    @staticmethod
    def panel(frame, x, y, w, h, alpha=None):
        if alpha is None:
            alpha = ModernHUD.BG_ALPHA
        roi = frame[y : y + h, x : x + w]
        bg = np.full_like(roi, (0, 0, 0), dtype=np.uint8)
        blended = cv2.addWeighted(roi, 1 - alpha, bg, alpha, 0)
        frame[y : y + h, x : x + w] = blended

    @staticmethod
    def text_with_bg(frame, text, x, y, color=(255, 255, 255), scale=0.5, thick=1, pad=6):
        (tw, th), bl = cv2.getTextSize(text, ModernHUD.FONT, scale, thick)
        ModernHUD.panel(frame, x - pad, y - th - pad, tw + 2 * pad, th + bl + 2 * pad)
        ModernHUD.text(frame, text, x, y, color, scale, thick)

    @staticmethod
    def top_bar(frame, fps_text, badges, color=(0, 255, 0)):
        h, w = frame.shape[:2]
        bar_h = 36
        ModernHUD.panel(frame, 0, 0, w, bar_h, alpha=0.6)
        ModernHUD.text(frame, fps_text, 12, 26, color, 0.55, 2)
        if badges:
            badge_str = " | ".join(badges)
            bw, _ = cv2.getTextSize(badge_str, ModernHUD.FONT, 0.5, 1)[0]
            bx = w - bw - 16
            ModernHUD.panel(frame, bx - 6, 4, bw + 12, bar_h - 4, alpha=0.45)
            ModernHUD.text(frame, badge_str, bx, 26, (255, 255, 0), 0.5, 1)

    @staticmethod
    def grid(frame):
        h, w = frame.shape[:2]
        color = (180, 180, 180)
        for i in range(1, 3):
            cv2.line(frame, (w * i // 3, 0), (w * i // 3, h), color, 1)
            cv2.line(frame, (0, h * i // 3), (w, h * i // 3), color, 1)

    @staticmethod
    def crosshair(frame):
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        color = (255, 255, 255)
        cv2.line(frame, (cx - 20, cy), (cx + 20, cy), color, 1)
        cv2.line(frame, (cx, cy - 20), (cx, cy + 20), color, 1)
        cv2.circle(frame, (cx, cy), 4, color, 1)

    @staticmethod
    def recording_indicator(frame, elapsed_sec):
        h, w = frame.shape[:2]
        text = f"● REC {int(elapsed_sec // 60):02d}:{int(elapsed_sec % 60):02d}"
        (tw, th), bl = cv2.getTextSize(text, ModernHUD.FONT_SM, 0.55, 2)
        pad = 8
        x = w - tw - 2 * pad - 8
        y = h - 10
        ModernHUD.panel(frame, x, y - th - pad, tw + 2 * pad, th + bl + 2 * pad, alpha=0.7)
        cv2.putText(frame, text, (x + pad, y), ModernHUD.FONT_SM, 0.55, (0, 0, 255), 3, cv2.LINE_AA)
        cv2.putText(frame, text, (x + pad, y), ModernHUD.FONT_SM, 0.55, (0, 0, 255), 2, cv2.LINE_AA)

    @staticmethod
    def corner_info(frame, lines, x=10, y=None):
        if y is None:
            y = frame.shape[0] - 10
        line_h = 18
        total_h = len(lines) * line_h + 6
        ModernHUD.panel(frame, x, y - total_h, 200, total_h, alpha=0.5)
        cy = y - 6
        for text, color in lines:
            ModernHUD.text_sm(frame, text, x + 4, cy, color, 0.45, 1)
            cy += line_h


# ============================================================
#  MAIN VIEWER (Multi-Threaded & Real-Time Synced)
# ============================================================


class Viewer:
    def __init__(self):
        self.client = ESP32Client(BASE_URL)

        # --- NEW: Automatically set SVGA resolution on startup ---
        print("Setting default camera resolution to SVGA (800x600)...")
        self.client.set_resolution("SVGA")
        # ---------------------------------------------------------

        self.buffer = StreamBuffer()
        self.analyzer = FrameAnalyzer()
        self.recorder = Recorder(RECORDING_DIR)
        self.fps = FPSCounter()
        self.telemetry = TelemetryOverlay(self.client)

        self.enable_face = False
        self.enable_qr = False
        self.enable_motion = False
        self.show_telemetry = False
        self.led_on = False
        self.running = True
        self.rotation_angle = 0
        self.show_grid = False
        self.show_crosshair = False
        self.show_timestamp = False
        self.recording_start_time = 0
        self.frame_dims = (0, 0)
        self.roi_region = None
        self.selecting_roi = False
        self.roi_start = None
        self.roi_end = None
        self.show_roi = False

        # Threading synchronization variables
        self.latest_frame = None
        self.new_frame_ready = False
        self.frame_lock = threading.Lock()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)

    def draw_hud(self, frame: np.ndarray):
        badges = []
        if self.rotation_angle:
            badges.append(f"ROT:{self.rotation_angle}°")
        if self.enable_face:
            badges.append("FACE")
        if self.enable_qr:
            badges.append("QR")
        if self.enable_motion:
            badges.append("MOTION")
        if self.show_telemetry:
            badges.append("TELE")
        if self.show_grid:
            badges.append("GRID")
        if self.show_crosshair:
            badges.append("CROSS")
        if self.show_timestamp:
            badges.append("TS")
        if self.analyzer.trail_enabled:
            badges.append("TRAIL")
        ModernHUD.top_bar(frame, f"FPS: {self.fps.smooth_fps:.1f}", badges)

        if self.show_grid:
            ModernHUD.grid(frame)
        if self.show_crosshair:
            ModernHUD.crosshair(frame)

        if self.recorder.recording and self.recording_start_time > 0:
            elapsed = time.time() - self.recording_start_time
            ModernHUD.recording_indicator(frame, elapsed)

        if self.show_timestamp:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ModernHUD.text_sm(frame, ts, frame.shape[1] - 160, 28, (180, 180, 180), 0.4, 1)

        if self.roi_region:
            x, y, w, h = self.roi_region
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            cv2.putText(frame, "ROI", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        elif self.roi_start and self.roi_end:
            cv2.rectangle(frame, self.roi_start, self.roi_end, (255, 255, 0), 2)
    def handle_keys(self, key: int):
        if key == ord("q"):
            self.running = False
        elif key == ord("s"):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(SNAPSHOT_DIR, f"snapshot_{ts}.jpg")
            ret = self.client.get_snapshot()
            if ret:
                with open(path, "wb") as f:
                    f.write(ret)
                print(f"Snapshot saved: {path}")
        elif key == ord("r"):
            if self.recorder.recording:
                self.recorder.stop()
            else:
                print("Press 'r' again to start recording after frame arrives")
        elif key == ord("1"):
            self.client.set_resolution("SVGA")
        elif key == ord("2"):
            self.client.set_resolution("UXGA")
        elif key == ord("3"):
            self.client.set_resolution("VGA")
        elif key == ord("4"):
            self.client.set_resolution("QVGA")
        elif key == ord("5"):
            self.client.set_resolution("QQVGA")
        elif key == ord("f"):
            self.enable_face = not self.enable_face
        elif key == ord("z"):
            self.enable_qr = not self.enable_qr
        elif key == ord("m"):
            self.enable_motion = not self.enable_motion
        elif key == ord("t"):
            self.show_telemetry = not self.show_telemetry
        elif key == ord("o"):
            self.rotation_angle = (self.rotation_angle + 90) % 360
            print(f"Rotation: {self.rotation_angle}°")
        elif key == ord("g"):
            self.show_grid = not self.show_grid
            print(f"Grid: {'ON' if self.show_grid else 'OFF'}")
        elif key == ord("c"):
            self.show_crosshair = not self.show_crosshair
            print(f"Crosshair: {'ON' if self.show_crosshair else 'OFF'}")
        elif key == ord("l"):
            self.led_on = not self.led_on
            self.client.toggle_led("on" if self.led_on else "off")
        elif key == ord("L"):
            self.client.flash_led(5)
        elif key == ord("p"):
            self.analyzer.trail_enabled = not self.analyzer.trail_enabled
            print(f"Motion trail: {'ON' if self.analyzer.trail_enabled else 'OFF'}")
        elif key == ord("T"):
            self.show_timestamp = not self.show_timestamp
            print(f"Timestamp: {'ON' if self.show_timestamp else 'OFF'}")
        elif key == ord("i"):
            self.show_roi = not self.show_roi
            self.selecting_roi = self.show_roi
            if not self.show_roi:
                self.roi_region = None
                self.roi_start = None
                self.roi_end = None
            print(f"ROI selection: {'ON' if self.show_roi else 'OFF'}")
        elif key == ord("x"):
            if self.roi_region:
                self.roi_region = None
                self.roi_start = None
                self.roi_end = None
                print("ROI cleared")

    def _capture_loop(self):
        """Background thread dedicated entirely to network streaming.
        Uses exponential backoff with random jitter for reconnection."""
        import random

        print(f"Connecting to {BASE_URL}...")
        retry_delay = 1.0
        max_retry = 30.0
        while self.running:
            stream = None
            try:
                stream = self.client.get_stream()
                print("Connected! Streaming started...\n")
                retry_delay = 1.0
                while self.running:
                    try:
                        data = stream.read(65536)
                        if not data:
                            break

                        self.buffer.feed(data)

                        while True:
                            frame = self.buffer.get_frame()
                            if frame is None:
                                break

                            with self.frame_lock:
                                self.latest_frame = frame
                                self.new_frame_ready = True

                    except (
                        TimeoutError,
                        urllib.error.URLError,
                        ConnectionError,
                        http.client.IncompleteRead,
                        http.client.RemoteDisconnected,
                    ):
                        print("Connection lost, reconnecting...")
                        break
                    except Exception as e:
                        print(f"Stream error: {e}. Reconnecting...")
                        break
            except Exception as e:
                print(f"Connection failed: {e}")
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            jitter = random.uniform(0.5, 1.5)
            actual_delay = min(retry_delay * jitter, max_retry)
            print(f"Retrying in {actual_delay:.1f}s... (backoff: {retry_delay:.0f}s)")
            time.sleep(actual_delay)
            retry_delay = min(retry_delay * 2, max_retry)

    def run(self):
        """Main UI Thread: Handles rendering, AI, and OpenCV events."""
        self.capture_thread.start()
        print("UI Thread initialized. Press 'h' for help.\n")

        def _mouse_callback(event, x, y, flags, param):
            if not self.show_roi:
                return
            if event == cv2.EVENT_LBUTTONDOWN:
                self.roi_start = (x, y)
                self.roi_end = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and self.roi_start:
                self.roi_end = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and self.roi_start:
                x1, y1 = self.roi_start
                x2, y2 = x, y
                rx, ry = min(x1, x2), min(y1, y2)
                rw, rh = abs(x2 - x1), abs(y2 - y1)
                if rw > 10 and rh > 10:
                    self.roi_region = (rx, ry, rw, rh)
                    print(f"ROI set: ({rx},{ry}) {rw}x{rh}")
                self.roi_start = None
                self.roi_end = None
                self.selecting_roi = False

        stream_recording = False

        while self.running:
            # ONLY RENDER FRESH FRAMES
            with self.frame_lock:
                if self.new_frame_ready and self.latest_frame is not None:
                    frame = self.latest_frame.copy()
                    self.new_frame_ready = False
                else:
                    frame = None

            if frame is None:
                # If no fresh frame, just keep the GUI alive and wait
                key = cv2.waitKey(10) & 0xFF
                self.handle_keys(key)
                continue

            # FPS accurately calculates actual camera frames
            fps_val = self.fps.update()

            # Apply rotation before CV analysis so annotations match
            if self.rotation_angle == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation_angle == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation_angle == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            if self.enable_face and fps_val > 0:
                faces = self.analyzer.detect_faces(frame)
                self.analyzer.draw_face_boxes(frame, faces)

            if self.enable_qr:
                qr_data = self.analyzer.read_qr(frame)
                if qr_data:
                    ModernHUD.text_with_bg(
                        frame, f"QR: {qr_data}", 12, frame.shape[0] - 14, (255, 0, 255), 0.55, 2
                    )

            if self.enable_motion:
                motion, thresh = self.analyzer.detect_motion(frame)
                if motion:
                    self.analyzer.draw_motion_contours(
                        frame, thresh if thresh is not None else np.zeros_like(frame)
                    )
                    ModernHUD.text_with_bg(
                        frame, "MOTION DETECTED!", frame.shape[1] - 170, 28, (0, 0, 255), 0.6, 2
                    )

            if self.show_telemetry:
                self.telemetry.update()
                self.telemetry.draw(frame)

            self.draw_hud(frame)

            h, w = frame.shape[:2]
            if (w, h) != self.frame_dims:
                self.frame_dims = (w, h)

            if not stream_recording and self.recorder.recording:
                self.recorder.start(frame)
                stream_recording = True
                self.recording_start_time = time.time()
            elif stream_recording and self.recorder.recording:
                self.recorder.write_frame(frame)
            elif stream_recording and not self.recorder.recording:
                self.recording_start_time = 0
                stream_recording = False

            title = f"ESP32-S3 Camera Viewer — {w}x{h}"
            cv2.setMouseCallback(title, _mouse_callback)
            cv2.imshow(title, frame)
            key = cv2.waitKey(1) & 0xFF
            self.handle_keys(key)

        self.recorder.stop()
        cv2.destroyAllWindows()
        print("Viewer closed.")


# ============================================================
#  HELP
# ============================================================


def print_help():
    print("""
=== ESP32-S3 Camera Viewer Controls ===
 q    - Quit
 s    - Save snapshot
 r    - Toggle recording
    1    - Resolution: SVGA (800x600)
    2    - Resolution: UXGA (1600x1200)
    3    - Resolution: VGA (640x480)
    4    - Resolution: QVGA (320x240)
    5    - Resolution: QQVGA (160x120)
    f    - Toggle face detection
 z    - Toggle QR code reader
 m    - Toggle motion detection
 t    - Toggle telemetry overlay
 o    - Rotate 90° CW (cycles 0/90/180/270)
 g    - Toggle rule-of-thirds grid
 c    - Toggle center crosshair
    l    - Toggle LED on/off
    L    - Flash LED (shift+L)
    p    - Toggle motion trail overlay
    T    - Toggle timestamp overlay (shift+T)
    h    - Show this help
 Dashboard: {BASE_URL}/dashboard
========================================
""")


class MultiCameraViewer:
    """View multiple ESP32 camera streams simultaneously in a grid layout."""

    def __init__(self, urls: list[str]):
        self.urls = urls
        self.clients = [ESP32Client(url) for url in urls]
        self.buffers = [StreamBuffer() for _ in urls]
        self.analyzers = [FrameAnalyzer() for _ in urls]
        self.fps_counters = [FPSCounter() for _ in urls]
        self.latest_frames: list[np.ndarray | None] = [None] * len(urls)
        self.frame_flags = [False] * len(urls)
        self.locks = [threading.Lock() for _ in urls]
        self.running = True
        self.threads = []

    def _capture_loop(self, idx: int):
        url = self.urls[idx]
        buf = self.buffers[idx]
        while self.running:
            try:
                stream = urllib.request.urlopen(url + "/", timeout=3)
                while self.running:
                    data = stream.read(65536)
                    if not data:
                        break
                    buf.feed(data)
                    frame = buf.get_frame()
                    if frame is not None:
                        with self.locks[idx]:
                            self.latest_frames[idx] = frame
                            self.frame_flags[idx] = True
            except Exception:
                pass
            time.sleep(1)

    def run(self):
        for i in range(len(self.urls)):
            t = threading.Thread(target=self._capture_loop, args=(i,), daemon=True)
            t.start()
            self.threads.append(t)
        print(f"Multi-camera: viewing {len(self.urls)} streams")
        while self.running:
            frames = []
            for i in range(len(self.urls)):
                with self.locks[i]:
                    if self.frame_flags[i] and self.latest_frames[i] is not None:
                        frames.append(self.latest_frames[i].copy())
                        self.frame_flags[i] = False
                    else:
                        frames.append(None)
            valid = [f for f in frames if f is not None]
            if not valid:
                cv2.waitKey(50)
                continue
            n = len(self.urls)
            cols = min(3, n)
            rows = (n + cols - 1) // cols
            display_h, display_w = 480, 640
            grid_h, grid_w = display_h * rows, display_w * cols
            grid = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)
            for i, frame in enumerate(frames):
                if frame is None:
                    continue
                r, c = divmod(i, cols)
                h, w = frame.shape[:2]
                scale = min(display_w / w, display_h / h)
                new_w, new_h = int(w * scale), int(h * scale)
                resized = cv2.resize(frame, (new_w, new_h))
                y_off, x_off = r * display_h, c * display_w
                grid[y_off:y_off + new_h, x_off:x_off + new_w] = resized
                cv2.putText(grid, f"Cam {i+1}", (x_off + 8, y_off + 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("ESP32-S3 Multi-Camera View", grid)
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                self.running = False
        cv2.destroyAllWindows()


if __name__ == "__main__":
    if MULTI_IPS:
        urls = [ip.rstrip("/") for ip in MULTI_IPS]
        viewer = MultiCameraViewer(urls)
        viewer.run()
    else:
        print_help()
        viewer = Viewer()
        viewer.run()
