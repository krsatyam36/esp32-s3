# Seeed XIAO ESP32S3 Sense - Low Latency Streamer

This repository contains the firmware and Python viewer to set up a robust, low-latency video stream from the Seeed XIAO ESP32S3 Sense camera over a local WiFi network. 

This guide covers the complete setup from a blank Ubuntu environment, including virtual environment creation, flashing the microcontroller via PlatformIO, and running the custom Python client.

## 1. System Prerequisites

Open your terminal and ensure the necessary Python virtual environment tools are installed on your Ubuntu system:

```bash
sudo apt update
sudo apt install python3-venv -y
2. Virtual Environment Setup
It is highly recommended to isolate the dependencies for this project.

Create and activate a virtual environment (we use vir_esp32SENSEenv located in the home directory):

Bash
# Create the virtual environment
python3 -m venv ~/vir_esp32SENSEenv

# Activate it (You must do this every time you work on the project)
source ~/vir_esp32SENSEenv/bin/activate
(Your terminal prompt should now have (vir_esp32SENSEenv) at the beginning).

3. Install Python Dependencies
With the virtual environment active, install PlatformIO (the build system for the ESP32) and the libraries required for the Python video viewer:

Bash
pip install platformio opencv-python numpy
4. Hardware Configuration (platformio.ini)
To initialize the project for the specific board, run:

Bash
pio project init --board seeed_xiao_esp32s3
CRITICAL: The XIAO ESP32S3 Sense requires the extra PSRAM to be enabled for the camera buffer to work. Ensure your platformio.ini file looks exactly like this:

Ini, TOML
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
5. Configure WiFi and Upload Firmware
Open src/main.cpp.

Locate the WiFi credentials section and update it to match your local network:

C++
const char* ssid = "YOUR_WIFI_SSID"; 
const char* password = "YOUR_WIFI_PASSWORD"; 
Connect the ESP32S3 to your computer via a data-capable USB-C cable.

Compile and upload the firmware:

Bash
pio run -t upload
6. Get the IP Address
Once the firmware is uploaded, open the serial monitor to find out what IP address your router assigned to the board:

Bash
pio device monitor
Wait a few seconds until you see an output like:
Stream Ready at: http://192.168.1.X/
(Copy this IP address and press Ctrl+C to exit the monitor).

7. Run the Python Viewer
We use a custom Python script (raw_view.py) instead of OpenCV's standard VideoCapture. OpenCV's internal network handler is sensitive to slight WiFi latency and will frequently crash with "Timeout" errors. Our script manually buffers the raw JPEG bytes, bypassing the timeout issue.

Open raw_view.py and paste the IP address you got from the monitor into the URL variable.

Run the script:

Bash
python raw_view.py
(Note for Linux users: If you see QFontDatabase: Cannot find font directory in the terminal, ignore it. It is a harmless Qt warning and the video window will still open).
