.PHONY: viewer server vision test check upload ota monitor discover auto \
        lint typecheck pytest clean docker-build docker-run help

# ESP32 IP (override with ESP_IP=...)
ESP_IP ?= http://192.168.1.X/

## Run the OpenCV viewer (auto-discovers IP if not set)
viewer:
	python src/raw_view.py

## Run the FastAPI web server (auto-discovers IP)
server:
	python src/app.py

## Run the Vision LLM CLI (auto-discovers IP)
vision:
	python src/vision_llm.py

## Connectivity test (requires ESP_IP or uses auto-discovered)
test:
	python src/stream_test.py $(ESP_IP)

## Validate setup (dependencies + config)
check:
	python src/check_deps.py

## Upload firmware via PlatformIO
upload:
	pio run -t upload

## Upload firmware via OTA
ota:
	pio run -t upload --upload-port $(ESP_IP)

## Open serial monitor
monitor:
	pio device monitor

## Auto-discover ESP32 IP and write to config.py
discover:
	python src/discover_esp32.py --write-config

## Upload, auto-discover, then launch viewer
auto: upload discover
	python src/raw_view.py

## Upload OTA, auto-discover, then launch viewer
auto-ota: ota
	python src/raw_view.py

## Lint with ruff
lint:
	ruff check src/
	ruff format --check src/

## Type check with mypy
typecheck:
	mypy src/

## Run all tests
pytest:
	python -m pytest tests/ -v

## Clean Python cache
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name '*.pyc' -delete

## Build Docker image
docker-build:
	docker build -t xiao-edge-platform .

## Run Docker container
docker-run:
	docker run -p 8000:8000 --env-file .env xiao-edge-platform

## Show help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
