#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <DHTesp.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#if __has_include("secrets.h")
#include "secrets.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID     "Wokwi-GUEST"
#define WIFI_PASSWORD ""
#define WIFI_CHANNEL  6
#endif
#ifndef DEVICE_KEY
#define DEVICE_KEY ""
#endif

const char *API_URL   = "http://iot-ascott.northcentralus.cloudapp.azure.com";
const char *MQTT_NAME = "arrs05";
const char *BROKER_HOST = "135.232.203.144";
const uint16_t BROKER_PORT = 1883;

const int DHT_PIN = 15;
const int LED_PIN = 2;
const unsigned long SEND_EVERY_MS  = 10000;
const unsigned long RETRY_EVERY_MS = 5000;

DHTesp dht;
WiFiClient net;
PubSubClient mqtt(net);

String statusTopic, settingsTopic, fanStateTopic;
unsigned long lastSend = 0, lastAttempt = 0;
bool haveSettings = false;
String fanMode = "off";
float maxHumidity = NAN, lastHumidity = NAN;
String reportedFan = "";

void sendReading(float humidity) {
  char body[80];
  snprintf(body, sizeof(body),
    "{\"mac\": \"%s\", \"humidity\": %.1f}",
    WiFi.macAddress().c_str(), humidity);
  HTTPClient http;
  http.begin(String(API_URL) + "/readings");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", DEVICE_KEY);
  int status = http.POST(body);
  Serial.print("POST -> "); Serial.println(status);
  if (status == 401) Serial.println("Register this fan first.");
  else if (status == 403) Serial.println("Wrong key.");
  http.end();
}

bool connectMqtt() {
  String id = "esp32-" + String(MQTT_NAME) + "-"
            + String((uint32_t)ESP.getEfuseMac(), HEX);
  if (!mqtt.connect(id.c_str(), statusTopic.c_str(), 1, true, "offline"))
    return false;
  mqtt.publish(statusTopic.c_str(), "online", true);
  mqtt.subscribe(settingsTopic.c_str());
  return true;
}

bool parseSettings(const String &msg, String &mode, float &maxHum) {
  JsonDocument doc;
  if (deserializeJson(doc, msg)) return false;
  if (!doc["mode"].is<const char *>()) return false;
  if (!doc["max_humidity"].is<float>() && !doc["max_humidity"].is<int>()) return false;
  String m = doc["mode"].as<const char *>();
  if (m != "auto" && m != "on" && m != "off") return false;
  mode = m;
  maxHum = doc["max_humidity"].as<float>();
  return true;
}

void updateFan() {
  bool on = false;
  if (haveSettings) {
    if      (fanMode == "on")  on = true;
    else if (fanMode == "off") on = false;
    else if (!isnan(lastHumidity) && lastHumidity > maxHumidity) on = true;
  }
  String fan = on ? "on" : "off";
  digitalWrite(LED_PIN, on ? HIGH : LOW);
  if (fan != reportedFan && mqtt.connected()) {
    mqtt.publish(fanStateTopic.c_str(), fan.c_str(), true);
    reportedFan = fan;
  }
}

void onMessage(char *topic, byte *payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  if (String(topic) == settingsTopic) {
    String m; float h;
    if (parseSettings(msg, m, h)) {
      fanMode = m; maxHumidity = h; haveSettings = true;
      updateFan();
    }
  }
}

bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > 15000) return false;
    delay(250);
  }
  Serial.print("MAC address: ");
  Serial.println(WiFi.macAddress());
  return true;
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.begin(115200);
  dht.setup(DHT_PIN, DHTesp::DHT22);
  String base = "ecse3038/" + String(MQTT_NAME);
  statusTopic   = base + "/status";
  settingsTopic = base + "/fan/settings";
  fanStateTopic = base + "/fan/state";
  mqtt.setServer(BROKER_HOST, BROKER_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setKeepAlive(15);
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastAttempt >= RETRY_EVERY_MS)
      { lastAttempt = millis(); connectWiFi(); }
    return;
  }
  if (mqtt.connected()) mqtt.loop();
  else if (millis() - lastAttempt >= RETRY_EVERY_MS)
    { lastAttempt = millis(); connectMqtt(); }
  if (millis() - lastSend < SEND_EVERY_MS) return;
  lastSend = millis();
  float h = dht.getHumidity();
  if (isnan(h)) { Serial.println("No sensor reading"); return; }
  lastHumidity = h;
  sendReading(h);
  updateFan();
}