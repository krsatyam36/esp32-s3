#pragma once

#include <ArduinoOTA.h>
#include <Arduino.h>

void setupOTA() {
    ArduinoOTA.setHostname("xiao-esp32s3-cam");

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

void handleOTA() {
    ArduinoOTA.handle();
}
