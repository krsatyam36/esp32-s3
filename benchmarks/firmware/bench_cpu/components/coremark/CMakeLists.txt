set(CM "${CMAKE_CURRENT_LIST_DIR}/coremark")
idf_component_register(
  SRCS "${CM}/core_list_join.c" "${CM}/core_matrix.c" "${CM}/core_state.c"
       "${CM}/core_util.c" "${CM}/core_main.c" "port/core_portme.c"
  INCLUDE_DIRS "${CM}" "port"
  REQUIRES esp_timer
)
set_source_files_properties("${CM}/core_main.c" PROPERTIES COMPILE_DEFINITIONS "main=coremark_main")
target_compile_definitions(${COMPONENT_LIB} PRIVATE
  MAIN_HAS_NOARGC=1
  MAIN_HAS_NORETURN=0
  PERFORMANCE_RUN=1
  ITERATIONS=6000
  TOTAL_DATA_SIZE=2000
  MEM_METHOD=MEM_STATIC
  SEED_METHOD=SEED_VOLATILE
  FLAGS_STR="-O2"
)
