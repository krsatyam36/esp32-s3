<div align="center">

# Seeed XIAO ESP32S3 Sense — Edge Intelligence Platform

**v2.2.0** — *Edge intelligence platform: streaming, Vision LLM, semantic search, YOLO gatekeeper, adaptive rate controller, scene classification, activity timeline, object counting, smart alerts, motion heatmap*

[![PlatformIO](https://img.shields.io/badge/PlatformIO-6.1+-F58220?style=flat&logo=platformio&logoColor=white)](https://platformio.org)
[![ESP32](https://img.shields.io/badge/ESP32-S3-E7352C?style=flat&logo=espressif&logoColor=white)](https://www.espressif.com)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=flat&logo=opencv&logoColor=white)](https://opencv.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Arduino](https://img.shields.io/badge/Arduino-Framework-00979D?style=flat&logo=arduino&logoColor=white)](https://www.arduino.cc)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-000?style=flat&logo=ollama&logoColor=white)](https://ollama.ai)
[![CI](https://github.com/krsatyam36/esp32-s3/actions/workflows/ci.yml/badge.svg)](https://github.com/krsatyam36/esp32-s3/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker&logoColor=white)](https://docker.com)

**Firmware and Python suite for low‑latency MJPEG streaming from the Seeed XIAO ESP32S3 Sense, with AI-powered features.**

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Prerequisites](#system-prerequisites)
- [Installation & Setup](#installation--setup)
  - [Step 0: Clone the Repository](#step-0-clone-the-repository)
  - [Step 1: Virtual Environment Setup](#step-1-virtual-environment-setup)
  - [Step 2: Install Python Dependencies](#step-2-install-python-dependencies)
  - [Step 3: Configure WiFi Credentials](#step-3-configure-wifi-credentials)
  - [Step 4: Upload Firmware to ESP32](#step-4-upload-firmware-to-esp32)
- [Running the Stream](#running-the-stream)
  - [Step 5: Get the IP Address](#step-5-get-the-ip-address)
  - [Step 6: Run the Python Viewer](#step-6-run-the-python-viewer)
  - [Step 7: Use the Web Dashboard](#step-7-use-the-web-dashboard)
  - [Step 8: OTA Firmware Updates](#step-8-ota-firmware-updates)
  - [Step 9: Vision LLM](#step-9-vision-llm)
  - [Step 10: FastAPI Server](#step-10-fastapi-server-apppy)
- [Boss Mode](#boss-mode)
- [How It Works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Project Structure with File Locations](#project-structure-with-file-locations)

---

## Overview

This repository turns a blank **Ubuntu** system into a full edge intelligence platform for the **Seeed XIAO ESP32S3 Sense** camera.

It includes:

- **Arduino firmware** (uploaded via PlatformIO) that captures frames and serves an MJPEG stream over WiFi.
- **FastAPI server** (`src/app.py`) — web dashboard with Vision LLM, YOLO gatekeeper, semantic search, and adaptive rate control.
- **Standalone Python viewer** (`src/raw_view.py`) — feature-rich OpenCV viewer with face/QR/motion detection, recording, and HUD.
- **Vision LLM CLI** (`src/vision_llm.py`) — stream frames to local Ollama vision models for real-time AI description.

## Features

| Feature | File | Description |
|---------|------|-------------|
| Low-latency MJPEG streaming | `include/web_server.h` | Serves MJPEG over WiFi on port 80 |
| Snapshot capture | `include/web_server.h` | Press `s` or use dashboard to save JPEG |
| Video recording | `src/raw_view.py` | Toggle with `r`, saves to `recordings/` |
| Resolution switching | `include/camera_utils.h` | 6 levels: QQVGA to UXGA |
| Face detection | `src/raw_view.py` | Toggle with `f` |
| QR code reader | `src/raw_view.py` | Toggle with `z`, decodes in real-time |
| Motion detection | `src/raw_view.py` | Toggle with `m`, highlights movement |
| LED control | `include/web_server.h` | Toggle with `l`, flash with `L` |
| Telemetry overlay | `include/web_server.h` | Heap, uptime, RSSI, temp, PSRAM, IP |
| Web dashboard | `src/index.html` | Full control UI at `http://localhost:8000` |
| OTA updates | `include/ota_manager.h` | Upload firmware over WiFi |
| Auto WiFi reconnect | `include/wifi_manager.h` | Handles disconnects gracefully |
| Vision LLM | `src/vision_llm.py` | Ollama vision models for AI description |
| Semantic search | `src/ai/vector_search.py` | Natural-language video search via CLIP + ChromaDB |
| YOLO event gatekeeper | `src/ai/event_gatekeeper.py` | Real-time object detection triggering LLM |
| Adaptive rate controller | `src/core/adaptive_controller.py` | Auto-adjusts resolution based on RSSI/latency |
| Boss Mode | `src/app.py` | Detects phone distraction, roasts you via LLM + TTS |
| Scene classification | `src/ai/scene_classifier.py` | Real-time indoor/outdoor/night/crowded analysis |
| Activity timeline | `src/ai/timeline_engine.py` | Tracks detection events with duration |
| Object counting | `src/ai/object_counter.py` | Cumulative stats with top-N class tracking |
| Smart alerts | `src/ai/smart_alert.py` | Configurable rules with thresholds and cooldown |
| Motion heatmap | `src/ai/motion_heatmap.py` | Accumulates motion with exponential decay |
| Performance metrics | `src/core/metrics_history.py` | Ring buffer of FPS/latency/queue depth |
| Health checks | `include/web_server.h` | `/ping` endpoint for connectivity |
| Camera diagnostics | `include/camera_utils.h` | Detailed init failure reporting with fallback |

## System Prerequisites

- **Ubuntu** (or any Debian‑based Linux with `apt`).
- **USB‑C data cable** — must support data transfer, not just charging.
- **Local WiFi network** (2.4 GHz).
- **Seeed XIAO ESP32S3 Sense** board.

---

## Installation & Setup

### Step 0: Clone the Repository

```bash
# Clone the repo to your machine
cd ~
git clone https://github.com/krsatyam36/esp32-s3.git Projects/xiao
cd Projects/xiao
```

> All paths in this guide assume you are inside the `~/Projects/xiao/` directory.

---

### Step 1: Virtual Environment Setup

Create a Python virtual environment to isolate dependencies.

**What this does:** A virtual environment keeps project libraries separate from your system Python, avoiding version conflicts.

```bash
# 1. Install the venv package (if not already installed)
sudo apt update
sudo apt install python3-venv -y

# 2. Create a virtual environment at ~/vir_esp32SENSEenv
python3 -m venv ~/vir_esp32SENSEenv

# 3. Activate it (run this every time you open a new terminal for this project)
source ~/vir_esp32SENSEenv/bin/activate
```

**Verify:** Your terminal prompt should now begin with `(vir_esp32SENSEenv)`.

> **Important:** Keep the virtual environment active for all subsequent Python commands.

---

### Step 2: Install Python Dependencies

With the virtual environment active, install PlatformIO and required Python libraries.

```bash
# Make sure you're in the project root: ~/Projects/xiao
# and the virtual env is active

# Install all dependencies at once (recommended)
pip install platformio opencv-python numpy fastapi uvicorn requests

# Optional extras:
pip install ultralytics          # YOLO event gatekeeper
pip install chromadb sentence-transformers torch   # Semantic search
```

**For Boss Mode TTS (text-to-speech):**
```bash
sudo apt install espeak -y
```

**Verify installation:**
```bash
python src/check_deps.py
```

---

### Step 3: Configure WiFi Credentials

The firmware needs your WiFi SSID and password to connect. You MUST create `src/config.h` before uploading.

**What happens:** The firmware's `include/wifi_manager.h` reads `ssid` and `password` from `src/config.h`. If `src/config.h` doesn't exist, compilation fails with:

```
error: 'ssid' was not declared in this scope
```

**How to fix it:**

**Option A — Copy the template:**

```bash
cp src/config.example.h src/config.h
```

Then edit `src/config.h` with your WiFi credentials.

**Option B — Use the pre-configured file:**

If `src/config.h` already exists (created by the setup), it already has your credentials — no action needed.

If you need to create your own (different WiFi):

```bash
# Copy the template
cp src/config.example.h src/config.h

# Edit with your credentials
nano src/config.h
```

The file at `src/config.h` should contain:

```cpp
#pragma once

const char* ssid = "YourWiFiSSID";
const char* password = "YourWiFiPassword";
```

**Security:** `src/config.h` is listed in `.gitignore` — your credentials will never be committed to git.

---

### Step 4: Upload Firmware to ESP32

Connect the XIAO ESP32S3 Sense to your computer using a **data-capable USB-C cable**.

**Upload the firmware:**

```bash
pio run -t upload
```

**Troubleshooting if upload fails:**

| Problem | Check |
|---------|-------|
| `Failed to connect` | Try a different USB port or cable |
| `Not a PlatformIO project` | Make sure you're in `~/Projects/xiao/` (where `platformio.ini` lives) |
| `A fatal error occurred` | Hold the BOOT button on the XIAO, then press RESET, then try again |

**If the camera doesn't work after upload:** Double-check that `-DBOARD_HAS_PSRAM` is in `platformio.ini` (lines 11-14). Without PSRAM, the camera buffer fails.

---

## Running the Stream

### Step 5: Get the IP Address

Open the serial monitor to see what IP the ESP32 gets from your router:

```bash
pio device monitor
```

Wait 5-10 seconds. You should see output ending with:

```
Stream Ready at: http://192.168.1.X/
```

**Copy that IP address** (e.g., `192.168.1.42`), then press **Ctrl+C** to exit the monitor.

**If you see `WiFi connection failed` instead:**
- Verify SSID and password in `src/config.h`
- Make sure you're on a 2.4 GHz network (ESP32 doesn't support 5 GHz)
- Check that your router allows new device connections

---

### Step 6: Run the Python Viewer

The viewer (`src/raw_view.py`) manually buffers raw JPEG bytes from the ESP32, which is more reliable than OpenCV's `VideoCapture`.

**Method 1 — Create a config file (one-time setup):**

```bash
# Copy the template (creates src/config.py)
cp src/config.example.py src/config.py

# Edit with your ESP32's IP address
nano src/config.py
```

Set the IP:

```python
ESP32_IP = "http://192.168.1.X/"
```

Then run:

```bash
python src/raw_view.py
```

**Method 2 — Pass IP on the command line (no config file needed):**

```bash
python src/raw_view.py --ip http://192.168.1.X/
```

**Method 3 — Use the Makefile:**

```bash
make viewer ESP_IP=http://192.168.1.X/
```

**Keyboard controls in the viewer window:**

| Key | Action |
|-----|--------|
| `q` | Quit |
| `s` | Save snapshot to `snapshots/` |
| `r` | Toggle video recording to `recordings/` |
| `1` | SVGA (800×600) |
| `2` | UXGA (1600×1200) |
| `3` | VGA (640×480) |
| `4` | QVGA (320×240) |
| `5` | QQVGA (160×120) |
| `f` | Toggle face detection |
| `z` | Toggle QR code reader |
| `m` | Toggle motion detection |
| `t` | Toggle telemetry overlay |
| `o` | Rotate stream 90° CW |
| `g` | Toggle rule-of-thirds grid |
| `c` | Toggle center crosshair |
| `l` | Toggle built-in LED |
| `L` | Flash LED 5 times |
| `h` | Show help overlay |

> **Linux users:** If you see `QFontDatabase: Cannot find font directory` — it's harmless, ignore it.

---

### Step 7: Use the Web Dashboard

The ESP32 serves an embedded web dashboard. Open your browser to:

```
http://192.168.1.X/dashboard
```

**Dashboard keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `s` | Take snapshot |
| `r` | Rotate stream right |
| `0` | Reset rotation |
| `g` | Toggle grid overlay |
| `l` | LED on |
| `L` | Flash LED |
| `n` | Force AI analysis |
| `1`–`6` | Set resolution (QQVGA..UXGA) |
| `Esc` | Exit fullscreen |

---

### Step 8: OTA Firmware Updates

Once the board is on WiFi, you can upload firmware **over the air** without USB:

```bash
pio run -t upload --upload-port 192.168.1.X
```

The board identifies itself as `xiao-esp32s3-cam` on the network.

**OTA via Makefile:**
```bash
make ota ESP_IP=http://192.168.1.X/
```

---

### Step 9: Vision LLM

Stream the camera feed to a local Ollama vision model for real-time AI description.

**Prerequisites:**

```bash
# Install Ollama (if not already)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a vision model
ollama pull gemma3:latest
# Alternatives: llama3.2-vision, llava:7b, qwen2.5vl:7b
```

**Run the vision CLI:**

```bash
python src/vision_llm.py --ip http://192.168.1.X/
```

**Or via Makefile:**
```bash
make vision ESP_IP=http://192.168.1.X/
```

**Controls in the vision window:**

| Key | Action |
|-----|--------|
| `q` | Quit |
| `a` | Toggle auto-analysis |
| `n` | Analyze current frame now |
| `o` | Rotate stream 90° CW |
| `g` | Toggle grid overlay |
| `h` | Show help |

---

### Step 10: FastAPI Server (app.py)

The full FastAPI server provides a web dashboard with ALL AI features:

```bash
python src/app.py --ip http://192.168.1.X/ --port 8000
```

**Or via Makefile:**
```bash
make server
```

Open **http://localhost:8000** in your browser.

**Web dashboard tabs:**
- **Dashboard** — Live stream, LED/resolution controls, telemetry
- **Analytics** — FPS & latency charts (Chart.js), object stats, timeline
- **Events** — YOLO detection event log
- **Alerts** — Alert rules management (enable/disable, thresholds)
- **Heatmap** — Motion heatmap visualization (with reset button)

**REST API endpoints** (all prefixed with `http://localhost:8000`):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/stream` | GET | MJPEG stream from ESP32 |
| `/analysis` | GET | SSE stream of LLM analysis |
| `/analyze-now` | POST | Force immediate LLM analysis |
| `/model` | POST | Set Ollama model |
| `/interval` | POST | Set analysis interval |
| `/events` | GET | YOLO detection events |
| `/search` | GET/POST | Semantic search |
| `/system-status` | GET | Full system status |
| `/health` | GET | ESP32 + Ollama connectivity |
| `/telemetry` | GET | ESP32 telemetry proxy |
| `/led` | POST | Toggle LED |
| `/res` | POST | Set resolution |
| `/models` | GET | Available Ollama models |
| `/ping` | GET | Health check |
| `/scene` | GET | Scene classification |
| `/timeline` | GET | Activity timeline |
| `/stats` | GET | Object counting stats |
| `/alerts` | GET | Alert rules |
| `/alerts/{idx}` | PUT/DELETE | Update/delete alert |
| `/metrics` | GET | Performance metrics |
| `/heatmap` | GET | Motion heatmap (base64 JPEG) |
| `/heatmap/reset` | POST | Reset heatmap |
| `/flip` | POST | Toggle vflip/hmirror |
| `/diag` | GET | Full ESP32 diagnostics |
| `/dashboard-data` | GET | Aggregated telemetry |

---

## Boss Mode

> ☠️ **When YOLO detects a cell phone in the frame for more than 5 seconds, the system roasts you.**

Block your own distractions:

1. **YOLO gatekeeper** (`src/ai/event_gatekeeper.py`) tracks cell phone detections continuously.
2. If a phone is in frame for **≥ 5 seconds**, it activates boss mode.
3. **Ollama** receives the frame with a toxic system prompt and roasts you.
4. The roast appears on the dashboard as **huge red text** with shake animation.
5. **espeak** yells the roast through your speakers.

**Requirements:**

```bash
sudo apt install espeak -y
```

---

## How It Works

### Architecture

```
┌─────────────────────┐     WiFi MJPEG      ┌────────────────────┐
│   ESP32-S3 Firmware │ ◄──────────────────► │   Python Host Apps │
│                     │     HTTP API         │                    │
│  include/           │                      │  src/raw_view.py   │
│  ├─ web_server.h    │                      │  src/vision_llm.py │
│  ├─ wifi_manager.h  │                      │  src/app.py        │
│  ├─ camera_utils.h  │                      │  src/ai/*.py       │
│  └─ ota_manager.h   │                      │  src/core/*.py     │
└─────────────────────┘                      └────────────────────┘
```

### Why a custom viewer?

OpenCV's `VideoCapture` uses a tight internal timeout and single-threaded execution. Even small WiFi delays cause it to throw errors or freeze.

**Our approach in `src/raw_view.py`:**
1. **Multi-threaded Capture** — background thread handles all network I/O
2. **Self-Healing Buffer** — detects and discards corrupted JPEG data
3. **Real-time Sync** — flushes buffer to always show the newest frame
4. **Non-blocking Decode** — only complete JPEG frames reach the display

### ESP32 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `http://IP/` | GET | MJPEG stream |
| `http://IP/snapshot` | GET | Single JPEG frame |
| `http://IP/res?val=UXGA` | GET | Set resolution |
| `http://IP/led?state=on` | GET | Toggle LED |
| `http://IP/flash?count=5` | GET | Flash LED |
| `http://IP/telemetry` | GET | JSON telemetry |
| `http://IP/ping` | GET | Health check |
| `http://IP/diag` | GET | Full diagnostics |
| `http://IP/flip?mode=v` | GET | Toggle flip/mirror |
| `http://IP/dashboard` | GET | HTML dashboard |

---

## Troubleshooting

| Problem | Likely Cause | File to Check | Solution |
|---------|-------------|--------------|----------|
| `'ssid' was not declared` | `src/config.h` missing | `src/config.h` | `cp src/config.example.h src/config.h` and fill credentials |
| `LED_BUILTIN redefined` | Duplicate define in `web_server.h` | `include/web_server.h:11` | Already fixed — uses `#ifndef` guard now |
| Camera stream blank | PSRAM not enabled | `platformio.ini` | Ensure `-DBOARD_HAS_PSRAM` is in `build_flags` |
| Upload fails | Bad USB cable or port | — | Use a data cable; try different USB port |
| No serial output | Wrong baud rate | `platformio.ini` | `monitor_speed = 115200` |
| `Stream Ready` never appears | Wrong WiFi credentials | `src/config.h` | Verify SSID/password; use 2.4 GHz |
| `QFontDatabase` warning | Missing desktop fonts | — | Harmless, ignore it |
| OTA upload fails | Board unreachable | — | Same network? Check IP is correct |
| Vision LLM can't connect | Ollama not running | — | `ollama serve` then `ollama list` |
| Vision model slow | Large model on CPU | — | Use `llava:7b` or increase interval |
| Camera init fails repeatedly | PSRAM or power issue | `include/camera_utils.h` | Firmware auto-retries with VGA fallback |
| Viewer reconnects slowly | Network latency | `src/raw_view.py` | Exponential backoff — retries up to 3 times |
| Need to test connectivity | Quick check | `src/stream_test.py` | `python src/stream_test.py http://IP/` |

---

## Project Structure with File Locations

```
~/Projects/xiao/
├── platformio.ini                 # Board config, PSRAM flags, upload speed
├── Makefile                       # `make viewer`, `make server`, `make upload`, etc.
├── README.md                      # This file
│
├── include/                       # C++ firmware headers
│   ├── camera_utils.h             #   Camera init(`initCamera()`), 6-level resolution (`setResolution()`)
│   ├── wifi_manager.h             #   WiFi connect (`connectWiFi()`), auto-reconnect (`handleWiFi()`)
│   ├── ota_manager.h              #   Over-the-air update handler (`setupOTA()`, `handleOTA()`)
│   ├── web_server.h               #   HTTP server + all API handlers (stream, snapshot, LED, telemetry, ping, diag, flip, dashboard)
│   └── dashboard_html.h           #   Embedded HTML dashboard (served at /dashboard)
│
├── src/                           # Python host apps + firmware source
│   ├── main.cpp                   #   ESP32 firmware entry point: setup() → initCamera → connectWiFi → setupOTA → startWebServer
│   ├── config.h                   #   ← YOUR WIFI CREDENTIALS HERE (gitignored)
│   ├── config.example.h           #   Template — copy to config.h
│   ├── config.py                  #   ← YOUR ESP32 IP HERE (gitignored)
│   ├── config.example.py          #   Template — copy to config.py
│   ├── app.py                     #   FastAPI server (v2.1.0 Edge Intelligence Platform)
│   ├── raw_view.py                #   Feature-rich OpenCV viewer (--ip CLI arg supported)
│   ├── vision_llm.py              #   Live feed → Ollama vision LLM
│   ├── stream_test.py             #   Connectivity test script
│   ├── check_deps.py              #   Dependency and config validator
│   ├── index.html                 #   Web dashboard HTML (tabbed UI + Chart.js)
│   ├── api_utils.py               #   Shared API utilities
│   │
│   ├── ai/                        #   AI modules
│   │   ├── __init__.py
│   │   ├── event_gatekeeper.py    #     YOLO object detection + LLM trigger
│   │   ├── motion_heatmap.py      #     Motion accumulation with exponential decay
│   │   ├── object_counter.py      #     Cumulative detection stats
│   │   ├── ollama_analyzer.py     #     Ollama vision LLM client
│   │   ├── scene_classifier.py    #     Indoor/outdoor/night/crowded heuristics
│   │   ├── smart_alert.py         #     Configurable alert rules
│   │   ├── timeline_engine.py     #     Activity timeline + duration tracking
│   │   └── vector_search.py       #     CLIP + ChromaDB semantic search
│   │
│   └── core/                      #   Core modules
│       ├── __init__.py
│       ├── adaptive_controller.py #     Auto-adjusts resolution/interval by RSSI
│       ├── camera_capture.py      #     Frame capture thread for server
│       ├── esp32_client.py        #     HTTP client to ESP32 endpoints
│       ├── metrics_history.py     #     Ring buffer of FPS/latency/queue depth
│       └── stream_buffer.py       #     Thread-safe JPEG buffer with flushing
│
├── esp32-s3/                      # Older project version (reference, kept for migration)
│   ├── platformio.ini
│   ├── Makefile
│   ├── include/                   #   C++ headers (identical to root include/)
│   │   ├── camera_utils.h
│   │   ├── wifi_manager.h
│   │   ├── ota_manager.h
│   │   ├── web_server.h
│   │   └── dashboard_html.h
│   ├── src/
│   │   ├── main.cpp
│   │   ├── config.h               #   WiFi credentials (copy of root src/config.h)
│   │   └── config.example.h
│   ├── app.py
│   ├── raw_view.py
│   ├── vision_llm.py
│   ├── stream_test.py
│   └── index.html
│
├── recordings/                    # Video recordings directory (created at runtime, gitignored)
├── snapshots/                     # Snapshot images directory (created at runtime, gitignored)
├── chroma_db/                     # ChromaDB persistent store (gitignored)
│
├── test/                          # PlatformIO test runner
├── testing/                       # Manual test documentation
├── tests/                         # Python unit tests
├── snapshots/                     # Old recordings
├── recordings/                    # Old recordings
│
├── requirements.txt               # Python dependencies
├── requirements-dev.txt           # Dev dependencies (ruff, mypy, pytest)
├── pyproject.toml                 # Python project metadata
├── py.typed                       # PEP 561 marker
├── ruff.toml                      # Ruff linter config
├── mypy.ini                       # Mypy type checker config
├── pytest.ini                     # Pytest config
├── .coveragerc                    # Coverage config
├── .python-version                # pyenv Python version
├── .env.example                   # Environment variables template
├── .pre-commit-config.yaml        # Pre-commit hooks
├── .gitignore                     # Git ignore rules
│
├── Dockerfile                     # Docker image for app.py
├── docker-compose.yml             # Docker Compose for app.py + Ollama
│
├── CHANGELOG.md                   # Release history
├── CODE_OF_CONDUCT.md             # Community guidelines
├── CONTRIBUTING.md                # Contribution guide
├── SECURITY.md                    # Security policy
└── .github/workflows/ci.yml       # GitHub Actions CI
```

---

<div align="center">

| Command | What it does |
|---------|-------------|
| `make viewer ESP_IP=http://IP/` | Run OpenCV viewer |
| `make server` | Run FastAPI server |
| `make vision ESP_IP=http://IP/` | Run Vision LLM |
| `make test ESP_IP=http://IP/` | Connectivity test |
| `make check` | Validate dependencies |
| `make upload` | Upload firmware via USB |
| `make ota ESP_IP=http://IP/` | Upload firmware via OTA |
| `make monitor` | Open serial monitor |
| `make lint` | Run ruff linter |
| `make typecheck` | Run mypy type checker |
| `make pytest` | Run Python tests |
| `make docker-build` | Build Docker image |
| `make docker-run` | Run Docker container |

Built with ❤️ for reliable ESP32 video streaming
Contributions and improvements welcome!

</div>
