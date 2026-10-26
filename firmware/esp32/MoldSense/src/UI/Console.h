#pragma once
#include <Arduino.h>
#include "../../Config.h"
namespace ms {
class Console {
public:
  using Handler = void (*)(const char *);
  void begin(Handler handler) {
    handler_ = handler;
    Serial.begin(cfg::serialBaud);
  }
  void tick(bool pumpingDump);
  void print(const char *fmt, ...);
  bool idle() const {
    return txRead_ == txUsed_;
  }
  uint32_t dropped() const {
    return dropped_;
  }

private:
  Handler handler_ = nullptr;
  char input_[96]{}, tx_[4096]{};
  size_t inputUsed_ = 0, txUsed_ = 0, txRead_ = 0;
  bool overflow_ = false;
  uint32_t dropped_ = 0;
};
} // namespace ms
