#pragma once
#include "Types.h"
#include <algorithm>
namespace ms {
inline float dewPoint(float t, float rh) {
  if (!finite(t) || !finite(rh) || rh <= 0 || rh > 100 || t <= -100)
    return NAN;
  // Magnus over water (Alduchov/Eskridge approximation), screening precision only.
  float g = logf(rh / 100.f) + 17.625f * t / (243.04f + t);
  return 243.04f * g / (17.625f - g);
}
inline float surfaceRH(float t, float rh, float ts) {
  if (!finite(ts) || ts <= -100 || !finite(t) || !finite(rh) || rh <= 0 || rh > 100)
    return NAN;
  return fminf(100.f, rh * expf(17.625f * t / (243.04f + t) - 17.625f * ts / (243.04f + ts)));
}
inline float median(float *values, size_t n) {
  if (!n)
    return NAN;
  std::sort(values, values + n);
  return n % 2 ? values[n / 2] : (values[n / 2 - 1] + values[n / 2]) * .5f;
}
inline uint32_t crc32(const void *data, size_t n) {
  uint32_t crc = 0xffffffff;
  const uint8_t *p = static_cast<const uint8_t *>(data);
  while (n--) {
    crc ^= *p++;
    for (uint8_t i = 0; i < 8; i++)
      crc = (crc >> 1) ^ (0xedb88320U & uint32_t(-int32_t(crc & 1)));
  }
  return ~crc;
}
inline uint32_t wallIdentity() {
  const uint32_t fields[] = {cfg::wallSetupId, uint32_t(cfg::wallBackend),
                             uint32_t(cfg::wallBackend == cfg::WallBackend::AnalogVoltage
                                          ? WALL_ADC_PIN
                                          : WALL_TOUCH_PIN)};
  return crc32(fields, sizeof(fields));
}
} // namespace ms
