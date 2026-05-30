import cv2
import urllib.request
import urllib.error
import numpy as np
import time
import json
import os
import threading
from datetime import datetime
from config import ESP32_IP

BASE_URL = ESP32_IP.rstrip("/")
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
        for c in contours:
            if cv2.contourArea(c) > self.motion_threshold:
                x, y, w, h = cv2.boundingRect(c)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

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
        lines = [
            f"HEAP: {self.data.get('heap', '--')}",
            f"Up: {self.data.get('uptime', '--')}s",
            f"RSSI: {self.data.get('rssi', '--')} dBm",
            f"Res: {self.data.get('resolution', '--')}",
            f"PSRAM: {self.data.get('free_psram', '--')}",
            f"Temp: {self.data.get('temperature', '--')} C",
        ]
        y = 60
        for line in lines:
            cv2.putText(frame, line, (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
            y += 18

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

        # Threading synchronization variables
        self.latest_frame = None
        self.new_frame_ready = False  
        self.frame_lock = threading.Lock()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)

    def draw_status_bar(self, frame: np.ndarray):
        parts = [f"FPS: {self.fps.smooth_fps:.1f}"]
        if self.recorder.recording: parts.append("REC")
        if self.enable_face: parts.append("FACE")
        if self.enable_qr: parts.append("QR")
        if self.enable_motion: parts.append("MOTION")
        if self.show_telemetry: parts.append("TELE")

        bar = " | ".join(parts)
        cv2.putText(frame, bar, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

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
        elif key == ord("f"):
            self.enable_face = not self.enable_face
        elif key == ord("z"):
            self.enable_qr = not self.enable_qr
        elif key == ord("m"):
            self.enable_motion = not self.enable_motion
        elif key == ord("t"):
            self.show_telemetry = not self.show_telemetry
        elif key == ord("l"):
            self.led_on = not self.led_on
            self.client.toggle_led("on" if self.led_on else "off")
        elif key == ord("L"):
            self.client.flash_led(5)

    def _capture_loop(self):
        """Background thread dedicated entirely to network streaming."""
        print(f"Connecting to {BASE_URL}...")
        try:
            stream = self.client.get_stream()
        except Exception as e:
            print(f"CRITICAL ERROR: {e}\nCheck if the board is on and the IP is correct.")
            self.running = False
            return

        print("Connected! Streaming started...\n")

        while self.running:
            try:
                # 64KB chunks to prevent socket bottlenecks on high-res frames
                data = stream.read(65536)
                if not data:
                    time.sleep(0.1)
                    continue
                
                self.buffer.feed(data)
                
                # Flush the queue: Keep extracting frames until the buffer is empty. 
                # We only want to pass the absolute newest one to the UI.
                while True:
                    frame = self.buffer.get_frame()
                    if frame is None:
                        break 
                    
                    with self.frame_lock:
                        self.latest_frame = frame
                        self.new_frame_ready = True

            except urllib.error.URLError:
                print("Connection lost, reconnecting...")
                try:
                    stream = self.client.get_stream()
                except:
                    time.sleep(1)
            except Exception as e:
                # If ANY error happens (like a timeout), re-initialize the stream
                print(f"Stream error: {e}. Attempting to reconnect...")
                try:
                    stream = self.client.get_stream()
                except Exception as reconnect_error:
                    print(f"Reconnect failed: {reconnect_error}")
                    time.sleep(1)

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

            if self.enable_face and fps_val > 0:
                faces = self.analyzer.detect_faces(frame)
                self.analyzer.draw_face_boxes(frame, faces)

            if self.enable_qr:
                qr_data = self.analyzer.read_qr(frame)
                if qr_data:
                    cv2.putText(frame, f"QR: {qr_data}", (10, frame.shape[0] - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

            if self.enable_motion:
                motion, thresh = self.analyzer.detect_motion(frame)
                if motion:
                    self.analyzer.draw_motion_contours(frame, thresh or np.zeros_like(frame))
                    cv2.putText(frame, "MOTION", (frame.shape[1] - 120, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            if self.show_telemetry:
                self.telemetry.update()
                self.telemetry.draw(frame)

            self.draw_status_bar(frame)

            if not stream_recording and self.recorder.recording:
                self.recorder.start(frame)
                stream_recording = True
            elif stream_recording and self.recorder.recording:
                self.recorder.write_frame(frame)
            elif stream_recording and not self.recorder.recording:
                stream_recording = False

            cv2.imshow("ESP32-S3 Camera Viewer", frame)
            
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
 f    - Toggle face detection
 z    - Toggle QR code reader
 m    - Toggle motion detection
 t    - Toggle telemetry overlay
 l    - Toggle LED on/off
 L    - Flash LED (shift+L)
 h    - Show this help
 Dashboard: {BASE_URL}/dashboard
=========================================
""")

if __name__ == "__main__":
    print_help()
    viewer = Viewer()
    viewer.run()