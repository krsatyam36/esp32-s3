idf_component_register(
  SRCS "live_detect.cc" "person_detect_model_data.cc"
  INCLUDE_DIRS "."
  REQUIRES esp32-camera esp-tflite-micro esp_timer esp_http_server esp_wifi
           nvs_flash esp_netif driver esp_psram
)
