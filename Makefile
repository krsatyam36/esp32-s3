.PHONY: viewer server vision test check upload ota monitor

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