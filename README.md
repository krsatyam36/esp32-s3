<div align="center">

# Seeed XIAO ESP32S3 Sense — Low Latency Streamer

**v1.0.0** — *Robust, low-latency video streaming from ESP32S3 Sense camera over WiFi*

[![PlatformIO](https://img.shields.io/badge/PlatformIO-6.1+-F58220?style=flat&logo=platformio&logoColor=white)](https://platformio.org)
[![ESP32](https://img.shields.io/badge/ESP32-S3-E7352C?style=flat&logo=espressif&logoColor=white)](https://www.espressif.com)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=flat&logo=opencv&logoColor=white)](https://opencv.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Arduino](https://img.shields.io/badge/Arduino-Framework-00979D?style=flat&logo=arduino&logoColor=white)](https://www.arduino.cc)

**Firmware and Python viewer for low‑latency MJPEG streaming from the Seeed XIAO ESP32S3 Sense, with custom buffering that avoids OpenCV timeouts.**

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Prerequisites](#system-prerequisites)
- [Installation & Setup](#installation--setup)
  - [1. Virtual Environment Setup](#1-virtual-environment-setup)
  - [2. Install Python Dependencies](#2-install-python-dependencies)
  - [3. Hardware Configuration (platformio.ini)](#3-hardware-configuration-platformioini)
  - [4. Configure WiFi and Upload Firmware](#4-configure-wifi-and-upload-firmware)
- [Running the Stream](#running-the-stream)
  - [5. Get the IP Address](#5-get-the-ip-address)
  - [6. Run the Python Viewer](#6-run-the-python-viewer)
- [How It Works](#how-it-works)
- [Pushing to GitHub](#pushing-to-github)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

---

## Overview

This repository provides everything you need to turn a blank **Ubuntu** system into a working low‑latency video streaming setup for the **Seeed XIAO ESP32S3 Sense** camera.  
It includes:

- The **Arduino firmware** (uploaded via PlatformIO) that captures frames and serves an MJPEG stream over WiFi.
- A **custom Python viewer** (`raw_view.py`) that reliably displays the stream without the timeout errors often seen with OpenCV’s `VideoCapture`.

All steps are covered, from installing Python tools to pushing the final code to GitHub.

## Features

- 🚀 **Low‑latency streaming** – custom raw JPEG buffering avoids OpenCV timeouts.
- 📷 **MJPEG over WiFi** – direct camera feed from the ESP32S3 Sense.
- 🔧 **One‑command PlatformIO setup** – fully configured for PSRAM and Arduino framework.
- 🐍 **Python viewer** – lightweight, uses only `opencv-python` and `numpy`.
- 💾 **PSRAM enabled** – necessary for the camera buffer to work correctly.
- 📡 **Auto‑connects to your WiFi** – just set SSID and password.
- 🖥️ **Works on Linux** (Ubuntu tested) – harmless Qt warnings are noted and can be ignored.

## System Prerequisites

- **Ubuntu** (or any Debian‑based Linux with `apt`).
- **USB‑C data cable** – must support data transfer, not just charging.
- **Local WiFi network** (2.4 GHz).
- **Seeed XIAO ESP32S3 Sense** board.

## Installation & Setup

### 1. Virtual Environment Setup

Isolate project dependencies in a dedicated Python virtual environment.

```bash
# Install the venv tool
sudo apt update
sudo apt install python3-venv -y

# Create the virtual environment (we'll use ~/vir_esp32SENSEenv)
python3 -m venv ~/vir_esp32SENSEenv

# Activate it (do this every time you work on the project)
source ~/vir_esp32SENSEenv/bin/activate
```

Your terminal prompt should now begin with `(vir_esp32SENSEenv)`.

### 2. Install Python Dependencies

With the virtual environment active, install PlatformIO and the libraries needed by the viewer:

```bash
pip install platformio opencv-python numpy
```

### 3. Hardware Configuration (platformio.ini)

Initialize the PlatformIO project for the XIAO ESP32S3 board:

```bash
pio project init --board seeed_xiao_esp32s3
```

**CRITICAL:** The XIAO ESP32S3 Sense must have PSRAM enabled for the camera buffer.
Edit `platformio.ini` so it matches exactly:

```ini
[env:seeed_xiao_esp32s3]
platform = espressif32
board = seeed_xiao_esp32s3
framework = arduino
monitor_speed = 115200
upload_speed = 921600

; Enable 8MB PSRAM for the camera buffer
build_flags = 
    -DBOARD_HAS_PSRAM
    -DARDUINO_USB_MODE=1
    -DARDUINO_USB_CDC_ON_BOOT=1
```

### 4. Configure WiFi and Upload Firmware

Open `src/main.cpp` and find the WiFi section.

Replace the credentials with your own:

```cpp
const char* ssid = "YOUR_WIFI_SSID"; 
const char* password = "YOUR_WIFI_PASSWORD"; 
```

Connect the ESP32S3 to your computer using a data‑capable USB‑C cable.

Compile and upload the firmware:

```bash
pio run -t upload
```

## Running the Stream

### 5. Get the IP Address

Once the upload finishes, open the serial monitor:

```bash
pio device monitor
```

Wait a few seconds until you see something like:

```
Stream Ready at: http://192.168.1.X/
```

Copy that IP address and press `Ctrl+C` to exit the monitor.

### 6. Run the Python Viewer

We use `raw_view.py` instead of OpenCV’s default `VideoCapture` because the built‑in network handler often crashes with “Timeout” errors when the WiFi latency fluctuates. Our script manually buffers raw JPEG bytes, completely avoiding that problem.

Open `raw_view.py` in a text editor.

Paste the IP address you copied into the `URL` variable.

Run the viewer:

```bash
python raw_view.py
```

**Linux users:** If you see `QFontDatabase: Cannot find font directory`, just ignore it – it’s a harmless Qt warning and the video window will appear as usual.

## How It Works

```
ESP32 Camera → captures frame → MJPEG HTTP stream (WiFi) → Python viewer (raw JPEG buffer) → OpenCV display
```

**Why a custom viewer?**  
OpenCV’s `VideoCapture` relies on a tight internal timeout. Even small WiFi delays can cause it to throw an error and stop. Our approach:

1. Fetches raw bytes from the stream.
2. Buffers them manually.
3. Decodes only complete JPEG frames.
4. Displays them without ever hitting a fatal timeout.

## Pushing to GitHub

Use these commands to push the project to the `main` branch on your repository:

```bash
git remote add origin https://github.com/krsatyam36/esp32-s3.git
git add .
git commit -m "Update README and project files"
git push -u origin main
```

When prompted for a password, use your **GitHub Personal Access Token** (not your GitHub account password).

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| Camera stream not working | PSRAM not enabled | Double‑check `platformio.ini` contains `-DBOARD_HAS_PSRAM` |
| Upload fails | Bad USB cable or wrong port | Use a data USB‑C cable; try a different port |
| No serial output after upload | Wrong baud rate | Make sure `monitor_speed = 115200` in `platformio.ini` |
| `Stream Ready` never appears | WiFi credentials wrong | Verify SSID and password; use 2.4 GHz network |
| Python viewer crashes with timeout | Using standard `VideoCapture` | Always use the provided `raw_view.py` |
| `QFontDatabase: Cannot find font directory` | Missing desktop fonts (Linux) | Harmless warning – video window still opens |

## Project Structure

```
.
├── platformio.ini       # Board & PSRAM configuration
├── src/
│   └── main.cpp         # ESP32 firmware (MJPEG server)
├── raw_view.py          # Custom Python viewer with buffering
├── include/             # Project header files
├── lib/                 # Private libraries
├── recordings/          # Captured video storage
├── snapshots/           # Captured image storage
├── test/                # PlatformIO test runner
└── README.md            # This documentation
```

<div align="center">
Built with ❤️ for reliable ESP32 video streaming
Contributions and improvements welcome!
</div>
