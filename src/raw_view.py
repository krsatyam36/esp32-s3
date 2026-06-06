import cv2
import urllib.request
import urllib.error
import http.client
import socket
import numpy as np
import time
import json
import os
import sys
import argparse
import threading
from datetime import datetime

parser = argparse.ArgumentParser(description="ESP32-S3 Camera Viewer")
parser.add_argument("--ip", type=str, default=None, help="ESP32 IP address (overrides config.py)")
args, _ = parser.parse_known_args()

if args.ip:
    BASE_URL = args.ip.rstrip("/")
else:
    try:
        from config import ESP32_IP
        BASE_URL = ESP32_IP.rstrip("/")
    except ImportError:
        print("ERROR: No config.py found and no --ip provided.")
        print("Copy config.example.py to config.py and set your ESP32 IP, or use --ip")
        sys.exit(1)
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
        a = self.buffer.find(b"\xff\xd8") # Start marker
        b = self.buffer.find(b"\xff\xd9") # End marker
        
        if a != -1 and b != -1:
            if a < b:
                # Perfect frame found! Extract it.
                jpg = self.buffer[a : b + 2]
                self.buffer = self.buffer[b + 2 :]
                img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                return img
            else:
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
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, "Face", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

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
                cv2.line(frame, self.trail_points[i - 1], self.trail_points[i], color, thickness, cv2.LINE_AA)
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
        self.filename = os.path.join(
            self.output_dir,
            f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.avi",
        )
        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
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
        cv2.putText(frame, text, (x + 1, y + 1), ModernHUD.FONT, scale, (0, 0, 0), thick + 1, cv2.LINE_AA)
        cv2.putText(frame, text, (x, y), ModernHUD.FONT, scale, color, thick, cv2.LINE_AA)

    @staticmethod
    def text_sm(frame, text, x, y, color=(255, 255, 255), scale=0.45, thick=1):
        cv2.putText(frame, text, (x + 1, y + 1), ModernHUD.FONT_SM, scale, (0, 0, 0), thick + 1, cv2.LINE_AA)
        cv2.putText(frame, text, (x, y), ModernHUD.FONT_SM, scale, color, thick, cv2.LINE_AA)

    @staticmethod
    def panel(frame, x, y, w, h, alpha=None):
        if alpha is None:
            alpha = ModernHUD.BG_ALPHA
        roi = frame[y:y + h, x:x + w]
        bg = np.full_like(roi, (0, 0, 0), dtype=np.uint8)
        blended = cv2.addWeighted(roi, 1 - alpha, bg, alpha, 0)
        frame[y:y + h, x:x + w] = blended

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

                    except (urllib.error.URLError, ConnectionError,
                            http.client.IncompleteRead, http.client.RemoteDisconnected,
                            socket.timeout):
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
                    ModernHUD.text_with_bg(frame, f"QR: {qr_data}", 12, frame.shape[0] - 14,
                                           (255, 0, 255), 0.55, 2)

            if self.enable_motion:
                motion, thresh = self.analyzer.detect_motion(frame)
                if motion:
                    self.analyzer.draw_motion_contours(frame, thresh if thresh is not None else np.zeros_like(frame))
                    ModernHUD.text_with_bg(frame, "MOTION DETECTED!", frame.shape[1] - 170, 28,
                                           (0, 0, 255), 0.6, 2)

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

if __name__ == "__main__":
    print_help()
    viewer = Viewer()
    viewer.run()