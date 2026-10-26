#pragma once

#include <Arduino.h>
#include <bsec3.h>

#include "MoldSenseConfig.h"
#include "PersistentClock.h"
#include "SessionJournal.h"

class BsecMode {
 public:
  bool begin(DeviceMode mode, PersistentClock &clock, SessionJournal &journal);
  void loop();
  bool saveState();
  void printStatus() const;
  bool ready() const;
  float temperature() const { return temperature_; }
  float humidity() const { return humidity_; }
  float gas() const { return gas_; }
  float iaq() const { return iaq_; }
  int iaqAccuracy() const { return iaqAccuracy_; }
  int modelAccuracy() const { return modelAccuracy_; }
  float classProbability(uint8_t index) const {
    return index < 4 ? classProbability_[index] : NAN;
  }

 private:
  static BsecMode *instance_;
  static void callback(const bme68xData data, const bsecOutputs outputs, Bsec3 bsec);
  void onData(const bsecOutputs &outputs);
  void appendLog();
  bool loadState();
  bool loadModel();
  void maybeSaveState();
  void checkStatus();
  const char *statePath() const;

  Bsec3 bsec_;
  DeviceMode mode_ = DeviceMode::LOG;
  PersistentClock *clock_ = nullptr;
  SessionJournal *journal_ = nullptr;
  bool ready_ = false;
  bool stateExists_ = false;
  bool haveReading_ = false;
  unsigned long lastLogMs_ = 0;
  unsigned long lastStateSaveMs_ = 0;
  uint32_t rows_ = 0;

  float iaq_ = NAN;
  int iaqAccuracy_ = -1;
  float temperature_ = NAN;
  float humidity_ = NAN;
  float pressure_ = NAN;
  float gas_ = NAN;
  float gasIndex_ = NAN;
  float classProbability_[4] = {NAN, NAN, NAN, NAN};
  int modelAccuracy_ = -1;
  float stabilization_ = NAN;
  float runIn_ = NAN;
  uint8_t state_[BSEC_MAX_STATE_BLOB_SIZE]{};
  uint8_t model_[BSEC_MAX_PROPERTY_BLOB_SIZE]{};
};
