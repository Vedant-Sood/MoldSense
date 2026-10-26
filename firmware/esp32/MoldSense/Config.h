#pragma once
// ================== EDIT HARDWARE / PRODUCT SETTINGS HERE ==================
// Defaults target a CLASSIC ESP32 DevKit. Verify the actual PCB before upload.
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define SWITCH_BASELINE_PIN 25
#define SWITCH_MODE_PIN 26
#define WALL_ADC_PIN 34
#define WALL_TOUCH_PIN 13

#include <stdint.h>
#include <stddef.h>
namespace cfg {
enum class WallBackend : uint8_t { AnalogVoltage, Esp32Touch };
constexpr WallBackend wallBackend = WallBackend::Esp32Touch;
constexpr uint8_t bmeAddress = 0x76, oledAddress = 0x3C;
constexpr uint32_t serialBaud = 115200, i2cHz = 100000, i2cTimeoutMs = 25;
constexpr bool debug = true, loggingEnabled = false;
constexpr uint32_t telemetryDefaultMs = 1000, telemetryMinMs = 1000, telemetryMaxMs = 60000;
constexpr uint32_t wallSampleMs = 100, analysisMs = 1000, oledRefreshMs = 500;
constexpr uint32_t detailPageMs = 5000, switchDebounceMs = 60, switchArmMs = 2000;
constexpr uint32_t retryMs = 10000, bmeStaleMs = 45000, wallStaleMs = 2000;
constexpr uint32_t logIntervalMs = 60000, logFlushMs = 300000;
constexpr size_t logBufferBytes = 3072, logMaxBytes = 256 * 1024;
constexpr uint32_t bsecSaveRetryMs = 60000;
constexpr uint32_t bsecSaveMs = 6UL * 60 * 60 * 1000, bsecFirstSaveMs = 10UL * 60 * 1000;
constexpr uint32_t baselineDurationMs = 60000, baselineSampleMs = 500;
constexpr size_t baselineCapacity = baselineDurationMs / baselineSampleMs + 1;
constexpr float baselineMinCoverage = .80f, baselineMaxCV = .03f;
constexpr float baselineMaxDrift = .03f, baselineMaxRhRange = 5, baselineMaxTempRange = 2;
constexpr uint32_t baselineWriteCooldownMs = 60000, commandArmMs = 15000;
constexpr size_t medianWindow = 7;
constexpr float wallEmaAlpha = .18f, maxBatchSpreadFraction = .12f;
// These are instrument transfer parameters, NOT material moisture percentages.
// ADC wet response assumed increasing; classic ESP32 touch counts decrease.
constexpr float wetDirection = wallBackend == WallBackend::AnalogVoltage ? 1.f : -1.f;
constexpr float dryDeadbandFraction = .03f, wetSpanFraction = .30f;
constexpr float noiseSigmaMultiplier = 3, noiseFloor = 2;
constexpr float wallRawMin = wallBackend == WallBackend::AnalogVoltage ? 20.f : 2.f;
constexpr float wallRawMax = wallBackend == WallBackend::AnalogVoltage ? 4075.f : 65500.f;
// A biased analog front-end is REQUIRED for reliable open-circuit detection.
constexpr float bmeTemperatureOffset = 0; // Measure enclosure self-heating; no invented offset.
constexpr float minAirTemp = -40, maxAirTemp = 85, minPressurePa = 30000, maxPressurePa = 110000;
constexpr size_t rollingSamples = 60; // One-minute means at the default analysis rate.
struct RiskSettings {
  float rhCaution = 60, rhSevere = 90; // EPA <60% target; 90% is an engineering ramp endpoint.
  float wallAbnormal = 25; // Relative index alert: characterize on the actual wall/probe.
  float nearDewPointC = 3; // Engineering margin; actual condensation requires Ts <= Td.
  float airPersistenceHours = 24, wallPersistenceHours = 24, condensationHours = 6;
  float maxExposureHours = 720; // Saturates counters safely at 30 observed days.
  float decayHours = 48;        // Screening-memory decay, not a validated biological death rate.
  float instantFraction = .20f; // Limits a transient's contribution.
  float environmentWeight = .50f, wallWeight = .70f, condensationWeight = .35f, vocWeight = .65f;
  float elevatedThreshold = 25, highThreshold = 50, criticalThreshold = 75;
  float criticalHoldHours = 6; // No CRITICAL from one short measurement.
  float minimumConfidence = 20;
  float wallInstantFraction = .65f;
  float temperatureMin = 0, temperatureLow = 10, temperatureHigh = 40, temperatureMax = 50,
        temperatureFloor = .2f;
  float maxIntegratedStepSeconds = 5; // Gaps are unknown exposure, never counted as wet/dry.
};
constexpr RiskSettings risk{};
// Changing this identity invalidates a baseline when geometry/material/front-end changes.
constexpr uint32_t wallSetupId = 1;
static_assert(SWITCH_BASELINE_PIN != SWITCH_MODE_PIN, "Switch pins must differ");
static_assert(medianWindow % 2 == 1 && baselineCapacity <= 1024,
              "Bounded filter/calibration storage");
static_assert(wallEmaAlpha > 0 && wallEmaAlpha <= 1 && wetSpanFraction > dryDeadbandFraction,
              "Invalid filter");
static_assert(baselineSampleMs >= wallSampleMs && analysisMs > 0, "Invalid sample schedule");
} // namespace cfg

// GPIO validity is intentionally constrained to the supported classic ESP32 profile.
static_assert(I2C_SDA_PIN != I2C_SCL_PIN && SWITCH_BASELINE_PIN != I2C_SDA_PIN &&
                  SWITCH_BASELINE_PIN != I2C_SCL_PIN && SWITCH_MODE_PIN != I2C_SDA_PIN &&
                  SWITCH_MODE_PIN != I2C_SCL_PIN,
              "GPIO collision");
static_assert(cfg::wallBackend != cfg::WallBackend::AnalogVoltage ||
                  (WALL_ADC_PIN >= 32 && WALL_ADC_PIN <= 39),
              "Use a classic ESP32 ADC1 pin for this analog driver");
static_assert(cfg::wallBackend != cfg::WallBackend::Esp32Touch ||
                  (WALL_TOUCH_PIN == 4 || WALL_TOUCH_PIN == 0 || WALL_TOUCH_PIN == 2 ||
                   WALL_TOUCH_PIN == 15 || WALL_TOUCH_PIN == 13 || WALL_TOUCH_PIN == 12 ||
                   WALL_TOUCH_PIN == 14 || WALL_TOUCH_PIN == 27 || WALL_TOUCH_PIN == 33 ||
                   WALL_TOUCH_PIN == 32),
              "Invalid classic ESP32 touch pin");

constexpr int activeWallPin =
    cfg::wallBackend == cfg::WallBackend::Esp32Touch ? WALL_TOUCH_PIN : WALL_ADC_PIN;
static_assert(activeWallPin != I2C_SDA_PIN && activeWallPin != I2C_SCL_PIN &&
                  activeWallPin != SWITCH_BASELINE_PIN && activeWallPin != SWITCH_MODE_PIN,
              "Wall pin collision");
static_assert(cfg::risk.rhSevere > cfg::risk.rhCaution && cfg::risk.airPersistenceHours > 0 &&
                  cfg::risk.wallPersistenceHours > 0 && cfg::risk.condensationHours > 0 &&
                  cfg::risk.decayHours > 0 && cfg::risk.nearDewPointC > 0,
              "Invalid risk denominator");
