# ESP32-S3 Benchmark Firmware

Reproducible ESP-IDF firmware used for the measurements in
[`docs/esp32-s3-benchmark.md`](../../../docs/esp32-s3-benchmark.md).

Board: Seeed Studio XIAO ESP32-S3 Sense (ESP32-S3R8, 240 MHz, 8 MB PSRAM).

## Projects

| Project | Measures |
|---|---|
| `bench_cpu/` | CoreMark 1.0, internal SRAM/PSRAM/flash bandwidth, FP32/FP64, dual-core scaling, temperature |
| `speech_bench/` | TFLite Micro keyword spotting (micro_speech model, int8) |

The person-detection measurement uses the upstream
`esp-tflite-micro/examples/person_detection` example in `CLI_ONLY_INFERENCE`
mode; only that compile flag is custom.

## Requirements

- ESP-IDF v5.4.1 (`idf.py` on `PATH`)
- Target: `esp32s3`
- For `bench_cpu`, clone the EEMBC CoreMark sources into the component
  (they are third-party and not vendored here):

```bash
git clone --depth 1 https://github.com/eembc/coremark.git /tmp/coremark
mkdir -p bench_cpu/components/coremark/coremark
cp /tmp/coremark/core_*.c /tmp/coremark/coremark.h \
   bench_cpu/components/coremark/coremark/
```

- For `speech_bench`, clone `esp-tflite-micro` next to it (or adjust
  `main/idf_component.yml`):

```bash
git clone --depth 1 https://github.com/espressif/esp-tflite-micro.git \
  benchmarks/firmware/esp-tflite-micro
```

## Build

```bash
cd bench_cpu          # or speech_bench
idf.py set-target esp32s3
idf.py build
```

`speech_bench/main/` contains the micro_speech model and test features copied
from the Apache-2.0 `esp-tflite-micro` example.

## Flash and run (important for this board)

This board uses the ESP32-S3 **native USB Serial/JTAG** controller. Two
non-default esptool options are required:

- `--before usb_reset` — the default DTR/RTS reset is for USB-UART bridges and
  leaves this board in the ROM loader.
- `--no-stub` — the flasher stub corrupts data on this USB-CDC link; the ROM
  loader is slower but reliable.

```bash
python3 -m esptool --port /dev/ttyACM0 --before usb_reset --after hard_reset \
  --no-stub write_flash --flash_mode dio --flash_size 2MB --flash_freq 80m \
  0x0 build/bootloader/bootloader.bin \
  0x8000 build/partition_table/partition-table.bin \
  0xe000 build/ota_data_initial.bin \
  0x10000 build/bench_cpu.bin

# Reset and run
python3 -m esptool --port /dev/ttyACM0 --before usb_reset --after hard_reset \
  --no-stub chip_id

# Console: /dev/ttyACM0, 115200 8N1
```

`bench_cpu` prints `BENCH:`-prefixed lines. `speech_bench` prints a single
`BENCH:ML|micro_speech|...` line.

## Flash caveat

The module reports an 8 MB flash but only the first **2 MB** is readable on this
unit (CRC failure at `0x200000`). The partition layout here is 2 MB and all
images fit well below that. Back up the original firmware before flashing.

The 2 MB original-firmware backup is intentionally **not** committed: it
contains the device's WiFi credentials.
