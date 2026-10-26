#pragma once

#include <Arduino.h>

class Dht22Verifier {
 public:
  void begin();
  void loop(float bmeTemperature, float bmeHumidity);
  void printStatus(float bmeTemperature, float bmeHumidity) const;

  bool valid() const { return valid_; }
  float temperature() const { return temperature_; }
  float humidity() const { return humidity_; }

 private:
  bool readSensor(float &temperature, float &humidity);
  static bool measureLevel(uint8_t level, uint32_t timeoutUs, uint32_t &durationUs);
  void printComparison(float bmeTemperature, float bmeHumidity) const;

  bool valid_ = false;
  float temperature_ = NAN;
  float humidity_ = NAN;
  unsigned long lastAttemptMs_ = 0;
  unsigned long lastSuccessMs_ = 0;
  uint32_t successfulReads_ = 0;
  uint32_t failedReads_ = 0;
};
