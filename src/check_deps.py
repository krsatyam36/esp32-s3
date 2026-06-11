"""
ESP32-S3 Setup Validation Script.
Checks all dependencies and configuration are correct.
"""

import importlib
import subprocess
from pathlib import Path

REQUIRED_PYTHON = [
    "cv2",
    "numpy",
    "requests",
    "fastapi",
    "uvicorn",
]

OPTIONAL_PYTHON = [
    ("ultralytics", "YOLO event gatekeeper"),
    ("chromadb", "Semantic video search"),
    ("sentence_transformers", "CLIP embeddings"),
    ("torch", "PyTorch (required by sentence-transformers)"),
]

REQUIRED_SYSTEM = [
    ("espeak", "Boss Mode TTS"),
]

HEADLESS_WARNING = False

REQUIRED_FILES = [
    "src/config.py",
    "src/config.h",
]


def check_python(name, label=None):
    try:
        importlib.import_module(name)
        return True, ""
    except ImportError:
        return False, label or name


def check_system(cmd):
    try:
        subprocess.run(["which", cmd], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main():
    print("=" * 56)
    print("  ESP32-S3 Edge Intelligence — Setup Validation")
    print("=" * 56)

    # PlatformIO
    print("\n[1/5] PlatformIO")
    try:
        result = subprocess.run(["pio", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"  [OK] {result.stdout.strip()}")
        else:
            print("  [FAIL] PlatformIO not found. Run: pip install platformio")
    except FileNotFoundError:
        print("  [FAIL] PlatformIO not found. Run: pip install platformio")

    # Python deps
    print("\n[2/5] Python Dependencies")
    all_ok = True
    for name in REQUIRED_PYTHON:
        ok, _ = check_python(name)
        if ok:
            print(f"  [OK] {name}")
        else:
            print(f"  [FAIL] {name} — run: pip install {name}")
            all_ok = False
    if all_ok:
        print("  All required packages installed.")
    try:
        import cv2
        try:
            cv2.namedWindow("test", cv2.WINDOW_NORMAL)
            cv2.destroyWindow("test")
            print("  [OK] OpenCV GUI (window support available)")
        except cv2.error:
            print("  [--] OpenCV GUI unavailable (headless environment)")
            HEADLESS_WARNING = True
    except ImportError:
        pass

    print("\n[3/5] Optional Python Dependencies")
    for name, purpose in OPTIONAL_PYTHON:
        ok, _ = check_python(name)
        status = "[OK]" if ok else "[--]"
        print(f"  {status} {name} ({purpose})")

    # Docker environment check
    is_docker = Path("/.dockerenv").exists() or Path("/proc/1/cgroup").read_text().find("docker") != -1 if Path("/proc/1/cgroup").exists() else False
    if is_docker:
        print("  [INFO] Running inside Docker container")

    # System deps
    print("\n[4/5] System Dependencies")
    for cmd, purpose in REQUIRED_SYSTEM:
        if check_system(cmd):
            print(f"  [OK] {cmd} ({purpose})")
        else:
            print(f"  [--] {cmd} ({purpose}) — run: sudo apt install {cmd}")

    # Config files
    print("\n[5/5] Configuration Files")
    root = Path(__file__).resolve().parent.parent

    config_py = root / "src" / "config.py"
    if config_py.exists():
        print("  [OK] src/config.py found")
        try:
            with open(config_py) as f:
                content = f.read()
            if "192.168" in content:
                print("  [!!] src/config.py still has default IP (192.168.1.X)")
            else:
                print("  [OK] src/config.py has custom IP configured")
        except Exception:
            pass
    else:
        print("  [FAIL] src/config.py not found! Copy from src/config.example.py")

    dot_env = root / ".env"
    if dot_env.exists():
        print("  [OK] .env file found")
    else:
        print("  [INFO] .env not present — using env vars or config.py")

    config_h = root / "src" / "config.h"
    if config_h.exists():
        print("  [OK] src/config.h found")
    else:
        alt = root / "include" / "config.h"
        if alt.exists():
            print("  [OK] include/config.h found (legacy location)")
        else:
            print("  [FAIL] src/config.h not found! Copy from src/config.example.h")

    print("\n" + "=" * 56)
    print("  Validation complete.")
    print("=" * 56)


if __name__ == "__main__":
    main()
