# Live person detection (TFLite Micro, frame-level)

This is the lighter classifier version. It runs the TFLite Micro person model on
each 96x96 grayscale frame and draws a frame-level border + confidence bar.

- 4.86 fps, 66.8 ms inference, 0 drops over a 5-minute soak.
- Temperature 76.1-81.1 C.

## Missing model data

The 1.9 MB generated model source is third-party TFLM example data and is not
committed. Copy it from the `esp-tflite-micro` checkout before building:

```bash
mkdir -p ~/esp
git clone --depth 1 https://github.com/espressif/esp-tflite-micro.git ~/esp/esp-tflite-micro
cp ~/esp/esp-tflite-micro/examples/person_detection/main/person_detect_model_data.cc main/
cp ~/esp/esp-tflite-micro/examples/person_detection/main/person_detect_model_data.h main/
```

`main/idf_component.yml` points at `../../esp-tflite-micro`; adjust the
`override_path` if your checkout lives elsewhere.

## Build and flash

```bash
idf.py set-target esp32s3
idf.py build
```

This project fits the 2 MB app layout (`partitions.csv`). Use the same
`esptool --before usb_reset --no-stub` flash sequence described in
`docs/ondevice-detection.md`.
