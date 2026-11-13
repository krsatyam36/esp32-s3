#include <stdio.h>
#include "coremark.h"
#include "core_portme.h"
#include "esp_timer.h"

#if PERFORMANCE_RUN
volatile ee_s32 seed1_volatile = 0x0;
volatile ee_s32 seed2_volatile = 0x0;
volatile ee_s32 seed3_volatile = 0x66;
#endif
volatile ee_s32 seed4_volatile = ITERATIONS;
volatile ee_s32 seed5_volatile = 0;

static CORE_TICKS start_time_val, stop_time_val;

static CORE_TICKS barebones_clock(void)
{
    return (CORE_TICKS)esp_timer_get_time();
}

#define GETMYTIME(_t)        (*(_t) = barebones_clock())
#define MYTIMEDIFF(fin, ini) ((fin) - (ini))

void start_time(void)
{
    GETMYTIME(&start_time_val);
}

void stop_time(void)
{
    GETMYTIME(&stop_time_val);
}

CORE_TICKS get_time(void)
{
    return (CORE_TICKS)MYTIMEDIFF(stop_time_val, start_time_val);
}

secs_ret time_in_secs(CORE_TICKS ticks)
{
    return ((secs_ret)ticks) / (secs_ret)EE_TICKS_PER_SEC;
}

ee_u32 default_num_contexts = 1;

void portable_init(core_portable *p, int *argc, char *argv[])
{
    (void)argc;
    (void)argv;
    if (sizeof(ee_ptr_int) != sizeof(ee_u8 *)) {
        printf("ERROR: ee_ptr_int does not hold a pointer\n");
    }
    p->portable_id = 1;
}

void portable_fini(core_portable *p)
{
    p->portable_id = 0;
}
