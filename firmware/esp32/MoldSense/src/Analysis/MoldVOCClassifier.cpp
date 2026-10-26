#include "MoldVOCClassifier.h"
namespace ms {
VocResult MoldVOCClassifier::evaluate(const AirReading &a, const ModelMetadata &m, bool accepted,
                                      uint32_t now) const {
  VocResult v;
  if (!m.installed)
    return v;
  v.status = "VOC MODEL: UNVALIDATED";
  if (!m.validated)
    return v;
  v.status = "VOC MODEL: REJECTED";
  if (!accepted || m.classCount < 2 || m.classCount > 4 || m.moldClass >= m.classCount ||
      !finite(m.validationQuality) || m.validationQuality <= 0 || m.validationQuality > 1)
    return v;
  v.modelValid = true;
  v.status = "VOC MODEL: WARMING";
  if (!a.valid || !a.gasValid || a.gasAccuracy == 0 || elapsed(now, a.gasMs, m.staleMs))
    return v;
  float sum = 0;
  for (uint8_t i = 0; i < m.classCount; i++) {
    if (!finite(a.classes[i]) || a.classes[i] < 0 || a.classes[i] > 1) {
      v.status = "VOC MODEL: BAD OUTPUT";
      return v;
    }
    sum += a.classes[i];
  }
  if (fabsf(sum - 1.f) > .05f) {
    v.status = "VOC MODEL: BAD OUTPUT";
    return v;
  }
  v.valid = true;
  v.probability = a.classes[m.moldClass];
  v.confidence = 100 * m.validationQuality * fminf(1.f, a.gasAccuracy / 3.f);
  v.status = "VOC MODEL: VALID";
  return v;
}
} // namespace ms
