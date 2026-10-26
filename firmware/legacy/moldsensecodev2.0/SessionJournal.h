#pragma once

#include <Arduino.h>

#include "MoldSenseConfig.h"
#include "PersistentClock.h"

class SessionJournal {
 public:
  bool begin(PersistentClock &clock);
  uint32_t start(DeviceMode mode, const String &label, const String &dataFile);
  void checkpoint(uint32_t rows = 0);
  void end(const String &reason = "STOP");
  bool active() const;
  uint32_t id() const;

 private:
  PersistentClock *clock_ = nullptr;
  bool active_ = false;
  uint32_t id_ = 0;
  DeviceMode mode_ = DeviceMode::LOG;
  String label_;
  String dataFile_;
  uint32_t rows_ = 0;

  void append(const String &event, const String &reason);
  static String modeName(DeviceMode mode);
  static String safeCsv(String value);
};
