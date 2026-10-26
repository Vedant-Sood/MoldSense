#pragma once
#include <bsec3.h>
#include "../Core/Math.h"
#include "../Storage/StorageManager.h"
#include "../Analysis/MoldVOCClassifier.h"
namespace ms {
class BMEManager {
public:
  void begin(StorageManager &store, uint32_t now);
  void tick(uint32_t now);
  const AirReading &reading() const {
    return data_;
  }
  bool ready() const {
    return ready_;
  }
  bool modelAccepted() const {
    return modelAccepted_;
  }
  ModelMetadata metadata() const;
  const char *stateStatus() const {
    return stateStatus_;
  }
  uint32_t identity() const {
    return identity_;
  }
  uint32_t sensorId() const {
    return sensorId_;
  }
  const bsec_version_t &version() const {
    return bsec_.version;
  }

private:
  bool initialize(uint32_t now, bool allowModel = true);
  static void callback(const bme68xData, const bsecOutputs, const Bsec3 &);
  void receive(const bsecOutputs &, uint8_t heaterIndex);
  static BMEManager *instance_;
  Bsec3 bsec_;
  alignas(8) uint8_t memory_[BSEC_INSTANCE_SIZE]{};
  uint8_t state_[BSEC_MAX_STATE_BLOB_SIZE]{};
  StorageManager *store_ = nullptr;
  uint64_t observationCounter_ = 0;
  AirReading data_;
  uint32_t retryAt_ = 0, startedAt_ = 0, lastSave_ = 0, identity_ = 0, sensorId_ = 0;
  bool ready_ = false, modelAccepted_ = false, saved_ = false, saveFailed_ = false;
  const char *stateStatus_ = "NOT LOADED";
};
} // namespace ms
