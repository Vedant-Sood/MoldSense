#pragma once

#include <Arduino.h>

#include "MoldSenseConfig.h"

class ModeSwitch {
 public:
  void begin();
  bool read(DeviceMode &mode) const;
  bool changed(DeviceMode currentMode, DeviceMode &nextMode);
  String status() const;

 private:
  static constexpr uint8_t INVALID_SELECTION = 0xFF;

  uint8_t readCode() const;
  uint8_t candidate_ = INVALID_SELECTION;
  uint8_t stable_ = INVALID_SELECTION;
  uint32_t candidateSinceMs_ = 0;
};
