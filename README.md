<div align="center">

# Seeed XIAO ESP32S3 Sense — Edge Intelligence Platform

**v2.3.8** — *Edge intelligence platform: streaming, Vision LLM, semantic search, YOLO gatekeeper, adaptive rate controller, scene classification, activity timeline, object counting, smart alerts, motion heatmap*

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

- 🚀 **Low-latency MJPEG streaming** over WiFi
- 📷 **Snapshot capture** — press `s` or use the dashboard
- 🎥 **Video recording** — toggle with `r`, saves to `recordings/`
- 🔄 **Resolution switching** — `1` (SVGA) / `2` (UXGA) / `3` (VGA) / `4` (QVGA) / `5` (QQVGA)
- 🧑 **Face detection overlay** — toggle with `f`
- 📱 **QR code reader** — toggle with `z`, decodes in real time
- 🏃 **Motion detection** — toggle with `m`, highlights movement
- 💡 **LED control** — toggle with `l`, flash with `L`
- 📊 **Telemetry overlay** — toggle with `t` (heap, uptime, RSSI, temp, PSRAM, IP)
- 🌐 **Web dashboard** — full control UI at `http://localhost:8000`
- 📡 **OTA updates** — upload firmware over WiFi via ArduinoOTA
- 🔁 **Auto WiFi reconnect** — handles disconnects gracefully
- 🤖 **Vision LLM** — stream frames to local Ollama vision models (gemma3, llama3.2-vision, qwen2.5vl) for real-time AI description
- 🎨 **Modern HUD overlay** — drop shadows, translucent dark panels, and feature badges
- 🔄 **Stream rotation** — rotate the view 90°/180°/270° with `o`
- ✚ **Rule-of-thirds grid** — composition aid toggle with `g`
- 🎯 **Center crosshair** — alignment guide toggle with `c`
- ⏱ **Recording timer** — live `MM:SS` counter with red indicator
- 🖥 **Fullscreen mode** — `f` key on the web dashboard
- 🔍 **Semantic search** — natural-language video search via CLIP + ChromaDB
- 👁 **YOLO event gatekeeper** — real-time object detection triggering LLM analysis
- ⚡ **Adaptive rate controller** — auto-adjusts resolution & interval based on RSSI/latency
- ☠️ **Boss Mode** — detects cell phone distraction & roasts you via LLM + TTS
- 🏠 **Scene classification** — real-time scene analysis (indoor/outdoor/night/crowded) using CV heuristics, no ML dependency
- 📋 **Activity timeline** — tracks detection events with duration and creates a searchable timeline
- 🔢 **Object counting** — cumulative detection statistics with top-N class tracking
- 🔔 **Smart alert system** — configurable rules with per-class confidence thresholds and cooldown
- 📈 **Performance metrics history** — ring buffer of FPS/latency/queue depth for real-time charts
- 🌡️ **Motion heatmap** — accumulates motion regions with exponential decay into a visual heatmap
- ❤️ **Health endpoint** — `/ping` for connectivity checks
- 🩺 **Camera diagnostics** — detailed init failure reporting with automatic fallback
- 🔁 **Exponential backoff reconnect** — resilient stream recovery in viewer
- 🖼️ **Frame dimensions** — displayed in viewer window title
- 🧪 **Stream test script** — `stream_test.py` for quick connectivity check
- 🎛️ **CLI arguments** — override IP, port, and model via `--ip` command line argument
- 🧰 **Makefile** — `make viewer`, `make server`, `make vision`, `make test`, `make check` for quick commands
- ✅ **Setup validation** — `python src/check_deps.py` verifies all dependencies and configuration
- 🔄 **Camera flip/mirror** — toggle vertical flip and horizontal mirror from the dashboard
- 🏥 **Diagnostics endpoint** — `/diag` returns full chip info, firmware version, and system health
- 📊 **Aggregated dashboard** — `/dashboard-data` returns all telemetry in a single call
- 📊 **Analytics dashboard** — real-time FPS and latency charts via Chart.js
- 🔄 **Tabbed UI** — organized panels for Dashboard, Analytics, Events, Alerts, and Heatmap
- ⚙️ **Alert rules management** — enable/disable alert rules directly from the web UI

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

### 10. Makefile Commands

A `Makefile` is provided for convenience:

```bash
make viewer        # Run OpenCV viewer (set ESP_IP=http://... to override)
make server        # Run FastAPI web server
make vision        # Run Vision LLM CLI
make test          # Run connectivity test
make upload        # Upload firmware via USB
make ota           # Upload firmware via OTA
make monitor       # Open serial monitor
```

### 11. FastAPI Server (app.py)

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

**Web dashboard features (tabbed UI):**
- Live MJPEG stream with grid overlay & rotation controls
- AI Vision panel with model selector, analysis interval, and real-time LLM results
- YOLO event log showing detected objects with confidence and severity
- Semantic search — search archived frames by natural language
- Adaptive controller status — shows current mode (normal/throttled/emergency)
- ESP32 controls — LED, 6-level resolution, telemetry, snapshots
- **Scene classification** — real-time indoor/outdoor/night/crowded detection
- **Analytics tab** — FPS & latency charts (Chart.js), object detection stats, activity timeline
- **Events tab** — full YOLO detection event log
- **Alerts tab** — configurable alert rules with enable/disable and history
- **Heatmap tab** — motion heatmap visualization with reset

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
| `/system-status` | GET | Full system status with all subsystems |
| `/health` | GET | ESP32 + Ollama connectivity |
| `/telemetry` | GET | ESP32 telemetry proxy (includes IP, chip info) |
| `/led` | POST | Toggle LED |
| `/res` | POST | Set resolution |
| `/models` | GET | Available Ollama models |
| `/ping` | GET | Health check (status, IP, uptime) |
| `/scene` | GET | Current scene classification + history |
| `/timeline` | GET | Activity timeline entries and active events |
| `/stats` | GET | Object counting statistics and top classes |
| `/alerts` | GET | Alert rules, history, and stats |
| `/alerts/{idx}` | PUT/DELETE | Update or delete alert rule |
| `/metrics` | GET | Performance metrics time series |
| `/heatmap` | GET | Motion heatmap as base64 JPEG |
| `/heatmap/reset` | POST | Reset accumulated motion heatmap |
| `/flip` | POST | Toggle camera vflip or hmirror |
| `/diag` | GET | Full ESP32 diagnostics (chip, flash, PSRAM, SDK) |
| `/dashboard-data` | GET | Aggregated telemetry for frontend |

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
| `/` | GET | MJPEG stream |
| `/snapshot` | GET | Single JPEG frame |
| `/res?val=QQVGA|QVGA|VGA|CIF|SVGA|UXGA` | GET | Change camera resolution (6 levels) |
| `/led?state=on|off` | GET | Toggle built-in LED |
| `/flash?count=N` | GET | Flash LED N times (1-20) |
| `/telemetry` | GET | JSON: heap, uptime, RSSI, IP, resolution, PSRAM, total_PSRAM, temperature, chip_id, cpu_freq, camera_init_attempts, framesize |
| `/ping` | GET | Health check: status, uptime, IP |
| `/diag` | GET | Full chip diagnostics: model, cores, flash, PSRAM, SDK, firmware version |
| `/flip?mode=v|h` | GET | Toggle vertical flip (v) or horizontal mirror (h) |
| `/dashboard` | GET | Full web dashboard (embedded) |

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
.
├── Makefile                 # Common dev commands (`make viewer`, etc.)
├── platformio.ini           # Board & PSRAM configuration
├── README.md                # This documentation
├── recordings/              # Captured video storage
├── snapshots/               # Captured image storage
├── chroma_db/               # ChromaDB persistent store (gitignored)
├── test/                    # PlatformIO test runner
├── testing/                 # Manual test documentation
├── include/                 # C++ firmware headers
│   ├── camera_utils.h       # Camera init, diagnostics, 6-level resolution
│   ├── wifi_manager.h       # WiFi connect with auto-reconnect
│   ├── ota_manager.h        # Over-the-air updates
│   ├── web_server.h         # HTTP server + all API handlers (incl. /ping)
│   └── dashboard_html.h     # Embedded web dashboard HTML
├── src/                     # Python host apps + firmware source
│   ├── app.py               # FastAPI server (Edge Intelligence Platform v2.3.8)
│   ├── raw_view.py          # Feature-rich Python viewer (with --ip CLI arg)
│   ├── vision_llm.py        # Live feed → Ollama vision LLM (with --ip CLI arg)
│   ├── stream_test.py       # Connectivity test script
│   ├── check_deps.py        # Dependency and config validator
│   ├── index.html           # Web dashboard with tabbed UI and charts
│   ├── config.py            # Your local IP (gitignored)
│   ├── config.example.py    # Template — copy to config.py & set IP
│   ├── config.h             # WiFi credentials (gitignored)
│   ├── config.example.h     # Template — copy to config.h & set WiFi
│   ├── main.cpp             # ESP32 firmware entry point (v2.3.8 with diagnostics)
│   ├── api_utils.py         # Shared API utilities
│   ├── ai/                  # AI modules
│   │   ├── __init__.py
│   │   ├── event_gatekeeper.py
│   │   ├── motion_heatmap.py
│   │   ├── object_counter.py
│   │   ├── ollama_analyzer.py
│   │   ├── scene_classifier.py
│   │   ├── smart_alert.py
│   │   ├── timeline_engine.py
│   │   └── vector_search.py
│   └── core/                # Core modules
│       ├── __init__.py
│       ├── adaptive_controller.py
│       ├── camera_capture.py
│       ├── esp32_client.py
│       ├── metrics_history.py
│       └── stream_buffer.py
├── esp32-s3/                # Older project version (reference)
│   ├── Makefile
│   ├── app.py
│   ├── raw_view.py
│   ├── vision_llm.py
│   ├── stream_test.py
│   ├── index.html
│   ├── platformio.ini
│   ├── include/
│   └── src/
│       ├── config.example.h
│       └── main.cpp
├── Dockerfile               # Docker image for app.py
├── docker-compose.yml       # Docker Compose for app.py + Ollama
├── requirements.txt         # Python dependencies
├── requirements-dev.txt     # Dev dependencies
├── pyproject.toml           # Python project metadata
├── .gitignore               # Git ignore rules
├── .github/workflows/
│   ├── ci.yml               # CI workflow
│   ├── codeql.yml           # CodeQL analysis
│   ├── docker.yml           # Docker build
│   ├── firmware.yml         # Firmware build
│   ├── labeler.yml          # PR labeler
│   └── stale.yml            # Stale issue management
└── CHANGELOG.md             # Release history
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
