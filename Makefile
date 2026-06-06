.PHONY: viewer server vision test check upload ota monitor lint typecheck clean help

# ESP32 IP (override with ESP_IP=...)
ESP_IP ?= http://192.168.1.X/

## Run the OpenCV viewer
viewer:
	python src/raw_view.py --ip $(ESP_IP)

## Run the FastAPI web server
server:
	python src/app.py

## Run the Vision LLM CLI
vision:
	python src/vision_llm.py --ip $(ESP_IP)

## Connectivity test
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