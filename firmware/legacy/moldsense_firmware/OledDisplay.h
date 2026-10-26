#pragma once

#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <Wire.h>

#include "BsecMode.h"
#include "CaptureMode.h"
#include "MoldSenseConfig.h"

class OledDisplay {
 public:
  bool begin(TwoWire &wire);
  void showBoot(const String &mode, const String &message);
  void update(DeviceMode mode, const BsecMode &bsec, const CaptureMode &capture);
  bool available() const { return available_; }

 private:
  Adafruit_SSD1306 display_{
    MoldSenseConfig::OLED_WIDTH,
    MoldSenseConfig::OLED_HEIGHT,
    &Wire,
    -1
  };
  bool available_ = false;
  unsigned long lastRefreshMs_ = 0;

  void beginFrame(const String &title);
  void printValueOrDash(float value, uint8_t decimals = 1);
  static bool respondsAt(TwoWire &wire, uint8_t address);
};
