idf_component_register(
  SRCS "bench_speech.cc" "model.cc" "no_micro_features_data.cc"
  INCLUDE_DIRS "."
  PRIV_REQUIRES esp_timer
)
