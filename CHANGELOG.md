# Changelog

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
