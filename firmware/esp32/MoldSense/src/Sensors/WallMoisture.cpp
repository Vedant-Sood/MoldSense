#include "WallMoisture.h"
#ifndef MOLDSENSE_HOST_TEST
#include <Arduino.h>
#if !CONFIG_IDF_TARGET_ESP32
#error                                                                                             \
    "This touch/ADC pin profile is validated for classic ESP32 only; port Config and driver for other targets."
#endif
#endif
namespace ms {
void WallMoisture::begin() {
#ifndef MOLDSENSE_HOST_TEST
  if (cfg::wallBackend == cfg::WallBackend::AnalogVoltage) {
    analogReadResolution(12);
    analogSetPinAttenuation(WALL_ADC_PIN, ADC_11db);
    pinMode(WALL_ADC_PIN, INPUT);
  }
#endif
}
void WallMoisture::tick(uint32_t now, const Baseline *baseline) {
#ifndef MOLDSENSE_HOST_TEST
  if (!elapsed(now, lastSample_, cfg::wallSampleMs))
    return;
  lastSample_ = now;
  float raw = cfg::wallBackend == cfg::WallBackend::AnalogVoltage ? analogRead(WALL_ADC_PIN)
                                                                  : touchRead(WALL_TOUCH_PIN);
  ingest(raw, now, baseline);
#endif
}
void WallMoisture::ingest(float raw, uint32_t now, const Baseline *baseline) {
  data_.raw = raw;
  data_.sampleMs = now;
  data_.valid = false;
  data_.index = NAN;
  data_.delta = NAN;
  data_.confidence = 0;
  data_.baselineValid = baseline && baseline->setupId == wallIdentity() &&
                        finite(baseline->median) && baseline->median > cfg::wallRawMin;
  data_.baseline = data_.baselineValid ? baseline->median : NAN;
  if (!finite(raw) || raw <= cfg::wallRawMin || raw >= cfg::wallRawMax) {
    data_.status = WallStatus::RangeFault;
    data_.filtered = NAN;
    count_ = 0;
    pos_ = 0;
    emaReady_ = false;
    return;
  }
  samples_[pos_] = raw;
  pos_ = (pos_ + 1) % cfg::medianWindow;
  if (count_ < cfg::medianWindow)
    ++count_;
  if (count_ < cfg::medianWindow) {
    data_.status = WallStatus::Warming;
    return;
  }
  float sorted[cfg::medianWindow];
  for (size_t i = 0; i < count_; i++)
    sorted[i] = samples_[i];
  float med = median(sorted, count_);
  // Ignore extreme endpoints; a real step becomes valid once the majority settles.
  float spread = sorted[count_ - 2] - sorted[1];
  if (spread > fmaxf(cfg::noiseFloor, med * cfg::maxBatchSpreadFraction)) {
    data_.status = WallStatus::Noisy;
    emaReady_ = false;
    return;
  }
  data_.filtered = emaReady_ ? data_.filtered + cfg::wallEmaAlpha * (med - data_.filtered) : med;
  emaReady_ = true;
  data_.valid = true;
  data_.status = WallStatus::Ok;
  if (data_.baselineValid) {
    data_.delta = data_.filtered - baseline->median;
    float dead = fmaxf(baseline->median * cfg::dryDeadbandFraction,
                       cfg::noiseSigmaMultiplier * baseline->stddev);
    float span = baseline->median * cfg::wetSpanFraction;
    data_.index = 100 * clamp01((cfg::wetDirection * data_.delta - dead) /
                                fmaxf(cfg::noiseFloor, span - dead));
    // Touch cannot positively verify contact/open-circuit; reserve confidence accordingly.
    data_.confidence =
        baseline->confidence * (cfg::wallBackend == cfg::WallBackend::Esp32Touch ? .9f : 1.f);
  }
}
} // namespace ms
