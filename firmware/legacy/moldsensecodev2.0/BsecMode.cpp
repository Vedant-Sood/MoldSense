#include "BsecMode.h"

#include <LittleFS.h>
#include <Wire.h>

BsecMode *BsecMode::instance_ = nullptr;

bool BsecMode::begin(DeviceMode mode, PersistentClock &clock, SessionJournal &journal) {
  mode_ = mode;
  clock_ = &clock;
  journal_ = &journal;
  instance_ = this;

  if (!LittleFS.exists(MoldSenseConfig::LOG_FILE)) {
    File file = LittleFS.open(MoldSenseConfig::LOG_FILE, FILE_WRITE);
    if (!file) return false;
    file.println("iso_utc,unix_epoch,uptime_ms,session_id,mode,iaq,iaq_accuracy,temperature_c,humidity_percent,pressure_pa,gas_ohms,raw_gas_index,stabilization,run_in,model_accuracy,class_1,class_2,class_3,class_4");
    file.close();
  }

  if (!bsec_.begin(MoldSenseConfig::BME_ADDRESS, Wire)) {
    Serial.println("BSEC initialization failed.");
    checkStatus();
    return false;
  }

  if (mode_ == DeviceMode::TEST && !loadModel()) return false;
  loadState();

  bsecSensor logSensors[] = {
    BSEC_OUTPUT_IAQ,
    BSEC_OUTPUT_RAW_TEMPERATURE,
    BSEC_OUTPUT_RAW_PRESSURE,
    BSEC_OUTPUT_RAW_HUMIDITY,
    BSEC_OUTPUT_RAW_GAS,
    BSEC_OUTPUT_STABILIZATION_STATUS,
    BSEC_OUTPUT_RUN_IN_STATUS
  };
  bsecSensor testSensors[] = {
    BSEC_OUTPUT_RAW_TEMPERATURE,
    BSEC_OUTPUT_RAW_PRESSURE,
    BSEC_OUTPUT_RAW_HUMIDITY,
    BSEC_OUTPUT_RAW_GAS,
    BSEC_OUTPUT_RAW_GAS_INDEX,
    BSEC_OUTPUT_GAS_ESTIMATE_1,
    BSEC_OUTPUT_GAS_ESTIMATE_2,
    BSEC_OUTPUT_GAS_ESTIMATE_3,
    BSEC_OUTPUT_GAS_ESTIMATE_4
  };

  bsecSensor *sensors = mode_ == DeviceMode::TEST ? testSensors : logSensors;
  uint8_t sensorCount = mode_ == DeviceMode::TEST
    ? sizeof(testSensors) / sizeof(testSensors[0])
    : sizeof(logSensors) / sizeof(logSensors[0]);
  float rate = mode_ == DeviceMode::TEST ? BSEC_SAMPLE_RATE_SCAN : BSEC_SAMPLE_RATE_LP;
  if (!bsec_.updateSubscription(sensors, sensorCount, rate)) {
    checkStatus();
    // The Bosch Arduino wrapper returns false for both errors and
    // warnings. Positive statuses (for example 14, sample-rate mismatch)
    // still leave a usable subscription configured, so only negative
    // statuses are fatal here.
    if (bsec_.status < BSEC_OK) {
      Serial.println("BSEC subscription failed.");
      return false;
    }
    Serial.println("BSEC subscription accepted with warning; continuing at the configured rate.");
  }

  bsec_.attachCallback(callback);
  journal_->start(mode_, mode_ == DeviceMode::TEST ? "four_class_test" : "continuous_air_log", MoldSenseConfig::LOG_FILE);
  ready_ = true;
  Serial.print("BSEC ready, version ");
  Serial.print(bsec_.version.major); Serial.print('.');
  Serial.print(bsec_.version.minor); Serial.print('.');
  Serial.print(bsec_.version.major_bugfix); Serial.print('.');
  Serial.println(bsec_.version.minor_bugfix);
  return true;
}

void BsecMode::loop() {
  if (!ready_) return;
  if (!bsec_.run()) checkStatus();
  maybeSaveState();

  if (haveReading_ && millis() - lastLogMs_ >= MoldSenseConfig::LOG_INTERVAL_MS) {
    lastLogMs_ = millis();
    appendLog();
  }
}

bool BsecMode::saveState() {
  if (!ready_ || !bsec_.getState(state_)) {
    checkStatus();
    return false;
  }

  String finalPath = statePath();
  String tempPath = finalPath + ".tmp";
  LittleFS.remove(tempPath);
  File file = LittleFS.open(tempPath, FILE_WRITE);
  if (!file) return false;
  size_t written = file.write(state_, BSEC_MAX_STATE_BLOB_SIZE);
  file.close();
  if (written != BSEC_MAX_STATE_BLOB_SIZE) {
    LittleFS.remove(tempPath);
    return false;
  }

  if (LittleFS.exists(finalPath)) LittleFS.remove(finalPath);
  if (!LittleFS.rename(tempPath, finalPath)) return false;
  stateExists_ = true;
  lastStateSaveMs_ = millis();
  clock_->checkpoint();
  Serial.println("BSEC STATE SAVED.");
  return true;
}

void BsecMode::printStatus() const {
  Serial.print("bsec_ready="); Serial.println(ready_ ? "YES" : "NO");
  Serial.print("bsec_status="); Serial.println(bsec_.status);
  Serial.print("bme68x_status="); Serial.println(bsec_.sensor.status);
  Serial.print("state_file="); Serial.println(statePath());
  Serial.print("state_exists="); Serial.println(stateExists_ ? "YES" : "NO");
  Serial.print("iaq_accuracy="); Serial.println(iaqAccuracy_);
  Serial.print("model_accuracy="); Serial.println(modelAccuracy_);
  if (mode_ == DeviceMode::TEST) {
    for (uint8_t i = 0; i < 4; i++) {
      Serial.print("class_"); Serial.print(i + 1); Serial.print('=');
      if (isnan(classProbability_[i])) Serial.println("NA");
      else Serial.println(classProbability_[i], 6);
    }
  }
}

bool BsecMode::ready() const {
  return ready_;
}

void BsecMode::callback(const bme68xData, const bsecOutputs outputs, Bsec3) {
  if (instance_) instance_->onData(outputs);
}

void BsecMode::onData(const bsecOutputs &outputs) {
  for (uint8_t i = 0; i < outputs.nOutputs; i++) {
    const bsecData &output = outputs.output[i];
    switch (output.sensor_id) {
      case BSEC_OUTPUT_IAQ:
        iaq_ = output.signal;
        iaqAccuracy_ = output.accuracy;
        break;
      case BSEC_OUTPUT_RAW_TEMPERATURE: temperature_ = output.signal; break;
      case BSEC_OUTPUT_RAW_PRESSURE: pressure_ = output.signal; break;
      case BSEC_OUTPUT_RAW_HUMIDITY: humidity_ = output.signal; break;
      case BSEC_OUTPUT_RAW_GAS:
        gas_ = output.signal;
        haveReading_ = true;
        break;
      case BSEC_OUTPUT_RAW_GAS_INDEX: gasIndex_ = output.signal; break;
      case BSEC_OUTPUT_STABILIZATION_STATUS: stabilization_ = output.signal; break;
      case BSEC_OUTPUT_RUN_IN_STATUS: runIn_ = output.signal; break;
      case BSEC_OUTPUT_GAS_ESTIMATE_1:
      case BSEC_OUTPUT_GAS_ESTIMATE_2:
      case BSEC_OUTPUT_GAS_ESTIMATE_3:
      case BSEC_OUTPUT_GAS_ESTIMATE_4: {
        uint8_t index = output.sensor_id - BSEC_OUTPUT_GAS_ESTIMATE_1;
        classProbability_[index] = output.signal;
        modelAccuracy_ = output.accuracy;
        break;
      }
      default: break;
    }
  }

  Serial.print(mode_ == DeviceMode::TEST ? "TEST" : "LOG");
  Serial.print(" | gas="); Serial.print(gas_, 0);
  Serial.print(" | temp="); Serial.print(temperature_, 2);
  Serial.print(" | rh="); Serial.print(humidity_, 2);
  if (mode_ == DeviceMode::LOG) {
    Serial.print(" | iaq="); Serial.print(iaq_, 2);
    Serial.print(" | acc="); Serial.println(iaqAccuracy_);
  } else {
    Serial.print(" | model_acc="); Serial.print(modelAccuracy_);
    for (uint8_t i = 0; i < 4; i++) {
      Serial.print(" | C"); Serial.print(i + 1); Serial.print('=');
      if (isnan(classProbability_[i])) Serial.print("NA");
      else Serial.print(classProbability_[i] * 100.0f, 1);
    }
    Serial.println();
  }
}

void BsecMode::appendLog() {
  File file = LittleFS.open(MoldSenseConfig::LOG_FILE, FILE_APPEND);
  if (!file) return;
  file.print(clock_->iso8601()); file.print(',');
  file.print(clock_->now()); file.print(',');
  file.print(millis()); file.print(',');
  file.print(journal_->id()); file.print(',');
  file.print(mode_ == DeviceMode::TEST ? "TEST" : "LOG"); file.print(',');
  if (!isnan(iaq_)) file.print(iaq_, 3); file.print(',');
  file.print(iaqAccuracy_); file.print(',');
  if (!isnan(temperature_)) file.print(temperature_, 4); file.print(',');
  if (!isnan(humidity_)) file.print(humidity_, 4); file.print(',');
  if (!isnan(pressure_)) file.print(pressure_, 3); file.print(',');
  if (!isnan(gas_)) file.print(gas_, 3); file.print(',');
  if (!isnan(gasIndex_)) file.print(gasIndex_, 0); file.print(',');
  if (!isnan(stabilization_)) file.print(stabilization_, 0); file.print(',');
  if (!isnan(runIn_)) file.print(runIn_, 0); file.print(',');
  file.print(modelAccuracy_);
  for (uint8_t i = 0; i < 4; i++) {
    file.print(',');
    if (!isnan(classProbability_[i])) file.print(classProbability_[i], 6);
  }
  file.println();
  file.close();
  rows_++;
  journal_->checkpoint(rows_);
}

bool BsecMode::loadState() {
  const char *path = statePath();
  if (!LittleFS.exists(path)) return false;
  File file = LittleFS.open(path, FILE_READ);
  if (!file || file.size() != BSEC_MAX_STATE_BLOB_SIZE) {
    if (file) file.close();
    return false;
  }
  size_t read = file.read(state_, BSEC_MAX_STATE_BLOB_SIZE);
  file.close();
  if (read != BSEC_MAX_STATE_BLOB_SIZE || !bsec_.setState(state_)) {
    checkStatus();
    return false;
  }
  stateExists_ = true;
  lastStateSaveMs_ = millis();
  Serial.println("BSEC STATE RESTORED.");
  return true;
}

bool BsecMode::loadModel() {
  if (!LittleFS.exists(MoldSenseConfig::MODEL_FILE)) {
    Serial.println("TEST ERROR: /bsec_model.bin is missing.");
    return false;
  }
  File file = LittleFS.open(MoldSenseConfig::MODEL_FILE, FILE_READ);
  if (!file || file.size() == 0 || file.size() > BSEC_MAX_PROPERTY_BLOB_SIZE) {
    if (file) file.close();
    Serial.println("TEST ERROR: invalid model size.");
    return false;
  }
  memset(model_, 0, sizeof(model_));
  size_t size = file.size();
  size_t read = file.read(model_, size);
  file.close();
  if (read != size || !bsec_.setConfig(model_)) {
    Serial.println("TEST ERROR: BSEC rejected model; check BSEC version compatibility.");
    checkStatus();
    return false;
  }
  Serial.println("FOUR-CLASS MODEL LOADED.");
  return true;
}

void BsecMode::maybeSaveState() {
  int confidence = mode_ == DeviceMode::TEST ? modelAccuracy_ : iaqAccuracy_;
  if (!stateExists_) {
    if (confidence >= 2) saveState();
    return;
  }
  if (millis() - lastStateSaveMs_ >= MoldSenseConfig::STATE_SAVE_INTERVAL_MS) {
    if (confidence >= 2) saveState();
    else lastStateSaveMs_ = millis();
  }
}

void BsecMode::checkStatus() {
  if (bsec_.status < BSEC_OK) Serial.println("BSEC ERROR: " + String(bsec_.status));
  else if (bsec_.status > BSEC_OK) Serial.println("BSEC warning: " + String(bsec_.status));
  if (bsec_.sensor.status < BME68X_OK) Serial.println("BME68X ERROR: " + String(bsec_.sensor.status));
  else if (bsec_.sensor.status > BME68X_OK) Serial.println("BME68X warning: " + String(bsec_.sensor.status));
}

const char *BsecMode::statePath() const {
  return mode_ == DeviceMode::TEST
    ? MoldSenseConfig::TEST_STATE_FILE
    : MoldSenseConfig::LOG_STATE_FILE;
}
