#include "OLEDUI.h"
#include <stdarg.h>
#include <string.h>
namespace ms {
void OLEDUI::line(uint8_t y, const char *format, ...) {
  char text[32];
  va_list args;
  va_start(args, format);
  vsnprintf(text, sizeof(text), format, args);
  va_end(args);
  display_.setTextSize(1);
  display_.setCursor(0, y);
  display_.print(text);
}
void OLEDUI::tick(uint32_t now, const ViewState &v) {
  if (!ok_) {
    if (attempted_ && !elapsed(now, retry_, cfg::retryMs))
      return;
    attempted_ = true;
    retry_ = now;
    Wire.beginTransmission(cfg::oledAddress);
    if (Wire.endTransmission() != 0)
      return;
    ok_ = display_.begin(SSD1306_SWITCHCAPVCC, cfg::oledAddress, false, false);
    if (!ok_)
      return;
    first_ = true;
  }
  if (!first_ && !elapsed(now, last_, cfg::oledRefreshMs))
    return;
  last_ = now;
  Wire.beginTransmission(cfg::oledAddress);
  if (Wire.endTransmission() != 0) {
    ok_ = false;
    return;
  }
  draw(now, v);
  if (first_ || memcmp(previous_, display_.getBuffer(), sizeof(previous_)) != 0) {
    display_.display();
    memcpy(previous_, display_.getBuffer(), sizeof(previous_));
    first_ = false;
  }
}
void OLEDUI::draw(uint32_t now, const ViewState &v) {
  display_.clearDisplay();
  display_.setTextColor(SSD1306_WHITE);
  line(0, "MOLDSENSE");
  if (v.mode == Mode::Boot || v.mode == Mode::SelfTest) {
    line(12, "Starting / self-check");
    line(24, "BME688  %s", v.bmeReady ? "READY" : "WAIT / FAIL");
    line(34, "Probe   %s", wallName(v.wall.status));
    line(44, "Baseline %s", v.baseline ? "LOADED" : "MISSING");
    line(54, "AI %s", v.voc.modelValid ? "LOADED" : "NOT TRAINED");
    return;
  }
  if (v.mode == Mode::BaselineCalibration) {
    line(17, "CALIBRATING %u%%", v.progress);
    display_.drawRect(0, 32, 126, 10, SSD1306_WHITE);
    display_.fillRect(2, 34, 122 * v.progress / 100, 6, SSD1306_WHITE);
    line(48, "Hold on dry reference");
    line(57, "BSEC learning retained");
    return;
  }
  if (v.mode == Mode::DetailView) {
    switch ((now / cfg::detailPageMs) % 5) {
    case 0:
      line(12, "T %.1f C RH %.1f%%", v.air.valid ? v.air.temperature : NAN,
           v.air.valid ? v.air.humidity : NAN);
      line(23, "Dew point %.1f C", v.risk.dewPoint);
      line(34, "Surface RH %.1f%%", v.risk.surfaceRh);
      line(45, "Condensation %s", v.risk.surfaceAvailable ? "MEASURED" : "UNKNOWN");
      line(56, "RH exposure %.1f h", v.risk.rhHours);
      break;
    case 1:
      line(12, "Probe %s", wallName(v.wall.status));
      line(23, "Raw %.0f Avg %.0f", v.wall.raw, v.wall.filtered);
      line(34, "Base %.0f", v.wall.baseline);
      line(45, "Delta %.1f", v.wall.delta);
      line(56, "Wall index %.0f", v.wall.index);
      break;
    case 2:
      line(12, "Gas %.0f ohm", v.air.gasOhms);
      line(23, "IAQ %.0f acc %u", v.air.iaqValid ? v.air.iaq : NAN, v.air.iaqAccuracy);
      line(34, "VOC p %.2f", v.voc.probability);
      line(45, "%s", v.voc.status);
      line(56, "Stab %u Run %u", v.air.stabilization, v.air.runIn);
      break;
    case 3:
      line(12, "BME %d BSEC %d", v.air.bmeStatus, v.air.bsecStatus);
      line(23, "NVS/Logs %s", v.storage ? "OK" : "CHECK");
      line(34, "BSEC %s", v.bsecState);
      line(45, "Up %llu s", (unsigned long long)(v.uptimeMs / 1000));
      line(56, "Conf %.0f%%", v.risk.confidence);
      break;
    default:
      line(12, "Env %.0f Wall %.0f", v.risk.environment, v.risk.wall);
      line(23, "Score %.0f%% %s", v.risk.probability, riskName(v.risk.level));
      line(34, "Wall wet %.1f h", v.risk.wallHours);
      line(45, "%s", v.calibration);
      line(56, "*Unvalidated index");
      break;
    }
    return;
  }
  line(11, "MOLD INDEX*  %s", v.risk.degraded ? "PARTIAL" : "");
  display_.setTextSize(2);
  display_.setCursor(0, 23);
  if (v.risk.valid) {
    display_.print(int(v.risk.probability + .5f));
    display_.print('%');
  } else
    display_.print("--");
  display_.setTextSize(1);
  display_.setCursor(64, 25);
  display_.print(riskName(v.risk.level));
  line(41, "Wall %.0f RH %.0f%%", v.wall.index, v.air.valid ? v.air.humidity : NAN);
  if (!v.baseline)
    line(53, "BASELINE REQUIRED");
  else if (!v.wall.valid || !v.air.valid)
    line(53, "SENSOR CHECK C%.0f", v.risk.confidence);
  else if (!v.voc.modelValid)
    line(53, "VOC MODEL: NOT TRAINED");
  else
    line(53, "%s C%.0f", v.wall.index >= cfg::risk.wallAbnormal ? "WALL ABNORMAL" : "RELATIVE RISK",
         v.risk.confidence);
}
} // namespace ms
