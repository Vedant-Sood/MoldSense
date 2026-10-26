#pragma once
#include "../Core/Math.h"
namespace ms {
class BaselineManager {
public:
  bool start(uint32_t now);
  void cancel() {
    active_ = false;
    status_ = "CANCELLED";
  }
  void tick(uint32_t now, const WallReading &, const AirReading &);
  bool takeResult(Baseline &result);
  Baseline statistics() const;
  bool active() const {
    return active_;
  }
  uint8_t progress(uint32_t now) const;
  const char *status() const {
    return status_;
  }
  uint16_t count() const {
    return count_;
  }

private:
  void finish();
  struct Sample {
    float wall, t, rh;
  };
  Sample samples_[cfg::baselineCapacity]{};
  float work_[cfg::baselineCapacity]{};
  uint32_t start_ = 0, last_ = 0;
  uint16_t count_ = 0;
  bool active_ = false, ready_ = false;
  Baseline result_{};
  const char *status_ = "IDLE";
};
} // namespace ms
