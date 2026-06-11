# Changelog

## v2.2.0 (2026-06-11)

### Added
- Dark/light theme toggle with localStorage persistence
- Fullscreen video stream toggle button
- Mobile-responsive hamburger sidebar navigation
- Event notification badge for unviewed events
- Real-time event search/filter functionality
- CSV export for analytics metrics data
- Color-coded event severity indicators (CRIT/INFO)
- Stream quality indicator dot (FPS+RSSI based)
- Pause/resume toggle for dashboard updates
- Configurable rate limiting middleware (RATE_LIMIT env)
- Structured JSON logging with configurable LOG_LEVEL
- K8s-style /livez and /readyz health probes
- Configurable CORS origins via CORS_ORIGINS env
- Graceful shutdown with configurable timeout
- ESP32 client retry with exponential backoff
- Custom 404/405/504 error handlers
- API version and name response headers
- Request timing logs with slow request warnings
- /api/env endpoint for runtime config inspection
- StreamBuffer max size limit (5MB) with overflow protection
- CameraCapture reconnection stats tracking
- Adaptive controller threshold env vars
- Metrics percentiles (p50/p95/p99) in summary
- Telemetry caching layer (2s TTL) in ESP32 client
- Frame size validation in CameraCapture
- Configurable timezone offset for timeline (TZ_OFFSET)
- Object counter reset endpoint (POST /stats/reset)
- Motion heatmap persistence to disk (HEATMAP_FILE)
- YOLO frame skip for performance (YOLO_FRAME_SKIP)
- Scene classification confidence scores
- Alert webhook notifications (ALERT_WEBHOOK_URL)
- Configurable YOLO model path (YOLO_MODEL_PATH)
- Timeline export endpoint (POST /timeline/export)
- Vector search indexing progress tracking
- Configurable Ollama system prompts via env vars
- Alert PATCH endpoint for quick enable/disable toggle
- Camera auto-exposure control endpoint (/ae)
- WiFi quality percentage in firmware telemetry
- MAC address in firmware diagnostics
- Enhanced Docker healthcheck using /readyz
- Enhanced Docker Compose with healthcheck, volumes
- Enhanced pytest config with timeout and markers
- Extended pre-commit hooks (mypy, JSON, TOML checks)
- Comprehensive .gitignore with organized patterns
- Enhanced mypy config with strictness options
- EditorConfig rules for C/C++/Python/TOML
- Enhanced coverage config with HTML report

## v2.1.0 (2026-06-11)

### Added
- Dark/light theme toggle with localStorage persistence
- Fullscreen video stream toggle button
- Mobile-responsive hamburger sidebar navigation
- Event notification badge for unviewed events
- Real-time event search/filter functionality
- CSV export for analytics metrics data
- Color-coded event severity indicators (CRIT/INFO)
- Stream quality indicator dot (FPS+RSSI based)
- Pause/resume toggle for dashboard updates
- Configurable rate limiting middleware (RATE_LIMIT env)
- Structured JSON logging with configurable LOG_LEVEL
- K8s-style /livez and /readyz health probes
- Configurable CORS origins via CORS_ORIGINS env
- Graceful shutdown with configurable timeout
- ESP32 client retry with exponential backoff
- Custom 404/405/504 error handlers
- API version and name response headers
- Request timing logs with slow request warnings
- /api/env endpoint for runtime config inspection
- StreamBuffer max size limit (5MB) with overflow protection
- CameraCapture reconnection stats tracking
- Adaptive controller threshold env vars
- Metrics percentiles (p50/p95/p99) in summary
- Telemetry caching layer (2s TTL) in ESP32 client
- Frame size validation in CameraCapture
- Configurable timezone offset for timeline (TZ_OFFSET)
- Object counter reset endpoint (POST /stats/reset)
- Motion heatmap persistence to disk (HEATMAP_FILE)
- YOLO frame skip for performance (YOLO_FRAME_SKIP)
- Scene classification confidence scores
- Alert webhook notifications (ALERT_WEBHOOK_URL)
- Configurable YOLO model path (YOLO_MODEL_PATH)
- Timeline export endpoint (POST /timeline/export)
- Vector search indexing progress tracking
- Configurable Ollama system prompts via env vars
- Alert PATCH endpoint for quick enable/disable toggle
- Camera auto-exposure control endpoint (/ae)
- WiFi quality percentage in firmware telemetry
- MAC address in firmware diagnostics
- Enhanced Docker healthcheck using /readyz
- Enhanced Docker Compose with healthcheck, volumes
- Enhanced pytest config with timeout and markers
- Extended pre-commit hooks (mypy, JSON, TOML checks)
- Comprehensive .gitignore with organized patterns
- Enhanced mypy config with strictness options
- EditorConfig rules for C/C++/Python/TOML
- Enhanced coverage config with HTML report

## v2.0.0 (2026-06-06)

### Added
- Scene classification (indoor/outdoor/night/crowded)
- Activity timeline tracking
- Object counting per class
- Smart alerts with configurable rules
- Motion heatmap visualization
- 6 firmware resolution modes (QQVGA..UXGA)
- /ping, /diag, /flip, /reset, /status firmware endpoints
- /dashboard-data, /api/version, /api/stats server endpoints
- CLI arguments for raw_view.py and vision_llm.py
- Dockerfile and docker-compose support
- CI/CD workflows (lint, test, build)
- 20 test files with 200+ test cases
- Type hints across all Python modules
- Project tooling (ruff, mypy, pre-commit, editorconfig)

### Changed
- Complete web dashboard redesign with tabbed layout
- FastAPI server refactored into core/ and ai/ modules
- Config loading with env var fallback
- Telemetry format extended (total_psram, chip_id)

### Fixed
- Cross-module dependency initialization order

## v1.3.1 (2026-05-15)

Initial public release with MJPEG streaming, Vision LLM, semantic search, YOLO gatekeeper, adaptive rate controller.
