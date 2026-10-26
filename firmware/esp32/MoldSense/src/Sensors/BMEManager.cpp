#include "BMEManager.h"
#include "../Models/MoldModelConfig.h"
#include "../Models/DefaultIaqConfig.h"
namespace ms {
BMEManager *BMEManager::instance_ = nullptr;
ModelMetadata BMEManager::metadata() const {
  ModelMetadata m;
  m.installed = moldmodel::installed;
  m.validated = moldmodel::validated;
  m.moldClass = moldmodel::moldClass;
  m.classCount = moldmodel::classCount;
  m.validationQuality = moldmodel::validationQuality;
  m.staleMs = moldmodel::staleMs;
  return m;
}
void BMEManager::begin(StorageManager &store, uint32_t now) {
  store_ = &store;
  instance_ = this;
  bsec_.allocateMemory(memory_);
  startedAt_ = now;
  initialize(now);
}
bool BMEManager::initialize(uint32_t now, bool allowModel) {
  ready_ = false;
  modelAccepted_ = false;
  retryAt_ = now;
  data_ = AirReading{};
  Wire.beginTransmission(cfg::bmeAddress);
  if (Wire.endTransmission() != 0) {
    data_.bmeStatus = -2;
    return false;
  }
  if (!bsec_.begin(cfg::bmeAddress, Wire)) {
    data_.bsecStatus = bsec_.status;
    data_.bmeStatus = bsec_.sensor.status;
    return false;
  }
  sensorId_ = bsec_.sensor.getUniqueId();
  bool useModel = allowModel && moldmodel::installed && moldmodel::validated &&
                  moldmodel::classCount >= 2 && moldmodel::classCount <= 4 &&
                  moldmodel::moldClass < moldmodel::classCount;
  const uint8_t *config = useModel ? moldmodel::data : defaultIaqConfig;
  size_t size = useModel ? moldmodel::size : sizeof(defaultIaqConfig);
  if (size != BSEC_MAX_PROPERTY_BLOB_SIZE || !bsec_.setConfig(config)) {
    if (useModel)
      return initialize(now, false);
    data_.bsecStatus = bsec_.status;
    return false;
  }
  bsec_.setTemperatureOffset(cfg::bmeTemperatureOffset);
  // Bind learning state to bytes, BSEC version, physical sensor, and heat correction.
  uint32_t fields[] = {crc32(config, size), crc32(&bsec_.version, sizeof(bsec_.version)), sensorId_,
                       crc32(&cfg::bmeTemperatureOffset, sizeof(float)), uint32_t(useModel)};
  identity_ = crc32(fields, sizeof(fields));
  if (store_->loadBsec(state_, sizeof(state_), identity_)) {
    if (bsec_.setState(state_)) {
      stateStatus_ = "RESTORED";
    } else {
      stateStatus_ = "REJECTED BY BSEC";
      bsec_.begin(cfg::bmeAddress, Wire);
      if (!bsec_.setConfig(config))
        return false;
      bsec_.setTemperatureOffset(cfg::bmeTemperatureOffset);
    }
  } else
    stateStatus_ = store_->bsecLoadStatus;
  bsecSensor outputs[BSEC_NUMBER_OUTPUTS];
  uint8_t n = 0;
  outputs[n++] = BSEC_OUTPUT_RAW_TEMPERATURE;
  outputs[n++] = BSEC_OUTPUT_RAW_PRESSURE;
  outputs[n++] = BSEC_OUTPUT_RAW_HUMIDITY;
  outputs[n++] = BSEC_OUTPUT_RAW_GAS;
  outputs[n++] = BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_TEMPERATURE;
  outputs[n++] = BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_HUMIDITY;
  outputs[n++] = BSEC_OUTPUT_STABILIZATION_STATUS;
  outputs[n++] = BSEC_OUTPUT_RUN_IN_STATUS;
  if (useModel) {
    for (uint8_t i = 0; i < moldmodel::classCount; i++)
      outputs[n++] = bsecSensor(BSEC_OUTPUT_GAS_ESTIMATE_1 + i);
  } else {
    outputs[n++] = BSEC_OUTPUT_IAQ;
    outputs[n++] = BSEC_OUTPUT_STATIC_IAQ;
    outputs[n++] = BSEC_OUTPUT_CO2_EQUIVALENT;
    outputs[n++] = BSEC_OUTPUT_BREATH_VOC_EQUIVALENT;
  }
  bool subscription =
      bsec_.updateSubscription(outputs, n, useModel ? BSEC_SAMPLE_RATE_SCAN : BSEC_SAMPLE_RATE_LP);
  // Positive BSEC info (e.g. gas-estimate precedence) is not a hardware error.
  if (!subscription && bsec_.status < 0) {
    data_.bsecStatus = bsec_.status;
    if (useModel)
      return initialize(now, false);
    return false;
  }
  modelAccepted_ = useModel;
  ready_ = true;
  bsec_.attachCallback(callback);
  startedAt_ = now;
  lastSave_ = now;
  saved_ = false;
  return true;
}
void BMEManager::tick(uint32_t now) {
  if (!ready_) {
    if (elapsed(now, retryAt_, cfg::retryMs))
      initialize(now);
    return;
  }
  bsec_.run();
  data_.bsecStatus = bsec_.status;
  data_.bmeStatus = bsec_.sensor.status;
  if (bsec_.status < 0 || bsec_.sensor.status < 0) {
    ready_ = false;
    retryAt_ = now;
    data_.valid = false;
    data_.gasValid = false;
    data_.iaqValid = false;
    return;
  }
  if (data_.valid && elapsed(now, data_.sampleMs, cfg::bmeStaleMs)) {
    data_.valid = false;
    data_.gasValid = false;
    data_.iaqValid = false;
    ready_ = false;
    retryAt_ = now;
    return;
  }
  // Also retry if initialization succeeded but no first sample ever arrived.
  if (!data_.valid && elapsed(now, startedAt_, cfg::bmeStaleMs)) {
    ready_ = false;
    retryAt_ = now;
    return;
  }
  if (elapsed(now, data_.iaqMs, cfg::bmeStaleMs))
    data_.iaqValid = false;
  if (elapsed(now, data_.gasMs, moldmodel::staleMs))
    data_.gasValid = false;
  if (elapsed(now, data_.gasObservationMs, cfg::bmeStaleMs))
    data_.gasOhms = NAN;
  uint32_t interval = saveFailed_ ? cfg::bsecSaveRetryMs
                      : saved_    ? cfg::bsecSaveMs
                                  : cfg::bsecFirstSaveMs;
  bool calibrated = modelAccepted_ ? data_.gasValid && data_.gasAccuracy == 3
                                   : data_.iaqValid && data_.iaqAccuracy >= 1 && data_.runIn;
  if (calibrated && elapsed(now, lastSave_, interval)) {
    lastSave_ = now;
    saveFailed_ = !(bsec_.getState(state_) && store_->saveBsec(state_, sizeof(state_), identity_));
    if (!saveFailed_)
      saved_ = true;
    stateStatus_ = saveFailed_ ? "SAVE ERROR" : "SAVED / VERIFIED";
  }
}
void BMEManager::callback(const bme68xData raw, const bsecOutputs out, const Bsec3 &) {
  if (instance_) {
        instance_->receive(out, raw.gas_index);
  }
}
void BMEManager::receive(const bsecOutputs &out, uint8_t heaterIndex) {
  uint32_t now = millis();
  bool t = false, rh = false;
  uint8_t classMask = 0;
  float classes[4] = {NAN, NAN, NAN, NAN};
  uint8_t accuracy = 3;
  for (uint8_t i = 0; i < out.nOutputs && i < BSEC_NUMBER_OUTPUTS; i++) {
    const auto &o = out.output[i];
    float x = o.signal;
    if (!finite(x))
      continue;
    switch (o.sensor_id) {
    case BSEC_OUTPUT_RAW_TEMPERATURE:
      data_.rawTemperature = x;
      break;
    case BSEC_OUTPUT_RAW_HUMIDITY:
      data_.rawHumidity = x;
      break;
    case BSEC_OUTPUT_RAW_PRESSURE:
      data_.pressure = x;
      break;
    case BSEC_OUTPUT_RAW_GAS:
      data_.gasOhms = x > 0 ? x : NAN;
      if (x > 0) {
        data_.heaterIndex = heaterIndex;
        data_.gasObservationMs = now;
        data_.observationId = ++observationCounter_;
      }
      break;
    case BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_TEMPERATURE:
      data_.temperature = x;
      t = true;
      break;
    case BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_HUMIDITY:
      data_.humidity = x;
      rh = true;
      break;
    case BSEC_OUTPUT_IAQ:
      data_.iaq = x;
      data_.iaqAccuracy = o.accuracy;
      data_.iaqMs = now;
      data_.iaqValid = x >= 0 && x <= 500;
      break;
    case BSEC_OUTPUT_STATIC_IAQ:
      data_.staticIaq = x;
      break;
    case BSEC_OUTPUT_CO2_EQUIVALENT:
      data_.co2Equivalent = x;
      break;
    case BSEC_OUTPUT_BREATH_VOC_EQUIVALENT:
      data_.breathVocEquivalent = x;
      break;
    case BSEC_OUTPUT_STABILIZATION_STATUS:
      data_.stabilization = x > 0;
      break;
    case BSEC_OUTPUT_RUN_IN_STATUS:
      data_.runIn = x > 0;
      break;
    default:
      if (o.sensor_id >= BSEC_OUTPUT_GAS_ESTIMATE_1 && o.sensor_id <= BSEC_OUTPUT_GAS_ESTIMATE_4) {
        uint8_t index = o.sensor_id - BSEC_OUTPUT_GAS_ESTIMATE_1;
        classes[index] = x;
        classMask |= 1 << index;
        accuracy = std::min(accuracy, o.accuracy);
      }
      break;
    }
  }
  if (t && rh) {
    data_.sampleMs = now;
    data_.valid = data_.temperature >= cfg::minAirTemp && data_.temperature <= cfg::maxAirTemp &&
                  data_.humidity > 0 && data_.humidity <= 100 && finite(data_.pressure) &&
                  data_.pressure >= cfg::minPressurePa && data_.pressure <= cfg::maxPressurePa;
  }
  if (classMask) {
    data_.gasValid = classMask == ((1u << moldmodel::classCount) - 1);
    data_.gasMs = now;
    data_.gasAccuracy = accuracy;
    ++data_.gasSequence;
    for (uint8_t i = 0; i < 4; i++)
      data_.classes[i] = classes[i];
  }
}
} // namespace ms
