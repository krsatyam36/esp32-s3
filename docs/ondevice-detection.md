# On-device live detection (XIAO ESP32-S3 Sense)

This branch adds two self-contained ESP-IDF firmwares that run live detection
entirely on the ESP32-S3 and stream an annotated MJPEG feed. No frames or
inference are sent to a server.

Board: Seeed Studio XIAO ESP32-S3 Sense (ESP32-S3R8, 8 MB PSRAM, 8 MB flash,
OV3660 camera, digital microphone, SD slot).

## Firmwares

| Project | Model | Input | Inference | Stream |
|---|---|---|---|---|
| `firmware/live_detect_bbox` | ESP-DL pedestrian detector (`pedestrian_detect_pico_s8_v1`, 425 KB) | 224x224 RGB | **116.9 ms** end-to-end on-device | 320x240 @ **4.05 fps**, real green bounding boxes |
| `firmware/live_detect` | TFLite Micro person classifier | 96x96 grayscale | **66.8 ms** | 320x240 @ **4.86 fps**, frame-level border + confidence bar |

The bbox version is the final one. The classifier version is kept because it is
much lighter and is a useful fallback.

### Bbox detector results

- Model: ESP-DL `pedestrian_detect_pico_s8_v1`, 425,328 bytes, int8.
- Live pipeline: 4.05 fps, 116.9 ms per frame (preprocess + model + postprocess),
  0 drops over 2,631 frames, ~11 minutes uptime.
- Temperature: **83.1 C** after the long run. Add the XIAO heat sink for
  sustained use; the demo is stable but hot.
- Real bounding boxes are drawn on-device, in the camera image coordinates,
  then the frame is re-encoded to JPEG.

### Classifier version results

- 4.86 fps average over a 5-minute soak, 66.8 ms inference, 0 drops, no reboots.
- Temperature 76.1-81.1 C over the soak.
- Frame-level indicator only (the model is a classifier, not a localizer).

## Pipeline

```
OV3660 camera (JPEG, QVGA)
  -> fmt2rgb888 (RGB888)
  -> ESP-DL pedestrian detector (224x224, ESP-NN)
  -> draw boxes on RGB888
  -> R/B swap for the JPEG encoder
  -> fmt2jpg
  -> MJPEG at "/" (also /stream, /snapshot, /health)
```

WiFi credentials are read from the NVS partition written by the original
firmware, so no credentials are stored in this repository. The station connects
via DHCP and keeps the same address the previous firmware used.

The MJPEG boundary is `123456789000000000000987654321`, matching the existing
host relay contract.

## Build and flash

ESP-IDF **v5.4.1**, target `esp32s3`.

The bbox firmware uses ESP-DL and the pedestrian model components, fetched by
the IDF component manager:

```yaml
dependencies:
  espressif/esp-dl: "~3.3.14"
  espressif/pedestrian_detect: "~0.3.3"
  espressif/esp32-camera: ">=2.0.15,<3.0.0"
```

It is a 2.84 MB image, so it uses an **8 MB flash layout** with a 3.3 MB app
partition. The unit's flash chip is 8 MB; the ROM loader's `read_flash` command
on this board fails above 2 MB, but normal writes and XIP boot above 2 MB were
verified (the image was written to 0x2C4800 and hash-verified).

The native USB Serial/JTAG controller needs two non-default esptool options:

```bash
# --before usb_reset: the default DTR/RTS reset is for USB-UART bridges.
# --no-stub: the flasher stub corrupts data on this USB-CDC link.
python3 -m esptool --port /dev/ttyACM0 --before usb_reset --after hard_reset \
  --no-stub write_flash --flash_mode dio --flash_size 8MB --flash_freq 80m \
  0x0 build/bootloader/bootloader.bin \
  0x8000 build/partition_table/partition-table.bin \
  0xe000 build/ota_data_initial.bin \
  0x10000 build/live_detect_bbox.bin
```

The original camera firmware backup is **not** committed: it contains WiFi
credentials. Keep a private copy before flashing. Restore it with:

```bash
python3 -m esptool --port /dev/ttyACM0 --before usb_reset --after hard_reset \
  --no-stub write_flash 0x0 /path/to/original_2mb_backup.bin
```

## Host viewer / relay

`host/esp32_relay.py` holds one upstream MJPEG connection, fans it out to
browser clients, and serves:

- `/` - HTML viewer
- `/stream` - MJPEG fan-out
- `/snapshot.jpg` - latest annotated frame
- `/health` - relay status

`host/systemd/` contains user-service units for the relay and an SSH tunnel
example. Adjust usernames/paths for your machines.

## Caveats

- **Pedestrian-specific:** the 425 KB model detects people, not 80 COCO classes.
  A COCO/YOLO11n detector needs 8 MB flash/PSRAM and takes ~1 s per frame on the
  ESP32-S3, so it is not usable in this 320x240 live pipeline.
- **Camera single-client:** while the MJPEG stream is open, the ESP32's own
  `/snapshot` can block. The host relay serves its buffered `/snapshot.jpg`
  instead.
- **Heat:** 83 C after sustained bbox detection. Use a heat sink for long runs.
- **`scout.service` (drone mission)** on the Jetson globs `/dev/ttyACM*` and
  grabs the ESP32 serial port. Stop it before reading the ESP32 console or
  flashing:
  `sudo systemctl stop scout.service`.
