#include <Arduino.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "camera_utils.h"
#include "wifi_manager.h"
#include "ota_manager.h"
#include "web_server.h"

void printDiagnostics() {
    Serial.println("\n========== XIAO ESP32S3 DIAGNOSTICS ==========");
    Serial.printf("Firmware: v%s\n", FIRMWARE_VERSION);
    Serial.printf("Chip Model: %s\n", ESP.getChipModel());
    Serial.printf("Chip Cores: %d\n", ESP.getChipCores());
    Serial.printf("CPU Freq: %d MHz\n", ESP.getCpuFreqMHz());
    Serial.printf("Flash Size: %u MB\n", ESP.getFlashChipSize() / (1024 * 1024));
    Serial.printf("PSRAM Size: %u MB\n", ESP.getPsramSize() / (1024 * 1024));
    Serial.printf("Free Heap: %u bytes\n", ESP.getFreeHeap());
    Serial.printf("Free PSRAM: %u bytes\n", ESP.getFreePsram());
    Serial.printf("Sketch Size: %u bytes\n", ESP.getSketchSize());
    Serial.printf("Free Sketch: %u bytes\n", ESP.getFreeSketchSpace());
    Serial.printf("SDK Version: %s\n", ESP.getSdkVersion());
    Serial.println("==============================================\n");
}

void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
    Serial.begin(115200);
    Serial.setDebugOutput(false);
    delay(1000);

    Serial.println("\n=== XIAO ESP32S3 Sense Camera v" FIRMWARE_VERSION " ===");

    printDiagnostics();

    if (!initCamera()) {
        Serial.println("Camera init failed! Halting.");
        return;
    }

    connectWiFi();

    setupOTA();

    startWebServer();

    Serial.println("System ready!");
}

void loop() {
    handleOTA();
    handleWiFi();

    static unsigned long last_status = 0;
    if (millis() - last_status > 10000) {
        last_status = millis();
        if (isWiFiConnected()) {
            Serial.printf("Stream Ready at: http://%s/\n", WiFi.localIP().toString().c_str());
        } else {
            Serial.println("WiFi NOT Connected!");
        }
    }

    delay(10);
}