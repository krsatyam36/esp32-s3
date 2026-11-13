# Host viewer / relay

`esp32_relay.py` maintains a single upstream MJPEG connection to the ESP32 and
fans it out to browsers. It serves:

- `/` - HTML viewer
- `/stream` - MJPEG fan-out
- `/snapshot.jpg` - latest annotated frame
- `/health` - relay status

It is stdlib-only and works with the ESP32 firmware's MJPEG boundary.

## systemd user units

- `systemd/esp32-relay.service` - runs the relay on the Jetson (listens on
  127.0.0.1:8090).
- `systemd/esp32-cam-tunnel.service` - SSH tunnel from a laptop to the Jetson
  (`localhost:8090` -> jetson `127.0.0.1:8090`). Adjust the host name.

Install:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now esp32-relay.service
```

The ESP32 WiFi credentials are read from its own NVS; nothing here stores them.
