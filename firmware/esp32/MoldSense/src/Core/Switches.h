#pragma once
#include "Types.h"
#ifndef MOLDSENSE_HOST_TEST
#include <Arduino.h>
#endif
namespace ms {
class DebouncedSwitch {
public:
  void begin(int pin, bool raw, uint32_t now) {
    pin_ = pin;
    stable_ = candidate_ = raw;
    changedAt_ = now;
  }
  bool update(bool raw, uint32_t now) {
    if (raw != candidate_) {
      candidate_ = raw;
      changedAt_ = now;
    }
    if (candidate_ != stable_ && elapsed(now, changedAt_, cfg::switchDebounceMs)) {
      stable_ = candidate_;
      return true;
    }
    return false;
  }
  bool active() const {
    return stable_;
  }
#ifndef MOLDSENSE_HOST_TEST
  void begin(int pin, uint32_t now) {
    pinMode(pin, INPUT_PULLUP);
    begin(pin, digitalRead(pin) == LOW, now);
  }
  bool tick(uint32_t now) {
    return update(digitalRead(pin_) == LOW, now);
  }
#endif
private:
  int pin_ = 0;
  uint32_t changedAt_ = 0;
  bool stable_ = false, candidate_ = false;
};
} // namespace ms
