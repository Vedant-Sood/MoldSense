#pragma once
#include "../Core/Math.h"
namespace ms {
class MoldRiskEngine {
public:
  RiskResult update(const AirReading &, const WallReading &, const SurfaceReading &,
                    const VocResult &, uint32_t now, bool observe = true);
  void newSite();
  RollingMeans rolling() const;

private:
  float rhDose_ = 0, wallDose_ = 0, condDose_ = 0, rhHours_ = 0, wallHours_ = 0, condHours_ = 0,
        highHours_ = 0;
  uint32_t last_ = 0, events_ = 0, consecutive_ = 0;
  bool started_ = false, prevAir_ = false, prevWall_ = false, prevSurface_ = false,
       wasCond_ = false, prevHigh_ = false;
  float rhHistory_[cfg::rollingSamples]{}, wallHistory_[cfg::rollingSamples]{},
      condHistory_[cfg::rollingSamples]{}, scoreHistory_[cfg::rollingSamples]{};
  size_t historyIndex_ = 0, historyCount_ = 0;
};
} // namespace ms
