#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <inttypes.h>

#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_psram.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "esp_private/esp_clk.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/temperature_sensor.h"

extern int coremark_main(void);

static volatile uint32_t g_sink;
static temperature_sensor_handle_t g_ts;
static bool g_ts_ok;

static uint64_t now_us(void)
{
    return (uint64_t)esp_timer_get_time();
}

static float temp_c(void)
{
    float v = -999.0f;
    if (!g_ts_ok) {
        return v;
    }
    if (temperature_sensor_get_celsius(g_ts, &v) != ESP_OK) {
        return -999.0f;
    }
    return v;
}

static void report_mem(const char *name, size_t bytes, uint32_t iters, uint64_t us)
{
    double sec = (double)us / 1e6;
    double mbs = ((double)bytes * (double)iters) / (1024.0 * 1024.0) / sec;
    printf("BENCH:MEM|%s|%.2f MB/s|%u iters|%.3f s\n", name, mbs, (unsigned)iters, sec);
}

static void bench_internal(void)
{
    const size_t N = 64 * 1024;
    uint8_t *a = heap_caps_malloc(N, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    uint8_t *b = heap_caps_malloc(N, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!a || !b) {
        printf("BENCH:MEM|internal alloc failed\n");
        free(a);
        free(b);
        return;
    }
    memset(a, 0x11, N);
    memset(b, 0x22, N);
    memcpy(b, a, N);

    const uint32_t it = 2000;

    uint64_t t0 = now_us();
    for (uint32_t i = 0; i < it; i++) {
        memcpy(b, a, N);
        g_sink += b[i & 63];
    }
    report_mem("internal memcpy 64K", N, it, now_us() - t0);

    t0 = now_us();
    uint32_t sum = 0;
    for (uint32_t i = 0; i < it; i++) {
        const uint32_t *p = (const uint32_t *)a;
        for (size_t j = 0; j < N / 4; j++) {
            sum += p[j];
        }
    }
    g_sink += sum;
    report_mem("internal read 64K", N, it, now_us() - t0);

    t0 = now_us();
    for (uint32_t i = 0; i < it; i++) {
        memset(b, (int)(i & 0xff), N);
        g_sink += b[0];
    }
    report_mem("internal write 64K", N, it, now_us() - t0);

    free(a);
    free(b);
}

static void bench_psram(void)
{
    const size_t N = 64 * 1024;
    uint8_t *pa = heap_caps_malloc(N, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    uint8_t *pb = heap_caps_malloc(N, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    uint8_t *dst = heap_caps_malloc(N, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!pa || !pb || !dst) {
        printf("BENCH:MEM|psram alloc failed (pa=%p pb=%p dst=%p)\n", pa, pb, dst);
        free(pa);
        free(pb);
        free(dst);
        return;
    }
    memset(pa, 0x33, N);
    memset(pb, 0x44, N);
    memcpy(dst, pa, N);

    const uint32_t it = 400;

    uint64_t t0 = now_us();
    for (uint32_t i = 0; i < it; i++) {
        memcpy(dst, pa, N);
        g_sink += dst[i & 63];
    }
    report_mem("psram read 64K", N, it, now_us() - t0);

    t0 = now_us();
    for (uint32_t i = 0; i < it; i++) {
        memset(pa, (int)(i & 0xff), N);
        g_sink += pa[0];
    }
    report_mem("psram write 64K", N, it, now_us() - t0);

    t0 = now_us();
    for (uint32_t i = 0; i < it; i++) {
        memcpy(pb, pa, N);
        g_sink += pb[i & 63];
    }
    report_mem("psram copy 64K", N, it, now_us() - t0);

    free(pa);
    free(pb);
    free(dst);
}

static const uint8_t flash_ro[64 * 1024] __attribute__((aligned(4))) = {
    [0 ... 64 * 1024 - 1] = 0xA5
};

static void bench_flash(void)
{
    const size_t N = 64 * 1024;
    uint8_t *dst = heap_caps_malloc(N, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!dst) {
        printf("BENCH:MEM|flash alloc failed\n");
        return;
    }
    memcpy(dst, flash_ro, N);

    const uint32_t it = 500;
    uint64_t t0 = now_us();
    for (uint32_t i = 0; i < it; i++) {
        memcpy(dst, flash_ro, N);
        g_sink += dst[i & 63];
    }
    report_mem("flash XIP read 64K", N, it, now_us() - t0);

    const uint32_t rit = 100;
    t0 = now_us();
    esp_err_t err = ESP_OK;
    for (uint32_t i = 0; i < rit; i++) {
        err = esp_flash_read(NULL, dst, 0x20000, N);
        g_sink += dst[i & 63];
    }
    if (err == ESP_OK) {
        report_mem("raw flash read 64K", N, rit, now_us() - t0);
    } else {
        printf("BENCH:MEM|raw flash read failed: %s\n", esp_err_to_name(err));
    }

    free(dst);
}

static void bench_fpu(void)
{
    volatile float f = 1.0f;
    uint32_t n = 5000000;
    uint64_t t0 = now_us();
    for (uint32_t i = 0; i < n; i++) {
        f = f * 1.0000001f + 0.0000001f;
    }
    uint64_t us = now_us() - t0;
    double mflops = ((double)n * 2.0) / ((double)us / 1e6) / 1e6;
    printf("BENCH:FPU|fp32|%.2f MFLOPS|%u ops|%.3f s|sink=%.6f\n", mflops, (unsigned)n,
           (double)us / 1e6, (double)f);

    volatile double d = 1.0;
    n = 1000000;
    t0 = now_us();
    for (uint32_t i = 0; i < n; i++) {
        d = d * 1.0000000001 + 0.0000000001;
    }
    us = now_us() - t0;
    mflops = ((double)n * 2.0) / ((double)us / 1e6) / 1e6;
    printf("BENCH:FPU|fp64|%.2f MFLOPS|%u ops|%.3f s|sink=%.9f\n", mflops, (unsigned)n,
           (double)us / 1e6, (double)d);
}

typedef struct {
    uint32_t n;
    volatile uint32_t out;
} alu_arg_t;

static volatile int g_done;
static volatile int g_ready;
static volatile int g_go;

static void alu_task(void *p)
{
    alu_arg_t *a = (alu_arg_t *)p;
    uint32_t x = 1;
    g_ready++;
    while (!g_go) {
        vTaskDelay(1);
    }
    for (uint32_t i = 0; i < a->n; i++) {
        x = x * 1664525u + 1013904223u;
    }
    a->out = x;
    g_done++;
    vTaskDelete(NULL);
}

static void bench_alu(void)
{
    const uint32_t n = 20000000;
    alu_arg_t a0 = {.n = n, .out = 0};
    alu_arg_t a1 = {.n = n, .out = 0};

    g_done = g_ready = g_go = 0;
    xTaskCreatePinnedToCore(alu_task, "alu0", 4096, &a0, 5, NULL, 0);
    while (g_ready < 1) {
        vTaskDelay(1);
    }
    uint64_t t0 = now_us();
    g_go = 1;
    while (g_done < 1) {
        vTaskDelay(1);
    }
    uint64_t us1 = now_us() - t0;
    printf("BENCH:CPU|alu1|%.2f Mops/s|%.3f s\n", (double)n / ((double)us1 / 1e6) / 1e6,
           (double)us1 / 1e6);

    g_done = g_ready = g_go = 0;
    xTaskCreatePinnedToCore(alu_task, "alu0", 4096, &a0, 5, NULL, 0);
    xTaskCreatePinnedToCore(alu_task, "alu1", 4096, &a1, 5, NULL, 1);
    while (g_ready < 2) {
        vTaskDelay(1);
    }
    t0 = now_us();
    g_go = 1;
    while (g_done < 2) {
        vTaskDelay(1);
    }
    uint64_t us2 = now_us() - t0;
    printf("BENCH:CPU|alu2|%.2f Mops/s|%.3f s\n",
           ((double)n * 2.0) / ((double)us2 / 1e6) / 1e6, (double)us2 / 1e6);
}

static void print_info(void)
{
    esp_chip_info_t ci;
    esp_chip_info(&ci);

    uint32_t fsz = 0;
    esp_flash_get_size(NULL, &fsz);

    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    printf("BENCH:INFO|target=%s|cores=%d|revision=%d|flash_bytes=%u"
           "|psram_bytes=%u|cpu_hz=%u|internal_free=%u|psram_free=%u"
           "|mac=%02x:%02x:%02x:%02x:%02x:%02x\n",
           CONFIG_IDF_TARGET, ci.cores, ci.revision, (unsigned)fsz,
           (unsigned)esp_psram_get_size(), (unsigned)esp_clk_cpu_freq(),
           (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
           (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void app_main(void)
{
    vTaskDelay(pdMS_TO_TICKS(5000));

    temperature_sensor_config_t cfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(10, 80);
    if (temperature_sensor_install(&cfg, &g_ts) == ESP_OK) {
        if (temperature_sensor_enable(g_ts) == ESP_OK) {
            g_ts_ok = true;
        }
    }

    printf("\nBENCH:BOOT|bench_cpu|%s\n", CONFIG_IDF_TARGET);
    print_info();
    printf("BENCH:TEMP|idle|%.1f\n", (double)temp_c());

    bench_internal();
    bench_psram();
    bench_flash();
    bench_fpu();
    bench_alu();

    printf("BENCH:TEMP|load|%.1f\n", (double)temp_c());
    printf("BENCH:COREMARK|begin\n");
    coremark_main();
    printf("BENCH:COREMARK|end\n");
    printf("BENCH:TEMP|after|%.1f\n", (double)temp_c());
    printf("BENCH:DONE\n");

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        printf("BENCH:ALIVE|temp=%.1f\n", (double)temp_c());
    }
}
