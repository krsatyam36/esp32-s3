#pragma once

#include <esp_http_server.h>
#include <esp_camera.h>
#include <Arduino.h>
#include "camera_utils.h"
#include "dashboard_html.h"

#define PART_BOUNDARY "123456789000000000000987654321"
#define FIRMWARE_VERSION "2.3.79"
#ifndef LED_BUILTIN
#define LED_BUILTIN 21
#endif
#define FW_NAME "xiao-esp32s3-cam"

static unsigned long _start_ms = 0;

static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;

// Handle stream_handler request/operation.
static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t *_jpg_buf = NULL;
    char part_buf[64];

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;
    httpd_resp_set_hdr(req, "X-Content-Type-Options", "nosniff");
    httpd_resp_set_hdr(req, "X-Frame-Options", "DENY");

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("Camera capture failed");
            res = ESP_FAIL;
        } else {
            if (fb->format != PIXFORMAT_JPEG) {
                bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
                esp_camera_fb_return(fb);
                fb = NULL;
                if (!jpeg_converted) {
                    Serial.println("JPEG compression failed");
                    res = ESP_FAIL;
                }
            } else {
                _jpg_buf_len = fb->len;
                _jpg_buf = fb->buf;
            }
        }
        if (res == ESP_OK) {
            size_t hlen = snprintf(part_buf, 64, _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
        }
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
            _jpg_buf = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }
        if (res != ESP_OK) break;
    }
    return res;
}

// Handle snapshot_handler request/operation.
static esp_err_t snapshot_handler(httpd_req_t *req) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    httpd_resp_set_type(req, "image/jpeg");
    esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    return res;
}

// Handle flip_handler request/operation.
static esp_err_t flip_handler(httpd_req_t *req) {
    char buf[16];
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing query");
        return ESP_FAIL;
    }
    char mode[8];
    if (httpd_query_key_value(buf, "mode", mode, sizeof(mode)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing mode");
        return ESP_FAIL;
    }
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No sensor");
        return ESP_FAIL;
    }
    if (strcmp(mode, "v") == 0) {
        s->set_vflip(s, s->status.vflip ? 0 : 1);
    } else if (strcmp(mode, "h") == 0) {
        s->set_hmirror(s, s->status.hmirror ? 0 : 1);
    } else {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid mode (use v or h)");
        return ESP_FAIL;
    }
    char json[64];
    snprintf(json, sizeof(json), "{\"success\":true,\"vflip\":%d,\"hmirror\":%d}",
             s->status.vflip, s->status.hmirror);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t resolution_handler(httpd_req_t *req) {
    char buf[16];
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing query");
        return ESP_FAIL;
    }

    char val[8];
    if (httpd_query_key_value(buf, "val", val, sizeof(val)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing val");
        return ESP_FAIL;
    }

    framesize_t fs;
    if (strcmp(val, "QQVGA") == 0) fs = FRAMESIZE_QQVGA;
    else if (strcmp(val, "QVGA") == 0) fs = FRAMESIZE_QVGA;
    else if (strcmp(val, "VGA") == 0) fs = FRAMESIZE_VGA;
    else if (strcmp(val, "CIF") == 0) fs = FRAMESIZE_CIF;
    else if (strcmp(val, "SVGA") == 0) fs = FRAMESIZE_SVGA;
    else if (strcmp(val, "UXGA") == 0) fs = FRAMESIZE_UXGA;
    else {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid resolution");
        return ESP_FAIL;
    }

    bool ok = setResolution(fs);
    char json[64];
    snprintf(json, sizeof(json), "{\"success\":%s}", ok ? "true" : "false");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t led_handler(httpd_req_t *req) {
    char buf[16];
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing query");
        return ESP_FAIL;
    }

    char state[8];
    if (httpd_query_key_value(buf, "state", state, sizeof(state)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing state");
        return ESP_FAIL;
    }

    bool on = (strcmp(state, "on") == 0);
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, on ? HIGH : LOW);

    char json[64];
    snprintf(json, sizeof(json), "{\"success\":true,\"state\":\"%s\"}", on ? "on" : "off");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t flash_handler(httpd_req_t *req) {
    char buf[16];
    int count = 3;
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char val[8];
        if (httpd_query_key_value(buf, "count", val, sizeof(val)) == ESP_OK) {
            count = atoi(val);
            if (count < 1) count = 1;
            if (count > 20) count = 20;
        }
    }

    pinMode(LED_BUILTIN, OUTPUT);
    for (int i = 0; i < count; i++) {
        digitalWrite(LED_BUILTIN, HIGH);
        delay(100);
        digitalWrite(LED_BUILTIN, LOW);
        delay(100);
    }

    char json[64];
    snprintf(json, sizeof(json), "{\"success\":true,\"flashes\":%d}", count);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t ae_handler(httpd_req_t *req) {
    char buf[16];
    int val = 0;
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char v[8];
        if (httpd_query_key_value(buf, "val", v, sizeof(v)) == ESP_OK) {
            val = atoi(v);
        }
    }
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No sensor");
        return ESP_FAIL;
    }
    s->set_ae_level(s, val);
    char json[64];
    snprintf(json, sizeof(json), "{\"success\":true,\"ae_level\":%d}", val);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t reset_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{\"status\":\"restarting\"}");
    delay(100);
    ESP.restart();
    return ESP_OK;
}

static void set_cors_headers(httpd_req_t *req) {
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type");
}

static esp_err_t options_handler(httpd_req_t *req) {
    set_cors_headers(req);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{}");
    return ESP_OK;
}

static esp_err_t telemetry_handler(httpd_req_t *req) {
    char json[512];
    unsigned long uptime_sec = millis() / 1000;
    int rssi = WiFi.RSSI();
    uint32_t heap = ESP.getFreeHeap();
    uint32_t psram = ESP.getFreePsram();
    float temp = temperatureRead();
    uint32_t total_psram = ESP.getPsramSize();

    int wifi_quality = map(constrain(rssi, -100, -50), -100, -50, 0, 100);
    snprintf(json, sizeof(json),
        "{"
        "\"heap\":%lu,"
        "\"uptime\":%lu,"
        "\"rssi\":%d,"
        "\"wifi_quality\":%d,"
        "\"resolution\":\"%s\","
        "\"free_psram\":%lu,"
        "\"total_psram\":%lu,"
        "\"temperature\":%.1f,"
        "\"ip\":\"%s\","
        "\"chip_id\":\"%s\","
        "\"cpu_freq\":%d,"
        "\"camera_init_attempts\":%d,"
        "\"framesize\":%d"
        "}",
        heap, uptime_sec, rssi, wifi_quality, resolutionToString(current_resolution),
        psram, total_psram, temp,
        WiFi.localIP().toString().c_str(),
        String((uint32_t)ESP.getEfuseMac(), HEX).c_str(),
        ESP.getCpuFreqMHz(),
        camera_init_attempts,
        (int)current_resolution);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t diag_handler(httpd_req_t *req) {
    char json[512];
    uint8_t mac[6];
    WiFi.macAddress(mac);
    snprintf(json, sizeof(json),
        "{"
        "\"chip_model\":\"%s\","
        "\"chip_cores\":%d,"
        "\"cpu_freq\":%d,"
        "\"flash_size\":%lu,"
        "\"psram_size\":%lu,"
        "\"free_heap\":%lu,"
        "\"free_psram\":%lu,"
        "\"sketch_size\":%lu,"
        "\"free_sketch\":%lu,"
        "\"sdk_version\":\"%s\","
        "\"firmware_version\":\"%s\","
        "\"camera_init_attempts\":%d,"
        "\"uptime\":%lu,"
        "\"wifi_rssi\":%d,"
        "\"mac_address\":\"%02X:%02X:%02X:%02X:%02X:%02X\""
        "}",
        ESP.getChipModel(),
        ESP.getChipCores(),
        ESP.getCpuFreqMHz(),
        ESP.getFlashChipSize(),
        ESP.getPsramSize(),
        ESP.getFreeHeap(),
        ESP.getFreePsram(),
        ESP.getSketchSize(),
        ESP.getFreeSketchSpace(),
        ESP.getSdkVersion(),
        FIRMWARE_VERSION,
        camera_init_attempts,
        millis() / 1000,
        WiFi.RSSI(),
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t brightness_handler(httpd_req_t *req) {
    char buf[16];
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing query");
        return ESP_FAIL;
    }
    char val[8];
    if (httpd_query_key_value(buf, "val", val, sizeof(val)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing val");
        return ESP_FAIL;
    }
    int level = atoi(val);
    level = constrain(level, -2, 2);
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No sensor");
        return ESP_FAIL;
    }
    s->set_brightness(s, level);
    char json[64];
    snprintf(json, sizeof(json), "{\"success\":true,\"brightness\":%d}", level);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t contrast_handler(httpd_req_t *req) {
    char buf[16];
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing query");
        return ESP_FAIL;
    }
    char val[8];
    if (httpd_query_key_value(buf, "val", val, sizeof(val)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing val");
        return ESP_FAIL;
    }
    int level = atoi(val);
    level = constrain(level, -2, 2);
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No sensor");
        return ESP_FAIL;
    }
    s->set_contrast(s, level);
    char json[64];
    snprintf(json, sizeof(json), "{\"success\":true,\"contrast\":%d}", level);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t quality_handler(httpd_req_t *req) {
    char buf[16];
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing query");
        return ESP_FAIL;
    }
    char val[8];
    if (httpd_query_key_value(buf, "val", val, sizeof(val)) != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing val");
        return ESP_FAIL;
    }
    int quality = atoi(val);
    quality = constrain(quality, 10, 100);
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No sensor");
        return ESP_FAIL;
    }
    s->set_quality(s, quality);
    char json[64];
    snprintf(json, sizeof(json), "{\"success\":true,\"quality\":%d}", quality);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t framesize_handler(httpd_req_t *req) {
    const char* resolutions[] = {"QQVGA", "QVGA", "CIF", "VGA", "SVGA", "UXGA"};
    const int res_values[] = {FRAMESIZE_QQVGA, FRAMESIZE_QVGA, FRAMESIZE_CIF, FRAMESIZE_VGA, FRAMESIZE_SVGA, FRAMESIZE_UXGA};
    int count = sizeof(resolutions) / sizeof(resolutions[0]);
    char json[512];
    char res_json[256] = "";
    for (int i = 0; i < count; i++) {
        char entry[64];
        int selected = ((int)current_resolution == res_values[i]) ? 1 : 0;
        snprintf(entry, sizeof(entry), "%s{\"name\":\"%s\",\"value\":%d,\"selected\":%d}",
                 (i > 0) ? "," : "", resolutions[i], res_values[i], selected);
        strcat(res_json, entry);
    }
    snprintf(json, sizeof(json), "{\"framesizes\":[%s],\"current\":\"%s\"}", res_json, resolutionToString(current_resolution));
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

static esp_err_t ping_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "application/json");
    char buf[256];
    snprintf(buf, sizeof(buf),
        "{\"status\":\"ok\",\"uptime\":%lu,\"ip\":\"%s\",\"fw\":\"%s\",\"hostname\":\"%s\"}",
        millis() / 1000,
        WiFi.localIP().toString().c_str(),
        FIRMWARE_VERSION,
        FW_NAME
    );
    return httpd_resp_send(req, buf, strlen(buf));
}

static esp_err_t status_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "application/json");
    char buf[512];
    snprintf(buf, sizeof(buf),
        "{\"status\":\"ok\",\"uptime\":%lu,\"heap\":%u,\"psram\":%u,\"rssi\":%d,\"ip\":\"%s\",\"fw\":\"%s\",\"free_blocks\":%u}",
        millis() / 1000,
        esp_get_free_heap_size(),
        ESP.getPsramSize(),
        WiFi.RSSI(),
        WiFi.localIP().toString().c_str(),
        FIRMWARE_VERSION,
        heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)
    );
    return httpd_resp_send(req, buf, strlen(buf));
}

static esp_err_t dashboard_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    httpd_resp_send(req, DASHBOARD_HTML, strlen(DASHBOARD_HTML));
    return ESP_OK;
}

void startWebServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.lru_purge_enable = true;

    httpd_uri_t stream_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = stream_handler,
        .user_ctx = NULL
    };
    httpd_uri_t snapshot_uri = {
        .uri = "/snapshot",
        .method = HTTP_GET,
        .handler = snapshot_handler,
        .user_ctx = NULL
    };
    httpd_uri_t res_uri = {
        .uri = "/res",
        .method = HTTP_GET,
        .handler = resolution_handler,
        .user_ctx = NULL
    };
    httpd_uri_t flip_uri = {
        .uri = "/flip",
        .method = HTTP_GET,
        .handler = flip_handler,
        .user_ctx = NULL
    };
    httpd_uri_t led_uri = {
        .uri = "/led",
        .method = HTTP_GET,
        .handler = led_handler,
        .user_ctx = NULL
    };
    httpd_uri_t flash_uri = {
        .uri = "/flash",
        .method = HTTP_GET,
        .handler = flash_handler,
        .user_ctx = NULL
    };
    httpd_uri_t telemetry_uri = {
        .uri = "/telemetry",
        .method = HTTP_GET,
        .handler = telemetry_handler,
        .user_ctx = NULL
    };
    httpd_uri_t ping_uri = {
        .uri = "/ping",
        .method = HTTP_GET,
        .handler = ping_handler,
        .user_ctx = NULL
    };
    httpd_uri_t diag_uri = {
        .uri = "/diag",
        .method = HTTP_GET,
        .handler = diag_handler,
        .user_ctx = NULL
    };
    httpd_uri_t reset_uri = {
        .uri = "/reset",
        .method = HTTP_GET,
        .handler = reset_handler,
        .user_ctx = NULL
    };
    httpd_uri_t dashboard_uri = {
        .uri = "/dashboard",
        .method = HTTP_GET,
        .handler = dashboard_handler,
        .user_ctx = NULL
    };
    httpd_uri_t status_uri = {
        .uri = "/status",
        .method = HTTP_GET,
        .handler = status_handler,
        .user_ctx = NULL
    };
    httpd_uri_t ae_uri = {
        .uri = "/ae",
        .method = HTTP_GET,
        .handler = ae_handler,
        .user_ctx = NULL
    };
    httpd_uri_t brightness_uri = {
        .uri = "/brightness",
        .method = HTTP_GET,
        .handler = brightness_handler,
        .user_ctx = NULL
    };
    httpd_uri_t contrast_uri = {
        .uri = "/contrast",
        .method = HTTP_GET,
        .handler = contrast_handler,
        .user_ctx = NULL
    };
    httpd_uri_t quality_uri = {
        .uri = "/quality",
        .method = HTTP_GET,
        .handler = quality_handler,
        .user_ctx = NULL
    };
    httpd_uri_t framesize_uri = {
        .uri = "/framesize",
        .method = HTTP_GET,
        .handler = framesize_handler,
        .user_ctx = NULL
    };
    httpd_uri_t options_uri = {
        .uri = "/*",
        .method = HTTP_OPTIONS,
        .handler = options_handler,
        .user_ctx = NULL
    };

    Serial.printf("Starting web server on port: %d\n", config.server_port);
    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        httpd_register_uri_handler(stream_httpd, &snapshot_uri);
        httpd_register_uri_handler(stream_httpd, &res_uri);
        httpd_register_uri_handler(stream_httpd, &flip_uri);
        httpd_register_uri_handler(stream_httpd, &led_uri);
        httpd_register_uri_handler(stream_httpd, &flash_uri);
        httpd_register_uri_handler(stream_httpd, &reset_uri);
        httpd_register_uri_handler(stream_httpd, &telemetry_uri);
        httpd_register_uri_handler(stream_httpd, &ping_uri);
        httpd_register_uri_handler(stream_httpd, &diag_uri);
        httpd_register_uri_handler(stream_httpd, &dashboard_uri);
        httpd_register_uri_handler(stream_httpd, &status_uri);
        httpd_register_uri_handler(stream_httpd, &ae_uri);
        httpd_register_uri_handler(stream_httpd, &brightness_uri);
        httpd_register_uri_handler(stream_httpd, &contrast_uri);
        httpd_register_uri_handler(stream_httpd, &quality_uri);
        httpd_register_uri_handler(stream_httpd, &framesize_uri);
        httpd_register_uri_handler(stream_httpd, &options_uri);
        Serial.println("Server started with all endpoints");
    } else {
        Serial.println("Server start failed");
    }
}