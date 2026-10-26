#pragma once
#include "../Core/Math.h"
namespace ms {
class WallMoisture {
public:
  void begin();
  void tick(uint32_t now, const Baseline *baseline);
  const WallReading &reading() const {
    return data_;
  }
  // Public deterministic front-end enables replay testing and future alternate probes.
  void ingest(float raw, uint32_t now, const Baseline *baseline);

private:
  WallReading data_;
  float samples_[cfg::medianWindow]{};
  size_t count_ = 0, pos_ = 0;
  uint32_t lastSample_ = 0;
  bool emaReady_ = false;
};
} // namespace ms
