#include "BaselineManager.h"
namespace ms {
bool BaselineManager::start(uint32_t now) {
  if (active_)
    return false;
  start_ = last_ = now;
  count_ = 0;
  active_ = true;
  ready_ = false;
  status_ = "CALIBRATING";
  return true;
}
uint8_t BaselineManager::progress(uint32_t now) const {
  return uint8_t(fminf(100.f, 100.f * uint32_t(now - start_) / cfg::baselineDurationMs));
}
void BaselineManager::tick(uint32_t now, const WallReading &w, const AirReading &a) {
  if (!active_)
    return;
  if (elapsed(now, last_, cfg::baselineSampleMs)) {
    last_ = now;
    if (count_ < cfg::baselineCapacity && w.valid && finite(w.filtered) && a.valid &&
        finite(a.temperature) && finite(a.humidity) &&
        !elapsed(now, w.sampleMs, cfg::wallStaleMs) && !elapsed(now, a.sampleMs, cfg::bmeStaleMs))
      samples_[count_++] = {w.filtered, a.temperature, a.humidity};
  }
  if (elapsed(now, start_, cfg::baselineDurationMs))
    finish();
}
void BaselineManager::finish() {
  active_ = false;
  status_ = "UNSTABLE / INSUFFICIENT";
  const size_t required =
      size_t((cfg::baselineDurationMs / cfg::baselineSampleMs) * cfg::baselineMinCoverage);
  if (count_ < required || count_ < 3)
    return;
  for (size_t i = 0; i < count_; i++)
    work_[i] = samples_[i].wall;
  float med = median(work_, count_);
  for (size_t i = 0; i < count_; i++)
    work_[i] = fabsf(samples_[i].wall - med);
  float mad = median(work_, count_);
  float cutoff = fmaxf(cfg::noiseFloor, 3.f * 1.4826f * mad);
  double sum = 0, sum2 = 0;
  float ts = 0, rs = 0, tmin = INFINITY, tmax = -INFINITY, rmin = INFINITY, rmax = -INFINITY,
        first = 0, second = 0;
  size_t n = 0, n1 = 0, n2 = 0;
  for (size_t i = 0; i < count_; i++) {
    const auto &s = samples_[i];
    if (fabsf(s.wall - med) > cutoff)
      continue;
    work_[n++] = s.wall;
    sum += s.wall;
    sum2 += double(s.wall) * s.wall;
    ts += s.t;
    rs += s.rh;
    tmin = fminf(tmin, s.t);
    tmax = fmaxf(tmax, s.t);
    rmin = fminf(rmin, s.rh);
    rmax = fmaxf(rmax, s.rh);
    if (i < count_ / 2) {
      first += s.wall;
      ++n1;
    } else {
      second += s.wall;
      ++n2;
    }
  }
  if (n < required || n < 3 || !n1 || !n2)
    return;
  float mean = sum / n, sd = sqrtf(fmaxf(0.f, (sum2 - sum * sum / n) / (n - 1)));
  float drift = fabsf(first / n1 - second / n2) / fmaxf(mean, 1.f);
  if (mean <= cfg::wallRawMin || mean >= cfg::wallRawMax || sd / mean > cfg::baselineMaxCV ||
      drift > cfg::baselineMaxDrift || tmax - tmin > cfg::baselineMaxTempRange ||
      rmax - rmin > cfg::baselineMaxRhRange)
    return;
  result_ = Baseline{};
  result_.setupId = wallIdentity();
  result_.count = n;
  result_.total = count_;
  result_.mean = mean;
  result_.median = median(work_, n);
  result_.stddev = sd;
  result_.temperature = ts / n;
  result_.humidity = rs / n;
  result_.dewPoint = dewPoint(result_.temperature, result_.humidity);
  result_.confidence = 100 * clamp01(float(n) / (cfg::baselineDurationMs / cfg::baselineSampleMs)) *
                       (1 - .5f * clamp01(sd / mean / cfg::baselineMaxCV));
  ready_ = true;
  status_ = "READY TO SAVE";
}
Baseline BaselineManager::statistics() const {
  Baseline b;
  b.count = b.total = count_;
  if (!count_)
    return b;
  float values[cfg::baselineCapacity];
  double sum = 0, sum2 = 0;
  for (size_t i = 0; i < count_; i++) {
    float x = samples_[i].wall;
    values[i] = x;
    sum += x;
    sum2 += double(x) * x;
  }
  b.mean = sum / count_;
  b.median = median(values, count_);
  b.stddev = count_ > 1 ? sqrt(fmax(0.0, (sum2 - sum * sum / count_) / (count_ - 1))) : 0;
  return b;
}
bool BaselineManager::takeResult(Baseline &b) {
  if (!ready_)
    return false;
  b = result_;
  ready_ = false;
  return true;
}
} // namespace ms
