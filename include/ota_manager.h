#pragma once

#include <ArduinoOTA.h>
#include <Arduino.h>

#define OTA_HOSTNAME "xiao-esp32s3-cam"

// Handle setupOTA request/operation.
void setupOTA() {
    ArduinoOTA.setHostname(OTA_HOSTNAME);

    ArduinoOTA.onStart([]() {
        Serial.println("OTA update started");
    });
    ArduinoOTA.onEnd([]() {
        Serial.println("OTA update finished");
    });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        Serial.printf("OTA: %u%%\r", progress / (total / 100));
    });
    ArduinoOTA.onError([](ota_error_t error) {
        Serial.printf("OTA error: %d\n", error);
    });

    ArduinoOTA.begin();
    Serial.println("OTA ready");
}

// Handle handleOTA request/operation.
void handleOTA() {
    ArduinoOTA.handle();
}
