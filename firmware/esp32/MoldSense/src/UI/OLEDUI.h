#pragma once
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "../Core/Types.h"
namespace ms {
struct ViewState {
  Mode mode = Mode::Boot;
  AirReading air;
  WallReading wall;
  VocResult voc;
  RiskResult risk;
  bool bmeReady = false, storage = false, baseline = false;
  uint8_t progress = 0;
  uint64_t uptimeMs = 0;
  uint32_t baselineId = 0;
  const char *calibration = "IDLE";
  const char *bsecState = "UNKNOWN";
};
class OLEDUI {
public:
  void tick(uint32_t now, const ViewState &);
  bool ok() const {
    return ok_;
  }

private:
  void draw(uint32_t, const ViewState &);
  void line(uint8_t y, const char *format, ...);
  Adafruit_SSD1306 display_{128, 64, &Wire, -1, cfg::i2cHz, cfg::i2cHz};
  uint8_t previous_[1024]{};
  uint32_t last_ = 0, retry_ = 0;
  bool ok_ = false, first_ = true, attempted_ = false;
};
} // namespace ms
