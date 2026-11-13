idf_component_register(
  SRCS "live_detect.cc"
  INCLUDE_DIRS "."
  REQUIRES pedestrian_detect esp-dl esp32-camera esp_timer esp_http_server
           esp_wifi nvs_flash esp_netif driver esp_psram
)
