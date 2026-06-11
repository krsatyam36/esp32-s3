"""Post-build script for PlatformIO — prints firmware size info."""

import os
from pathlib import Path


def main():
    firmware_dir = Path(".pio", "build")
    for fw in firmware_dir.rglob("firmware.bin"):
        size = fw.stat().st_size
        mb = size / (1024 * 1024)
        print(f"Firmware size: {size} bytes ({mb:.2f} MB)")
        break


if __name__ == "__main__":
    main()
