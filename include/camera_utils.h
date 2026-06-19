#pragma once

#include <esp_camera.h>
#include <Arduino.h>

/*
 * XIAO ESP32S3 Sense — OV2640 Camera Pin Mapping
 * See also: https://wiki.seeedstudio.com/xiao_esp32s3_camera/
 */
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39
#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15
#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

static framesize_t current_resolution = FRAMESIZE_UXGA;
static int camera_init_attempts = 0;

// Handle initCamera request/operation.
bool initCamera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    if (psramFound()) {
        config.frame_size = FRAMESIZE_UXGA;
        config.jpeg_quality = 10;
        config.fb_count = 2;
    } else {
        config.frame_size = FRAMESIZE_SVGA;
        config.jpeg_quality = 12;
        config.fb_count = 1;
    }
    current_resolution = config.frame_size;

    esp_err_t err = esp_camera_init(&config);
    camera_init_attempts++;

    if (err != ESP_OK) {
        Serial.printf("Camera init failed (attempt %d) with error 0x%x\n", camera_init_attempts, err);
        if (camera_init_attempts < 3) {
            Serial.println("Retrying with VGA fallback...");
            config.frame_size = FRAMESIZE_VGA;
            config.jpeg_quality = 15;
            config.fb_count = 1;
            err = esp_camera_init(&config);
            if (err == ESP_OK) {
                current_resolution = FRAMESIZE_VGA;
                Serial.println("Camera initialized with VGA fallback");
                return true;
            }
        }
        return false;
    }
    Serial.println("Camera initialized successfully");
    return true;
}

bool setResolution(framesize_t size) {
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) return false;
    int ret = s->set_framesize(s, size);
    if (ret == 0) {
        current_resolution = size;
        Serial.printf("Resolution changed to %d\n", size);
        return true;
    }
    return false;
}

// Handle setSpecialEffect request/operation.
bool setSpecialEffect(int effect) {
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) return false;
    effect = constrain(effect, 0, 6);
    int ret = s->set_special_effect(s, effect);
    return (ret == 0);
}

bool setWhiteBalance(int mode) {
    sensor_t *s = esp_camera_sensor_get();
    if (s == NULL) return false;
    mode = constrain(mode, 0, 4);
    int ret = s->set_wb_mode(s, mode);
    return (ret == 0);
}

const char* resolutionToString(framesize_t fs) {
    switch (fs) {
        case FRAMESIZE_QQVGA: return "QQVGA";
        case FRAMESIZE_QVGA:  return "QVGA";
        case FRAMESIZE_VGA:   return "VGA";
        case FRAMESIZE_CIF:   return "CIF";
        case FRAMESIZE_SVGA:  return "SVGA";
        case FRAMESIZE_UXGA:  return "UXGA";
        default:              return "OTHER";
    }
}
