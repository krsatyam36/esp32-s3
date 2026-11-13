#ifndef CORE_PORTME_H
#define CORE_PORTME_H

#include <stdint.h>
#include <stddef.h>

#define HAS_FLOAT 1
#define HAS_TIME_H 0
#define USE_CLOCK 0
#define HAS_STDIO 1
#define HAS_PRINTF 1

#define COMPILER_VERSION "xtensa-esp-elf GCC 14.2"
#ifndef COMPILER_FLAGS
#define COMPILER_FLAGS FLAGS_STR
#endif
#define MEM_LOCATION "STATIC"

typedef int16_t ee_s16;
typedef uint16_t ee_u16;
typedef int32_t ee_s32;
typedef float ee_f32;
typedef uint8_t ee_u8;
typedef uint32_t ee_u32;
typedef uintptr_t ee_ptr_int;
typedef size_t ee_size_t;

#define align_mem(x) (void *)(4 + (((ee_ptr_int)(x)-1) & ~((ee_ptr_int)3)))

typedef uint64_t CORE_TICKS;
#define EE_TICKS_PER_SEC 1000000
#define CLOCKS_PER_SEC 1000000

typedef struct CORE_PORTABLE_S {
    ee_u8 portable_id;
} core_portable;

extern ee_u32 default_num_contexts;
void portable_init(core_portable *p, int *argc, char *argv[]);
void portable_fini(core_portable *p);


#ifndef SEED_METHOD
#define SEED_METHOD SEED_VOLATILE
#endif
#ifndef MEM_METHOD
#define MEM_METHOD MEM_STATIC
#endif
#ifndef MAIN_HAS_NOARGC
#define MAIN_HAS_NOARGC 1
#endif
#ifndef MAIN_HAS_NORETURN
#define MAIN_HAS_NORETURN 0
#endif
#ifndef ITERATIONS
#define ITERATIONS 1000
#endif

#ifndef MULTITHREAD
#define MULTITHREAD 1
#define USE_PTHREAD 0
#define USE_FORK    0
#define USE_SOCKET  0
#endif

#endif
