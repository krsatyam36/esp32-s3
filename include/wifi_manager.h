#pragma once

#include <WiFi.h>
#include <Arduino.h>

#define WIFI_TIMEOUT_MS 20000
#define WIFI_RECONNECT_DELAY_MS 10000
#include "config.h"

static unsigned long last_wifi_check = 0;
static const unsigned long WIFI_CHECK_INTERVAL = 10000;

#ifndef WIFI_MAX_ATTEMPTS
#define WIFI_MAX_ATTEMPTS 40
#endif

// Handle connectWiFi request/operation.
void connectWiFi() {
    Serial.printf("Connecting to WiFi: %s\n", ssid);
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(ssid, password);

    int attempts = 0;
    int max_attempts = WIFI_MAX_ATTEMPTS;
    while (WiFi.status() != WL_CONNECTED && attempts < max_attempts) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\nWiFi connection failed");
    }
}

// Handle handleWiFi request/operation.
void handleWiFi() {
    if (millis() - last_wifi_check < WIFI_CHECK_INTERVAL) return;
    last_wifi_check = millis();

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi lost! Reconnecting...");
        WiFi.reconnect();
    }
}

bool isWiFiConnected() {
    return WiFi.status() == WL_CONNECTED;
}
