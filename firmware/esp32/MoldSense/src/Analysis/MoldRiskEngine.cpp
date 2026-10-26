#include "MoldRiskEngine.h"
namespace ms {
static float dose(float old, float intensity, float hours, float horizon) {
  if (intensity > 0)
    return fminf(horizon, old + hours * intensity);
  return fmaxf(0.f, old - hours * horizon / cfg::risk.decayHours);
}
void MoldRiskEngine::newSite() {
  *this = MoldRiskEngine();
}
RiskResult MoldRiskEngine::update(const AirReading &a, const WallReading &w,
                                  const SurfaceReading &s, const VocResult &v, uint32_t now,
                                  bool observe) {
  const auto &c = cfg::risk;
  RiskResult r;
  float dt = started_ ? uint32_t(now - last_) / 1000.f : 0;
  last_ = now;
  started_ = true;
  bool gap = dt > c.maxIntegratedStepSeconds;
  if (gap || !observe)
    dt = 0;
  const float h = dt / 3600.f;
  bool air = observe && a.valid && finite(a.temperature) && finite(a.humidity) && a.humidity > 0 &&
             a.humidity <= 100 && !elapsed(now, a.sampleMs, cfg::bmeStaleMs);
  bool wall = observe && w.valid && w.baselineValid && finite(w.index) &&
              !elapsed(now, w.sampleMs, cfg::wallStaleMs);
  bool surf =
      air && s.valid && finite(s.temperature) && s.temperature >= -40 && s.temperature <= 85;
  if (air)
    r.dewPoint = dewPoint(a.temperature, a.humidity);
  float er = 0, wr = wall ? clamp01(w.index / 100) : 0, cr = 0;
  if (air) {
    er = clamp01((a.humidity - c.rhCaution) / (c.rhSevere - c.rhCaution));
    // Air RH alone does not describe wall-surface water activity.
    // Temperature modifies favorable airborne conditions; it cannot rule out past mold.
    float tf = c.temperatureFloor;
    if (a.temperature > c.temperatureMin && a.temperature < c.temperatureMax)
      tf = a.temperature < c.temperatureLow
               ? c.temperatureFloor + (1 - c.temperatureFloor) *
                                          (a.temperature - c.temperatureMin) /
                                          (c.temperatureLow - c.temperatureMin)
           : a.temperature > c.temperatureHigh
               ? 1 - (1 - c.temperatureFloor) * (a.temperature - c.temperatureHigh) /
                         (c.temperatureMax - c.temperatureHigh)
               : 1;
    er *= tf;
  }
  if (surf) {
    r.surfaceRh = surfaceRH(a.temperature, a.humidity, s.temperature);
    r.surfaceAvailable = true;
    // Sensitive-material RHcrit from ASHRAE 160 addendum e (2016), NOT full VTT.
    float t = s.temperature;
    float critical = t <= 20 ? (-.00267f * t * t * t + .160f * t * t - 3.13f * t + 100) : 80;
    if (t > 0 && t < 50)
      er = fmaxf(er, clamp01((r.surfaceRh - critical) / fmaxf(1.f, 100 - critical)));
    cr = clamp01((c.nearDewPointC - (t - r.dewPoint)) / c.nearDewPointC);
  }
  if (air && prevAir_ && !gap) {
    rhDose_ = dose(rhDose_, er, h, c.airPersistenceHours);
    if (a.humidity > c.rhCaution)
      rhHours_ = fminf(c.maxExposureHours, rhHours_ + h);
  }
  if (wall && prevWall_ && !gap) {
    wallDose_ = dose(wallDose_, wr, h, c.wallPersistenceHours);
    if (w.index >= c.wallAbnormal)
      wallHours_ = fminf(c.maxExposureHours, wallHours_ + h);
  }
  if (surf && prevSurface_ && !gap) {
    condDose_ = dose(condDose_, cr, h, c.condensationHours);
    if (s.temperature <= r.dewPoint)
      condHours_ = fminf(c.maxExposureHours, condHours_ + h);
  }
  // Count only observed dry->condensing edges. Reconnection is not a new event.
  bool cond = surf && s.temperature <= r.dewPoint;
  if (cond && prevSurface_ && !wasCond_ && !gap && events_ < UINT32_MAX)
    ++events_;
  wasCond_ = cond;
  prevAir_ = air;
  prevWall_ = wall;
  prevSurface_ = surf;
  if (air)
    r.environment = 100 * (c.instantFraction * er +
                           (1 - c.instantFraction) * clamp01(rhDose_ / c.airPersistenceHours));
  if (wall)
    r.wall = 100 * (c.wallInstantFraction * wr +
                    (1 - c.wallInstantFraction) * clamp01(wallDose_ / c.wallPersistenceHours));
  if (surf)
    r.condensation = 100 * (c.instantFraction * cr +
                            (1 - c.instantFraction) * clamp01(condDose_ / c.condensationHours));
  if (observe && v.valid && finite(v.probability))
    r.voc = 100 * clamp01(v.probability);
  // Weighted noisy-OR is a transparent SCREENING SCORE, not a Bayesian posterior.
  // Missing evidence is omitted without renormalizing remaining weights upward.
  float values[] = {r.environment, r.wall, r.condensation, r.voc};
  float weights[] = {c.environmentWeight, c.wallWeight, c.condensationWeight, c.vocWeight};
  float residual = 1;
  bool any = false;
  for (uint8_t i = 0; i < 4; i++)
    if (finite(values[i])) {
      any = true;
      float term = clamp01(weights[i]) * clamp01(values[i] / 100);
      r.contributions[i] = 100 * residual * term;
      residual *= 1 - term;
    }
  // Quality coverage budget: air 30, wall 40, measured surface 10, validated VOC 20.
  r.confidence = (air ? 30 : 0) + (wall ? 40 * clamp01(w.confidence / 100) : 0) + (surf ? 10 : 0) +
                 (finite(r.voc) ? 20 * clamp01(v.confidence / 100) : 0);
  r.valid = any && r.confidence >= c.minimumConfidence;
  r.degraded = r.confidence < 80;
  if (any)
    r.probability = 100 * (1 - residual);
  bool high = r.valid && r.probability >= c.highThreshold;
  if (high && prevHigh_ && !gap)
    highHours_ = fminf(c.maxExposureHours, highHours_ + h);
  else
    highHours_ = 0;
  if (high) {
    if (consecutive_ < UINT32_MAX)
      ++consecutive_;
  } else
    consecutive_ = 0;
  prevHigh_ = high;
  if (r.valid) {
    r.level = r.probability < c.elevatedThreshold ? RiskLevel::Low
              : r.probability < c.highThreshold   ? RiskLevel::Elevated
                                                  : RiskLevel::High;
    if (r.probability >= c.criticalThreshold && highHours_ >= c.criticalHoldHours)
      r.level = RiskLevel::Critical;
  }
  r.rhHours = rhHours_;
  r.wallHours = wallHours_;
  r.condensationHours = condHours_;
  r.elevatedHours = highHours_;
  r.condensationEvents = events_;
  r.consecutiveElevated = consecutive_;
  rhHistory_[historyIndex_] = air ? a.humidity : NAN;
  wallHistory_[historyIndex_] = wall ? w.index : NAN;
  condHistory_[historyIndex_] = r.condensation;
  scoreHistory_[historyIndex_] = r.valid ? r.probability : NAN;
  historyIndex_ = (historyIndex_ + 1) % cfg::rollingSamples;
  if (historyCount_ < cfg::rollingSamples)
    ++historyCount_;
  return r;
}
RollingMeans MoldRiskEngine::rolling() const {
  RollingMeans out;
  out.count = historyCount_;
  float *dest[] = {&out.rh, &out.wall, &out.condensation, &out.probability};
  const float *sources[] = {rhHistory_, wallHistory_, condHistory_, scoreHistory_};
  for (int j = 0; j < 4; j++) {
    float sum = 0;
    size_t n = 0;
    for (size_t i = 0; i < historyCount_; i++)
      if (finite(sources[j][i])) {
        sum += sources[j][i];
        ++n;
      }
    *dest[j] = n ? sum / n : NAN;
  }
  return out;
}
} // namespace ms
