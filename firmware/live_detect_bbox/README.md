# Live pedestrian detection with real bounding boxes

ESP-DL pedestrian detector running entirely on the XIAO ESP32-S3 Sense.

- Model: `pedestrian_detect_pico_s8_v1` (425 KB, int8), fetched as the
  `espressif/pedestrian_detect` component.
- Input: 224x224 RGB, derived from the QVGA camera frame.
- Output: real bounding boxes drawn on-device, streamed as MJPEG.
- Measured: 4.05 fps, 116.9 ms/frame, 0 drops, 83.1 C after ~11 min.

## Build

```bash
idf.py set-target esp32s3
idf.py build
```

The component manager fetches ESP-DL `~3.3.14`, `pedestrian_detect ~0.3.3` and
`esp32-camera`.

## Flash (native USB Serial/JTAG)

```bash
python3 -m esptool --port /dev/ttyACM0 --before usb_reset --after hard_reset \
  --no-stub write_flash --flash_mode dio --flash_size 8MB --flash_freq 80m \
  0x0 build/bootloader/bootloader.bin \
  0x8000 build/partition_table/partition-table.bin \
  0xe000 build/ota_data_initial.bin \
  0x10000 build/live_detect_bbox.bin
```

The app is 2.84 MB, so this project uses an 8 MB flash layout with a 3.3 MB
app partition (`partitions.csv`). The NVS partition stays at 0x9000 so the
WiFi credentials written by the original firmware remain usable.

## Notes

- The model is pedestrian-specific by design. See `docs/ondevice-detection.md`
  for why a COCO detector is not practical here.
- Sustained detection runs around 83 C; a heat sink is recommended.
