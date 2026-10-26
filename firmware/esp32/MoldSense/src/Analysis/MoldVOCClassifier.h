#pragma once
#include "../Core/Types.h"
namespace ms {
struct ModelMetadata {
  bool installed = false, validated = false;
  uint8_t moldClass = 0, classCount = 0;
  float validationQuality = 0;
  uint32_t staleMs = 45000;
};
class MoldVOCClassifier {
public:
  VocResult evaluate(const AirReading &air, const ModelMetadata &model, bool accepted,
                     uint32_t now) const;
};
} // namespace ms
