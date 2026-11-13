// On-device live pedestrian detection (real bounding boxes) for XIAO ESP32-S3 Sense.
//
// Camera -> JPEG decode -> ESP-DL pedestrian detector -> bbox overlay -> JPEG
// -> MJPEG HTTP stream. All inference runs on the ESP32; only the annotated
// MJPEG leaves the board.

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <list>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"

#include "esp_system.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "esp_http_server.h"
#include "esp_camera.h"
#include "img_converters.h"
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "esp_private/esp_clk.h"
#include "lwip/inet.h"
#include "driver/ledc.h"
#include "driver/temperature_sensor.h"

#include "pedestrian_detect.hpp"
#include "dl_image_define.hpp"

static const char *TAG = "live_bbox";

#define WIFI_CONNECTED_BIT BIT0
static EventGroupHandle_t s_wifi_events;

#define MAX_JPEG (256 * 1024)
#define STREAM_BOUNDARY "123456789000000000000987654321"

static PedestrianDetect *g_detector;

static uint8_t *g_latest;
static size_t g_latest_len;
static uint32_t g_seq;
static SemaphoreHandle_t g_lock;

static volatile float g_max_score;
static volatile float g_fps;
static volatile float g_inf_ms;
static volatile float g_temp = -1.0f;
static volatile uint32_t g_frames;
static volatile uint32_t g_drops;
static volatile uint32_t g_objects;
static volatile uint16_t g_width;
static volatile uint16_t g_height;

static temperature_sensor_handle_t g_ts;
static bool g_ts_ok;

// ---------------------------------------------------------------------------
// Camera (XIAO ESP32-S3 Sense pinout)
// ---------------------------------------------------------------------------
static esp_err_t camera_start(void)
{
    camera_config_t c = {};
    c.ledc_channel = LEDC_CHANNEL_0;
    c.ledc_timer = LEDC_TIMER_0;
    c.pin_pwdn = -1;
    c.pin_reset = -1;
    c.pin_xclk = 10;
    c.pin_sccb_sda = 40;
    c.pin_sccb_scl = 39;
    c.pin_d7 = 48;
    c.pin_d6 = 11;
    c.pin_d5 = 12;
    c.pin_d4 = 14;
    c.pin_d3 = 16;
    c.pin_d2 = 18;
    c.pin_d1 = 17;
    c.pin_d0 = 15;
    c.pin_vsync = 38;
    c.pin_href = 47;
    c.pin_pclk = 13;
    c.xclk_freq_hz = 20000000;
    c.pixel_format = PIXFORMAT_JPEG;
    c.frame_size = FRAMESIZE_QVGA;
    c.jpeg_quality = 15;
    c.fb_count = 2;
    c.fb_location = CAMERA_FB_IN_PSRAM;
    c.grab_mode = CAMERA_GRAB_LATEST;

    esp_err_t err = esp_camera_init(&c);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "camera init failed: %s", esp_err_to_name(err));
        return err;
    }
    sensor_t *s = esp_camera_sensor_get();
    if (s) {
        ESP_LOGI(TAG, "camera sensor pid=0x%02x ver=0x%02x",
                 (unsigned)s->id.PID, (unsigned)s->id.VER);
    }
    return ESP_OK;
}

// ---------------------------------------------------------------------------
// WiFi: reuse credentials already stored in NVS by the original firmware
// ---------------------------------------------------------------------------
static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        char ipbuf[16];
        ESP_LOGI(TAG, "got ip: %s",
                 esp_ip4addr_ntoa(&e->ip_info.ip, ipbuf, sizeof(ipbuf)));
        xEventGroupSetBits(s_wifi_events, WIFI_CONNECTED_BIT);
    }
}

static void wifi_start(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    s_wifi_events = xEventGroupCreate();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                               &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                               &wifi_event_handler, NULL));

    wifi_config_t wc = {};
    esp_err_t err = esp_wifi_get_config(WIFI_IF_STA, &wc);
    ESP_LOGI(TAG, "stored wifi: err=%s ssid_len=%u pass_len=%u",
             esp_err_to_name(err), (unsigned)strlen((char *)wc.sta.ssid),
             (unsigned)strlen((char *)wc.sta.password));
    if (wc.sta.ssid[0] == 0) {
        ESP_LOGE(TAG, "no stored SSID; WiFi will not connect");
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_wifi_set_ps(WIFI_PS_NONE);
    xEventGroupWaitBits(s_wifi_events, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE,
                        portMAX_DELAY);
    ESP_LOGI(TAG, "WiFi ready");
}

// ---------------------------------------------------------------------------
// ESP-DL pedestrian detector
// ---------------------------------------------------------------------------
static bool detector_start(void)
{
    g_detector = new PedestrianDetect(PedestrianDetect::PICO_S8_V1, false);
    if (!g_detector) {
        ESP_LOGE(TAG, "detector alloc failed");
        return false;
    }
    ESP_LOGI(TAG, "ESP-DL pedestrian detector ready");
    return true;
}

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------
static inline void put_px(uint8_t *rgb, int w, int x, int y,
                          uint8_t r, uint8_t g, uint8_t b)
{
    uint8_t *p = rgb + ((size_t)y * w + x) * 3;
    p[0] = r;
    p[1] = g;
    p[2] = b;
}

static void fill_rect(uint8_t *rgb, int w, int h, int x0, int y0, int x1, int y1,
                      uint8_t r, uint8_t g, uint8_t b)
{
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 >= w) x1 = w - 1;
    if (y1 >= h) y1 = h - 1;
    for (int y = y0; y <= y1; y++) {
        for (int x = x0; x <= x1; x++) {
            put_px(rgb, w, x, y, r, g, b);
        }
    }
}

static void draw_box(uint8_t *rgb, int w, int h, int x1, int y1, int x2, int y2,
                     uint8_t r, uint8_t g, uint8_t b, int t)
{
    if (x1 > x2) { int tmp = x1; x1 = x2; x2 = tmp; }
    if (y1 > y2) { int tmp = y1; y1 = y2; y2 = tmp; }
    fill_rect(rgb, w, h, x1, y1, x2, y1 + t - 1, r, g, b);
    fill_rect(rgb, w, h, x1, y2 - t + 1, x2, y2, r, g, b);
    fill_rect(rgb, w, h, x1, y1, x1 + t - 1, y2, r, g, b);
    fill_rect(rgb, w, h, x2 - t + 1, y1, x2, y2, r, g, b);
}

static void swap_rb(uint8_t *rgb, size_t pixels)
{
    for (size_t i = 0; i < pixels; i++, rgb += 3) {
        uint8_t t = rgb[0];
        rgb[0] = rgb[2];
        rgb[2] = t;
    }
}

// ---------------------------------------------------------------------------
// HTTP: MJPEG at "/" (same contract the existing relay expects), snapshot,
// health metrics.
// ---------------------------------------------------------------------------
static esp_err_t stream_handler(httpd_req_t *req)
{
    httpd_resp_set_type(req,
        "multipart/x-mixed-replace; boundary=" STREAM_BOUNDARY);
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    uint8_t *buf = (uint8_t *)heap_caps_malloc(MAX_JPEG,
                                               MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) {
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                                   "out of memory");
    }

    uint32_t last = 0;
    char hdr[160];
    while (true) {
        size_t len = 0;
        xSemaphoreTake(g_lock, portMAX_DELAY);
        if (g_seq != last) {
            len = g_latest_len;
            if (len) memcpy(buf, g_latest, len);
            last = g_seq;
        }
        xSemaphoreGive(g_lock);

        if (!len) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        int hlen = snprintf(hdr, sizeof(hdr),
                            "--%s\r\nContent-Type: image/jpeg\r\n"
                            "Content-Length: %u\r\n\r\n",
                            STREAM_BOUNDARY, (unsigned)len);
        if (httpd_resp_send_chunk(req, hdr, hlen) != ESP_OK) break;
        if (httpd_resp_send_chunk(req, (const char *)buf, len) != ESP_OK) break;
        if (httpd_resp_send_chunk(req, "\r\n", 2) != ESP_OK) break;
    }
    httpd_resp_send_chunk(req, NULL, 0);
    free(buf);
    return ESP_OK;
}

static esp_err_t snapshot_handler(httpd_req_t *req)
{
    xSemaphoreTake(g_lock, portMAX_DELAY);
    size_t len = g_latest_len;
    uint8_t *buf = NULL;
    if (len) {
        buf = (uint8_t *)heap_caps_malloc(len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (buf) memcpy(buf, g_latest, len);
    }
    xSemaphoreGive(g_lock);

    if (!buf) {
        return httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "no frame yet");
    }
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = httpd_resp_send(req, (const char *)buf, len);
    free(buf);
    return err;
}

static esp_err_t health_handler(httpd_req_t *req)
{
    int rssi = 0;
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) rssi = ap.rssi;

    char json[512];
    int n = snprintf(json, sizeof(json),
        "{\"objects\":%u,\"max_score\":%.3f,\"fps\":%.2f,\"inf_ms\":%.2f,"
        "\"temp\":%.1f,\"frames\":%u,\"drops\":%u,\"free_heap\":%u,"
        "\"free_psram\":%u,\"rssi\":%d,\"uptime_s\":%u,\"width\":%u,"
        "\"height\":%u,\"cpu_mhz\":%u}",
        (unsigned)g_objects, g_max_score, g_fps, g_inf_ms, g_temp,
        (unsigned)g_frames, (unsigned)g_drops,
        (unsigned)esp_get_free_heap_size(),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
        rssi, (unsigned)(esp_timer_get_time() / 1000000),
        (unsigned)g_width, (unsigned)g_height,
        (unsigned)(esp_clk_cpu_freq() / 1000000));
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    return httpd_resp_send(req, json, n);
}

static void http_start(void)
{
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port = 80;
    cfg.lru_purge_enable = true;
    cfg.max_open_sockets = 4;

    httpd_handle_t server = NULL;
    ESP_ERROR_CHECK(httpd_start(&server, &cfg));

    httpd_uri_t root = {};
    root.uri = "/";
    root.method = HTTP_GET;
    root.handler = stream_handler;
    httpd_register_uri_handler(server, &root);

    httpd_uri_t stream = {};
    stream.uri = "/stream";
    stream.method = HTTP_GET;
    stream.handler = stream_handler;
    httpd_register_uri_handler(server, &stream);

    httpd_uri_t snap = {};
    snap.uri = "/snapshot";
    snap.method = HTTP_GET;
    snap.handler = snapshot_handler;
    httpd_register_uri_handler(server, &snap);

    httpd_uri_t health = {};
    health.uri = "/health";
    health.method = HTTP_GET;
    health.handler = health_handler;
    httpd_register_uri_handler(server, &health);

    ESP_LOGI(TAG, "HTTP server on :80");
}

// ---------------------------------------------------------------------------
// Detection pipeline
// ---------------------------------------------------------------------------
static void detect_task(void *arg)
{
    const int max_w = 640;
    const int max_h = 480;
    uint8_t *rgb = (uint8_t *)heap_caps_malloc((size_t)max_w * max_h * 3,
                                               MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!rgb) {
        ESP_LOGE(TAG, "rgb buffer alloc failed");
        vTaskDelete(NULL);
        return;
    }

    uint32_t fps_count = 0;
    int64_t fps_t0 = esp_timer_get_time();
    int64_t temp_t0 = 0;

    while (true) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb) {
            g_drops++;
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        int w = fb->width;
        int h = fb->height;
        bool ok = false;
        if (fb->format == PIXFORMAT_JPEG) {
            ok = fmt2rgb888(fb->buf, fb->len, fb->format, rgb);
        } else if (fb->format == PIXFORMAT_RGB565) {
            ok = fmt2rgb888(fb->buf, fb->len, fb->format, rgb);
        }
        esp_camera_fb_return(fb);

        if (!ok || w > max_w || h > max_h) {
            g_drops++;
            continue;
        }

        dl::image::img_t img = {};
        img.data = rgb;
        img.width = (uint16_t)w;
        img.height = (uint16_t)h;
        img.pix_type = dl::image::DL_IMAGE_PIX_TYPE_RGB888;

        int64_t t0 = esp_timer_get_time();
        std::list<dl::detect::result_t> &results = g_detector->run(img);
        int64_t inf_us = esp_timer_get_time() - t0;

        float inf_ms = (float)inf_us / 1000.0f;
        g_inf_ms = (g_inf_ms == 0.0f) ? inf_ms : (g_inf_ms * 0.9f + inf_ms * 0.1f);

        uint32_t objects = 0;
        float best = 0.0f;
        for (const auto &res : results) {
            if (res.box.size() < 4) continue;
            objects++;
            if (res.score > best) best = res.score;
            draw_box(rgb, w, h, res.box[0], res.box[1], res.box[2], res.box[3],
                     0, 255, 0, 3);
        }
        g_objects = objects;
        g_max_score = best;
        g_width = (uint16_t)w;
        g_height = (uint16_t)h;

        swap_rb(rgb, (size_t)w * h);

        uint8_t *jpg = NULL;
        size_t jlen = 0;
        if (fmt2jpg(rgb, (size_t)w * h * 3, w, h, PIXFORMAT_RGB888, 15,
                    &jpg, &jlen)) {
            if (jlen <= MAX_JPEG) {
                xSemaphoreTake(g_lock, portMAX_DELAY);
                memcpy(g_latest, jpg, jlen);
                g_latest_len = jlen;
                g_seq++;
                xSemaphoreGive(g_lock);
            } else {
                g_drops++;
            }
            free(jpg);
        } else {
            g_drops++;
        }

        g_frames++;
        fps_count++;

        int64_t now = esp_timer_get_time();
        if (now - fps_t0 >= 1000000) {
            g_fps = (float)fps_count * 1e6f / (float)(now - fps_t0);
            fps_count = 0;
            fps_t0 = now;
            if (g_ts_ok && now - temp_t0 >= 1000000) {
                float t = -1.0f;
                if (temperature_sensor_get_celsius(g_ts, &t) == ESP_OK) {
                    g_temp = t;
                }
                temp_t0 = now;
            }
        }

        vTaskDelay(1);
    }
}

extern "C" void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "nvs init: %s (not erasing; WiFi credentials live there)",
                 esp_err_to_name(ret));
    }

    if (camera_start() != ESP_OK) {
        vTaskDelay(portMAX_DELAY);
    }
    if (!detector_start()) {
        ESP_LOGE(TAG, "detector init failed");
        vTaskDelay(portMAX_DELAY);
    }

    temperature_sensor_config_t tcfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(-10, 80);
    if (temperature_sensor_install(&tcfg, &g_ts) == ESP_OK) {
        if (temperature_sensor_enable(g_ts) == ESP_OK) g_ts_ok = true;
    }

    g_lock = xSemaphoreCreateMutex();
    g_latest = (uint8_t *)heap_caps_malloc(MAX_JPEG,
                                           MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!g_latest) {
        ESP_LOGE(TAG, "latest frame alloc failed");
        vTaskDelay(portMAX_DELAY);
    }

    wifi_start();

    xTaskCreatePinnedToCore(detect_task, "detect", 12288, NULL, 5, NULL, 1);
    http_start();

    ESP_LOGI(TAG, "bbox detection ready at http://192.168.1.12/");

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        ESP_LOGI(TAG,
                 "fps=%.2f inf=%.2fms objects=%u score=%.2f temp=%.1f frames=%u drops=%u",
                 g_fps, g_inf_ms, (unsigned)g_objects, g_max_score, g_temp,
                 (unsigned)g_frames, (unsigned)g_drops);
    }
}
