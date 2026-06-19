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

#ifndef NTP_SERVER
#define NTP_SERVER "pool.ntp.org"
#endif
#ifndef NTP_OFFSET
#define NTP_OFFSET 0
#endif
#ifndef NTP_INTERVAL
#define NTP_INTERVAL 3600000
#endif

static bool ntp_synced = false;

void syncNTP() {
    configTime(NTP_OFFSET, 0, NTP_SERVER);
    Serial.printf("Syncing NTP from %s...\n", NTP_SERVER);
    time_t now = time(nullptr);
    int retries = 0;
    while (now < 100000 && retries < 10) {
        delay(500);
        now = time(nullptr);
        retries++;
    }
    if (now >= 100000) {
        ntp_synced = true;
        struct tm *ti = localtime(&now);
        Serial.printf("NTP sync OK: %04d-%02d-%02d %02d:%02d:%02d\n",
            ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
            ti->tm_hour, ti->tm_min, ti->tm_sec);
    } else {
        Serial.println("NTP sync failed (will retry in loop)");
    }
}

static unsigned long last_ntp_sync = 0;

void setLedPattern(int pattern) {
    pinMode(LED_BUILTIN, OUTPUT);
    switch (pattern) {
        case 0:
            digitalWrite(LED_BUILTIN, HIGH); delay(200);
            digitalWrite(LED_BUILTIN, LOW);  delay(200);
            digitalWrite(LED_BUILTIN, HIGH); delay(200);
            digitalWrite(LED_BUILTIN, LOW);
            break;
        case 1:
            for (int i = 0; i < 3; i++) {
                digitalWrite(LED_BUILTIN, HIGH); delay(300);
                digitalWrite(LED_BUILTIN, LOW);  delay(300);
            }
            break;
        case 2:
            digitalWrite(LED_BUILTIN, HIGH);
            break;
        case 3:
            for (int i = 0; i < 5; i++) {
                digitalWrite(LED_BUILTIN, HIGH); delay(100);
                digitalWrite(LED_BUILTIN, LOW);  delay(100);
            }
            break;
    }
}
void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
    Serial.begin(115200);
    Serial.setDebugOutput(false);
    delay(1000);

    Serial.println("\n=== XIAO ESP32S3 Sense Camera v" FIRMWARE_VERSION " ===");

    printDiagnostics();

    setLedPattern(0);

    if (!initCamera()) {
        Serial.println("Camera init failed! Halting.");
        setLedPattern(3); // Error pattern
        return;
    }

    connectWiFi();

    setLedPattern(1); // WiFi connecting pattern

    setupOTA();

    startWebServer();

    if (isWiFiConnected()) {
        syncNTP();
        setLedPattern(2); // Streaming pattern
    }

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

    if (isWiFiConnected() && !ntp_synced && millis() - last_ntp_sync > 30000) {
        last_ntp_sync = millis();
        syncNTP();
    } else if (isWiFiConnected() && ntp_synced && millis() - last_ntp_sync > NTP_INTERVAL) {
        last_ntp_sync = millis();
        syncNTP();
    }

    delay(10);
}