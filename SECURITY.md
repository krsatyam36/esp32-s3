# Security Policy

## Reporting a Vulnerability

Open an issue with the label `security` or contact the maintainer directly.
Do not disclose security-related issues publicly until a fix is available.

## Security Best Practices

1. Keep ESP32 firmware updated via OTA
2. Use a dedicated network for IoT devices
3. Set strong WiFi credentials
4. Don't expose the ESP32 directly to the internet
5. Use environment variables for secrets, not config.py committed to git
