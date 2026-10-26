#pragma once
#include <stdint.h>
#include <stddef.h>
#include <math.h>
#include "../../Config.h"
namespace ms {
inline float clamp01(float x) {
  return fminf(1.f, fmaxf(0.f, x));
}
inline bool finite(float x) {
  return isfinite(x);
}
inline bool elapsed(uint32_t now, uint32_t then, uint32_t ms) {
  return uint32_t(now - then) >= ms;
}
enum class WallStatus : uint8_t { Warming, Ok, RangeFault, Noisy, Stale };
enum class Mode : uint8_t {
  Boot,
  SelfTest,
  NormalScan,
  DetailView,
  BaselineCalibration,
  SensorError
};
enum class RiskLevel : uint8_t { Low, Elevated, High, Critical, Unknown };
inline const char *riskName(RiskLevel r) {
  switch (r) {
  case RiskLevel::Low:
    return "LOW";
  case RiskLevel::Elevated:
    return "ELEVATED";
  case RiskLevel::High:
    return "HIGH";
  case RiskLevel::Critical:
    return "CRITICAL";
  default:
    return "UNKNOWN";
  }
}
inline const char *wallName(WallStatus r) {
  switch (r) {
  case WallStatus::Ok:
    return "OK";
  case WallStatus::RangeFault:
    return "OPEN/SATURATION";
  case WallStatus::Noisy:
    return "NOISY";
  case WallStatus::Stale:
    return "STALE";
  default:
    return "WARMING";
  }
}
struct AirReading {
  float rawTemperature = NAN, temperature = NAN, rawHumidity = NAN, humidity = NAN;
  float pressure = NAN, gasOhms = NAN, iaq = NAN, staticIaq = NAN, co2Equivalent = NAN,
        breathVocEquivalent = NAN;
  float classes[4] = {NAN, NAN, NAN, NAN};
  uint8_t iaqAccuracy = 0, gasAccuracy = 0, stabilization = 0, runIn = 0;
  uint32_t sampleMs = 0, gasMs = 0, iaqMs = 0, gasObservationMs = 0;
  uint64_t gasSequence = 0, observationId = 0;
  uint8_t heaterIndex = 0;
  bool valid = false, gasValid = false, iaqValid = false;
  int bsecStatus = 0, bmeStatus = 0;
};
struct Baseline {
  uint32_t setupId = 0;
  uint16_t count = 0, total = 0;
  float mean = NAN, median = NAN, stddev = NAN, confidence = 0;
  float temperature = NAN, humidity = NAN, dewPoint = NAN, typicalMoisture = 0;
};
struct WallReading {
  float raw = NAN, filtered = NAN, baseline = NAN, delta = NAN, index = NAN, confidence = 0;
  uint32_t sampleMs = 0;
  bool valid = false, baselineValid = false;
  WallStatus status = WallStatus::Warming;
};
struct SurfaceReading {
  float temperature = NAN;
  bool valid = false;
}; // Future measured surface input.
struct VocResult {
  float probability = NAN, confidence = 0;
  bool valid = false, modelValid = false;
  const char *status = "VOC MODEL: NOT TRAINED";
};
struct RiskResult {
  float probability = NAN, confidence = 0, dewPoint = NAN, surfaceRh = NAN;
  float environment = NAN, wall = NAN, condensation = NAN, voc = NAN;
  float contributions[4] = {0, 0, 0, 0}; // Sequential marginal contributions; sum exactly to score.
  float rhHours = 0, wallHours = 0, condensationHours = 0, elevatedHours = 0;
  uint32_t condensationEvents = 0, consecutiveElevated = 0;
  RiskLevel level = RiskLevel::Unknown;
  bool valid = false, degraded = true, surfaceAvailable = false;
};
struct RollingMeans {
  float rh = NAN, wall = NAN, condensation = NAN, probability = NAN;
  uint16_t count = 0;
};
} // namespace ms
