.PHONY: help viewer server vision test

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

viewer: ## Run the OpenCV camera viewer
	python raw_view.py

server: ## Run the FastAPI webserver
	python app.py

vision: ## Run the Vision LLM client
	python vision_llm.py

test: ## Test ESP32 connectivity
	python stream_test.py
