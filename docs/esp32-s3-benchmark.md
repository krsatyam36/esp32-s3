# ESP32-S3 Hardware & ML Benchmark

**Board:** Seeed Studio XIAO ESP32-S3 Sense (ESP32-S3R8)
**Chip:** ESP32-S3, dual-core Xtensa LX7 @ 240 MHz, rev v0.2
**Memory:** 8 MB octal PSRAM, 8 MB flash (see flash caveat), OV2640/OV3660/OV5640 camera, digital mic, SD slot
**MAC:** 98:a3:16:xx:xx:xx (redacted)
**Firmware tested:** ESP-IDF v5.4.1, `-O2`, USB Serial/JTAG console
**Date:** 2026-11-12

The original camera firmware was backed up before testing and restored afterwards.
Camera stream verified again at 1600x1200, ~4.7-5.3 fps.

---

## Results

| Sector | Benchmark | Result |
|---|---|---|
| CPU | CoreMark 1.0 (valid 10.32 s run, STATIC, -O2) | **581.25** (2.42 CoreMark/MHz) |
| CPU | ALU, single core | 79.4 Mops/s |
| CPU | ALU, both cores (1.99x scaling) | **158.1 Mops/s** |
| Memory | Internal SRAM memcpy | 363.65 MB/s |
| Memory | Internal SRAM write (memset) | 726.26 MB/s |
| Memory | Internal SRAM read | 130.00 MB/s |
| Memory | PSRAM read -> internal | 56.43 MB/s |
| Memory | PSRAM write | 33.27 MB/s |
| Memory | PSRAM copy (PSRAM->PSRAM) | 21.29 MB/s |
| Flash | XIP cached read | 25.84 MB/s |
| Flash | Raw SPI read | 11.99 MB/s |
| FPU | FP32 (hardware) | **43.38 MFLOPS** |
| FPU | FP64 (software) | 2.79 MFLOPS |
| ML | Person detection, int8 96x96x1 | **53 ms/inference (18.9 fps)** |
| ML | Keyword spotting (micro_speech), int8 | **2.76 ms/inference (362 fps)** |
| Camera | 1600x1200 MJPEG stream | **4.5-5.5 fps, ~140 KB/frame (~5-6 Mbps)** |
| Thermal | Idle / load (internal sensor) | 57-59 C / 59-61 C |
| Wireless | Observed camera stream throughput | ~5-6 Mbps (not max WiFi) |

Person-detection breakdown: depthwise conv 23 ms, conv 29 ms, FC/pooling ~0 ms.
micro_speech model: 18.8 KB, 1960-byte input, 30 KB tensor arena.

---

## What these numbers mean

- **Vision ML:** 19 fps for a 96x96 person detector is comfortably real-time for a 10-15 fps vision pipeline. A 128x128 MobileNet-class model should land around 60-100 ms; 224x224 models will be in the ~200-400 ms range and are not real-time.
- **Audio ML:** keyword spotting at 2.76 ms/inference leaves massive headroom for continuous 16 kHz audio (10-20 ms frames) and multi-model audio pipelines.
- **CPU:** 581 CoreMark is normal for an ESP32-S3 at 240 MHz; both cores scale almost linearly for independent work.
- **Memory:** PSRAM read bandwidth (~56 MB/s) is the main limit for high-resolution image work. A 1600x1200 RGB888 frame is 5.76 MB, so ~5 fps means ~29 MB/s of pixel traffic - close to the practical PSRAM limit once camera/JPEG overhead is included. Keep frame processing in grayscale/RGB565 or lower resolutions for higher FPS.
- **FPU:** The single-precision FPU is useful (~43 MFLOPS); double precision falls back to software (~2.8 MFLOPS), so keep ML and DSP in FP32/int8.
- **Camera:** 1600x1200 is the UXGA mode (OV2640-class). The Sense module supports OV2640, OV3660 and OV5640; higher sensor resolutions would require a different firmware mode and more PSRAM bandwidth.
- **WiFi:** The 5-6 Mbps figure is the camera/JPEG pipeline, not the WiFi ceiling. ESP32-S3 2.4 GHz WiFi typically reaches tens of Mbps in good conditions; an iperf test was not run to avoid reflashing again.

---

## Important caveats

1. **Flash reporting anomaly:** `esptool flash_id` reports an 8 MB GD25Q64 (c8:4017), but reads fail with CRC at exactly `0x200000`. The first 2 MB is fully readable; only that region was backed up. The running firmware image is 847 KB, so the backup covers bootloader, partition table, NVS, otadata and app0, and the restore was verified working.
   - For future firmware: keep images under 2 MB, or investigate the upper-flash addressing issue before relying on the full 8 MB.
2. **USB-CDC reliability:** the default esptool flasher stub corrupts data on this board's USB Serial/JTAG link. Use `--no-stub` (ROM loader). Reset/run the app with `--before usb_reset`; the default DTR/RTS reset is for USB-UART bridges and leaves this board in the ROM loader.
3. **Camera is single-client:** while the relay holds the MJPEG stream, the ESP32's own `/snapshot` blocks. The relay's `/snapshot.jpg` serves the last buffered frame and works fine.
4. **`scout.service` still has its original bug:** it globs `/dev/ttyACM*` and grabs the ESP32, then its MAVLink thread dies. Stop it before any future serial/flashing work:
   `sudo systemctl stop scout.service`
5. Temperature is the chip's internal sensor, not an external thermocouple. No power/current measurement was made.

---

## Reproduction / artifacts

On the Jetson (`jetson1`, 192.168.1.9):

- `~/esp/bench_cpu/` - CoreMark + memory + FPU + dual-core firmware
- `~/esp/speech_bench/` - micro_speech benchmark firmware
- `~/esp/esp-tflite-micro/` - person detection (CLI mode) and TFLM component
- `~/esp/esp-idf/` - ESP-IDF v5.4.1 toolchain
- `~/esp32s3_original_2mb.bin` - original firmware backup (2 MB)

On the laptop:

- `/home/kumarsatyam/esp32s3_original_2mb.bin` - copy of the backup
  SHA-256: `9b15523a7c92143689b7487e247787c1a25457332d99972fbc4b61eb51e0608b`

Correct interaction commands:

```bash
# Reset and run the flashed app (USB Serial/JTAG)
python3 -m esptool --port /dev/ttyACM0 --before usb_reset --after hard_reset --no-stub chip_id

# Flash (works around the stub corruption)
python3 -m esptool --port /dev/ttyACM0 --before usb_reset --after hard_reset --no-stub \
  write_flash --flash_mode dio --flash_size 2MB --flash_freq 80m \
  0x0 build/bootloader/bootloader.bin \
  0x8000 build/partition_table/partition-table.bin \
  0xe000 build/ota_data_initial.bin \
  0x10000 build/<app>.bin
```

Console: `/dev/ttyACM0`, 115200 8N1, `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`.

---

## Restored state

- Original camera firmware restored and verified (`/snapshot` returns 1600x1200 JPEG).
- `esp32-relay.service` active: http://localhost:8090 (1600x1200, ~5 fps).
- `esp32-cam-tunnel.service` active on the laptop.
- `scout.service` restarted (still has the `/dev/ttyACM0` bug).
