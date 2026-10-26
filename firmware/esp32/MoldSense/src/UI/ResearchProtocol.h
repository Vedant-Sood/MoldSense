#pragma once
#include "Console.h"
#include "OLEDUI.h"
#include "../Core/Math.h"
namespace ms {
class ResearchProtocol {
public:
  void begin(Console &c, uint32_t session);
  void packet(const char *type, uint64_t uptime);
  void number(const char *key, double value);
  void integer(const char *key, uint64_t value);
  void text(const char *key, const char *value);
  void boolean(const char *key, bool value);
  void finish();
  void ack(const char *command, uint32_t request, bool success, const char *reason, uint64_t uptime,
           uint32_t token = 0);
  void reading(const ViewState &v, uint32_t site, uint64_t uptime, uint32_t interval);
  const char *deviceId() const {
    return device_;
  }

private:
  void add(const char *format, ...);
  Console *console_ = nullptr;
  char packet_[3072]{}, device_[32]{};
  size_t used_ = 0;
  bool overflow_ = false;
  uint64_t sequence_ = 0;
  uint32_t boot_ = 0;
};
} // namespace ms
