#pragma once

#include <Arduino.h>
#include <bme68xLibrary.h>

#include "PersistentClock.h"
#include "SessionJournal.h"

class CaptureMode {
 public:
  bool begin(PersistentClock &clock, SessionJournal &journal, uint32_t bootId);
  void loop();
  bool start(String label);
  bool stop(const String &reason = "STOP");
  void printStatus() const;
  bool active() const;
  uint32_t rows() const { return rowCount_; }
  uint32_t cycles() const { return cycleIndex_; }
  float temperature() const { return temperature_; }
  float humidity() const { return humidity_; }
  float gas() const { return gas_; }

 private:
  Bme68x sensor_;
  PersistentClock *clock_ = nullptr;
  SessionJournal *journal_ = nullptr;
  uint32_t bootId_ = 0;
  uint32_t sensorId_ = 0;
  bool initialized_ = false;
  bool active_ = false;
  uint32_t captureId_ = 0;
  uint32_t rowCount_ = 0;
  uint32_t cycleIndex_ = 0;
  uint8_t lastGasIndex_ = 255;
  uint64_t startEpoch_ = 0;
  String startIso_ = "UNSET";
  String label_;
  String rowsPath_;
  String finalPath_;
  unsigned long lastPollMs_ = 0;
  float temperature_ = NAN;
  float humidity_ = NAN;
  float gas_ = NAN;

  void recoverInterruptedCapture();
  bool finalizeFile();
  uint32_t countRows() const;
  void saveCaptureMetadata(bool open);
  static String safeLabel(String label);
};
