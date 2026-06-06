#pragma once

#include <esp_http_server.h>
#include <esp_camera.h>
#include <Arduino.h>
#include "camera_utils.h"
#include "dashboard_html.h"

#define PART_BOUNDARY "123456789000000000000987654321"
#define LED_BUILTIN 21

static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;

// ==================== MJPEG STREAM ====================

static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t *_jpg_buf = NULL;
    char part_buf[64];

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;

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

// ==================== SNAPSHOT ====================

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

// ==================== RESOLUTION ====================

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

// ==================== LED CONTROL ====================

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

// ==================== FLASH LED ====================

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

// ==================== TELEMETRY ====================

static esp_err_t telemetry_handler(httpd_req_t *req) {
    char json[512];
    unsigned long uptime_sec = millis() / 1000;
    int rssi = WiFi.RSSI();
    uint32_t heap = ESP.getFreeHeap();
    uint32_t psram = ESP.getFreePsram();
    float temp = temperatureRead();

    snprintf(json, sizeof(json),
        "{"
        "\"heap\":%lu,"
        "\"uptime\":%lu,"
        "\"rssi\":%d,"
        "\"ip\":\"%s\","
        "\"resolution\":\"%s\","
        "\"free_psram\":%lu,"
        "\"temperature\":%.1f"
        "}",
        heap, uptime_sec, rssi, WiFi.localIP().toString().c_str(),
        resolutionToString(current_resolution), psram, temp);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

// ==================== PING / HEALTH ====================

static esp_err_t ping_handler(httpd_req_t *req) {
    char json[128];
    snprintf(json, sizeof(json),
        "{\"status\":\"ok\",\"ip\":\"%s\",\"uptime\":%lu}",
        WiFi.localIP().toString().c_str(), millis() / 1000);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json, strlen(json));
    return ESP_OK;
}

// ==================== DASHBOARD ====================

static esp_err_t dashboard_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    httpd_resp_send(req, DASHBOARD_HTML, strlen(DASHBOARD_HTML));
    return ESP_OK;
}

// ==================== START SERVER ====================

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
    httpd_uri_t dashboard_uri = {
        .uri = "/dashboard",
        .method = HTTP_GET,
        .handler = dashboard_handler,
        .user_ctx = NULL
    };

    Serial.printf("Starting web server on port: %d\n", config.server_port);
    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        httpd_register_uri_handler(stream_httpd, &snapshot_uri);
        httpd_register_uri_handler(stream_httpd, &res_uri);
        httpd_register_uri_handler(stream_httpd, &led_uri);
        httpd_register_uri_handler(stream_httpd, &flash_uri);
        httpd_register_uri_handler(stream_httpd, &telemetry_uri);
        httpd_register_uri_handler(stream_httpd, &ping_uri);
        httpd_register_uri_handler(stream_httpd, &dashboard_uri);
        Serial.println("Server started with all endpoints");
    } else {
        Serial.println("Server start failed");
    }
}
