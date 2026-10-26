#pragma once

#include <Arduino.h>

class PersistentClock {
 public:
  void begin();
  bool setUnixTime(uint64_t epoch);
  bool valid() const;
  uint64_t now() const;
  String iso8601() const;
  String quality() const;
  void checkpoint();

 private:
  bool valid_ = false;
  String quality_ = "UNSET";
};
