/* Basic copper-comb capacitance reader for classic ESP32-WROOM/DevKit.
   Comb A -> GPIO13 (T4); comb B -> GND. The combs must not touch.
   Output is relative capacitive-touch units, not calibrated picofarads. */

#include <Arduino.h>

constexpr uint8_t TOUCH_PIN = 13;
constexpr uint16_t SAMPLE_COUNT = 32;
constexpr uint16_t CALIBRATION_READS = 120;
uint32_t baseline = 0;

uint32_t readCapacitanceRaw() {
  uint64_t total = 0;
  for (uint16_t i = 0; i < SAMPLE_COUNT; ++i) {
    total += touchRead(TOUCH_PIN);
    delayMicroseconds(250);
  }
  return static_cast<uint32_t>(total / SAMPLE_COUNT);
}

void calibrate() {
  Serial.println("Calibrating: keep the plate clear...");
  delay(1500);
  uint64_t total = 0;
  for (uint16_t i = 0; i < CALIBRATION_READS; ++i) {
    total += readCapacitanceRaw();
    delay(5);
  }
  baseline = static_cast<uint32_t>(total / CALIBRATION_READS);
  Serial.print("Baseline = ");
  Serial.println(baseline);
  Serial.println("Send c to recalibrate.");
  Serial.println("raw,change_from_baseline,change_percent");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("ESP32 copper-comb capacitance reader");
  calibrate();
}

void loop() {
  if (Serial.available()) {
    const char command = Serial.read();
    if (command == 'c' || command == 'C') calibrate();
  }

  const uint32_t raw = readCapacitanceRaw();
  const int32_t change = static_cast<int32_t>(baseline) - static_cast<int32_t>(raw);
  const float percent = baseline ? (100.0f * change / baseline) : 0.0f;

  Serial.print(raw);
  Serial.print(',');
  Serial.print(change);
  Serial.print(',');
  Serial.println(percent, 2);
  delay(200);
}
