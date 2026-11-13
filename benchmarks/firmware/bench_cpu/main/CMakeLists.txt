idf_component_register(
  SRCS "bench_main.c"
  INCLUDE_DIRS "."
  REQUIRES coremark esp_timer esp_psram spi_flash esp_hw_support driver
)
