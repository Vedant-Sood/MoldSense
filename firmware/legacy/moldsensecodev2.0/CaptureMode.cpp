#include "CaptureMode.h"

#include <LittleFS.h>
#include <Preferences.h>
#include <Wire.h>

#include "MoldSenseConfig.h"

namespace {
constexpr uint8_t REQUIRED_DATA_STATUS =
  BME68X_GASM_VALID_MSK | BME68X_HEAT_STAB_MSK | BME68X_NEW_DATA_MSK;
}

bool CaptureMode::begin(PersistentClock &clock, SessionJournal &journal, uint32_t bootId) {
  clock_ = &clock;
  journal_ = &journal;
  bootId_ = bootId;

  sensor_.begin(MoldSenseConfig::BME_ADDRESS, Wire);
  if (sensor_.checkStatus() == BME68X_ERROR) {
    Serial.println("CAPTURE SENSOR ERROR: " + sensor_.statusString());
    return false;
  }

  sensor_.setTPH();
  uint16_t temperatures[MoldSenseConfig::HEATER_STEPS];
  uint16_t multipliers[MoldSenseConfig::HEATER_STEPS];
  memcpy(temperatures, MoldSenseConfig::HEATER_TEMPERATURES, sizeof(temperatures));
  memcpy(multipliers, MoldSenseConfig::HEATER_MULTIPLIERS, sizeof(multipliers));
  uint32_t tphMs = sensor_.getMeasDur(BME68X_PARALLEL_MODE) / 1000UL;
  uint16_t sharedDuration = MoldSenseConfig::CAPTURE_POLL_MS > tphMs
    ? MoldSenseConfig::CAPTURE_POLL_MS - tphMs
    : 1;
  sensor_.setHeaterProf(
    temperatures,
    multipliers,
    sharedDuration,
    MoldSenseConfig::HEATER_STEPS
  );
  sensor_.setOpMode(BME68X_PARALLEL_MODE);
  sensorId_ = sensor_.getUniqueId();
  initialized_ = true;

  recoverInterruptedCapture();
  Serial.print("CAPTURE READY | sensor_id=");
  Serial.println(sensorId_);
  return true;
}

void CaptureMode::loop() {
  if (!initialized_ || millis() - lastPollMs_ < MoldSenseConfig::CAPTURE_POLL_MS) return;
  lastPollMs_ = millis();
  if (!sensor_.fetchData()) return;

  bme68xData data{};
  uint8_t fieldsLeft = 0;
  do {
    fieldsLeft = sensor_.getData(data);
    if ((data.status & REQUIRED_DATA_STATUS) != REQUIRED_DATA_STATUS) continue;

    temperature_ = data.temperature;
    humidity_ = data.humidity;
    gas_ = data.gas_resistance;

    if (lastGasIndex_ != 255 && data.gas_index == 0 && lastGasIndex_ != 0) cycleIndex_++;
    lastGasIndex_ = data.gas_index;
    if (!active_) continue;

    File rows = LittleFS.open(rowsPath_, FILE_APPEND);
    if (!rows) {
      Serial.println("CAPTURE ERROR: cannot append raw row.");
      continue;
    }

    rows.print("[0,");
    rows.print(sensorId_); rows.print(',');
    rows.print(millis()); rows.print(',');
    rows.print(clock_->now()); rows.print(',');
    rows.print(data.temperature, 6); rows.print(',');
    rows.print(data.pressure / 100.0f, 6); rows.print(',');
    rows.print(data.humidity, 6); rows.print(',');
    rows.print(data.gas_resistance, 6); rows.print(',');
    rows.print(data.gas_index); rows.print(',');
    rows.print("true,");
    rows.print(cycleIndex_); rows.print(',');
    rows.print(1); rows.print(',');
    rows.println("0]");
    rows.close();

    rowCount_++;
    if ((rowCount_ % 100) == 0) {
      journal_->checkpoint(rowCount_);
      Serial.print("CAPTURE rows=");
      Serial.print(rowCount_);
      Serial.print(" cycles=");
      Serial.println(cycleIndex_);
    }
  } while (fieldsLeft);
}

bool CaptureMode::start(String label) {
  if (!initialized_ || active_) return false;
  label = safeLabel(label);
  if (label.length() == 0) {
    Serial.println("CAPTURE ERROR: label is required.");
    return false;
  }

  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  captureId_ = prefs.getUInt("captureCount", 0) + 1;
  prefs.putUInt("captureCount", captureId_);
  prefs.end();

  rowsPath_ = "/cap_" + String(captureId_) + ".rows";
  finalPath_ = "/cap_" + String(captureId_) + ".bmerawdata";
  label_ = label;
  startEpoch_ = clock_->now();
  startIso_ = clock_->iso8601();
  rowCount_ = 0;
  cycleIndex_ = 0;
  lastGasIndex_ = 255;

  File rows = LittleFS.open(rowsPath_, FILE_WRITE);
  if (!rows) return false;
  rows.close();

  active_ = true;
  saveCaptureMetadata(true);
  journal_->start(DeviceMode::CAPTURE, label_, finalPath_);
  Serial.print("CAPTURE STARTED: ");
  Serial.print(label_);
  Serial.print(" -> ");
  Serial.println(finalPath_);
  return true;
}

bool CaptureMode::stop(const String &reason) {
  if (!active_) return false;
  rowCount_ = countRows();
  bool finalized = finalizeFile();
  if (finalized) {
    LittleFS.remove(rowsPath_);
    saveCaptureMetadata(false);
    journal_->checkpoint(rowCount_);
    journal_->end(reason);
    active_ = false;
    Serial.print("CAPTURE SAVED: ");
    Serial.println(finalPath_);
  }
  return finalized;
}

void CaptureMode::printStatus() const {
  Serial.print("capture_active="); Serial.println(active_ ? "YES" : "NO");
  Serial.print("capture_id="); Serial.println(captureId_);
  Serial.print("label="); Serial.println(label_);
  Serial.print("rows="); Serial.println(rowCount_);
  Serial.print("cycles="); Serial.println(cycleIndex_);
  Serial.print("output="); Serial.println(finalPath_);
}

bool CaptureMode::active() const {
  return active_;
}

void CaptureMode::recoverInterruptedCapture() {
  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, true);
  bool wasOpen = prefs.getBool("capOpen", false);
  if (wasOpen) {
    captureId_ = prefs.getUInt("capId", 0);
    label_ = prefs.getString("capLabel", "recovered");
    rowsPath_ = prefs.getString("capRows", "");
    finalPath_ = prefs.getString("capFinal", "");
    startEpoch_ = prefs.getULong64("capStart", 0);
    startIso_ = prefs.getString("capStartIso", "UNSET");
  }
  prefs.end();

  if (!wasOpen || rowsPath_.length() == 0 || !LittleFS.exists(rowsPath_)) return;
  rowCount_ = countRows();
  if (finalizeFile()) {
    LittleFS.remove(rowsPath_);
    saveCaptureMetadata(false);
    Serial.print("Recovered interrupted capture: ");
    Serial.println(finalPath_);
  }
}

bool CaptureMode::finalizeFile() {
  File rows = LittleFS.open(rowsPath_, FILE_READ);
  if (!rows) return false;
  String tempPath = finalPath_ + ".tmp";
  LittleFS.remove(tempPath);
  File output = LittleFS.open(tempPath, FILE_WRITE);
  if (!output) {
    rows.close();
    return false;
  }

  output.print("{\"configHeader\":{");
  output.print("\"dateCreated_ISO\":\""); output.print(startIso_); output.print("\",");
  output.print("\"appVersion\":\""); output.print(MoldSenseConfig::FIRMWARE_VERSION); output.print("\",");
  output.print("\"boardType\":\"custom_board_1\",\"boardMode\":\"heater_profile_exploration\",\"boardLayout\":\"grouped\"},");
  output.print("\"configBody\":{\"heaterProfiles\":[{\"id\":\"");
  output.print(MoldSenseConfig::HEATER_PROFILE_ID);
  output.print("\",\"timeBase\":140,\"temperatureTimeVectors\":[[320,5],[100,2],[100,10],[100,30],[200,5],[200,5],[200,5],[320,5],[320,5],[320,5]]}],");
  output.print("\"dutyCycleProfiles\":[{\"id\":\"duty_1\",\"numberScanningCycles\":1,\"numberSleepingCycles\":0}],");
  output.print("\"sensorConfigurations\":[{\"sensorIndex\":0,\"heaterProfile\":\"heater_354\",\"dutyCycleProfile\":\"duty_1\"}]},");
  output.print("\"rawDataHeader\":{\"counterPowerOnOff\":"); output.print(bootId_);
  output.print(",\"seedPowerOnOff\":\"capture_"); output.print(captureId_); output.print("\",");
  output.print("\"counterFileLimit\":0,\"dateCreated\":\""); output.print(startEpoch_); output.print("\",");
  output.print("\"dateCreated_ISO\":\""); output.print(startIso_); output.print("\",");
  output.print("\"firmwareVersion\":\""); output.print(MoldSenseConfig::FIRMWARE_VERSION); output.print("\",");
  output.print("\"boardId\":\""); output.print(sensorId_, HEX); output.print("\"},");
  output.print("\"rawDataBody\":{\"dataColumns\":[");
  output.print("{\"name\":\"Sensor Index\",\"unit\":\"\",\"format\":\"integer\",\"key\":\"sensor_index\",\"colId\":1},");
  output.print("{\"name\":\"Sensor ID\",\"unit\":\"\",\"format\":\"integer\",\"key\":\"sensor_id\",\"colId\":2},");
  output.print("{\"name\":\"Time Since PowerOn\",\"unit\":\"Milliseconds\",\"format\":\"integer\",\"key\":\"timestamp_since_poweron\",\"colId\":3},");
  output.print("{\"name\":\"Real time clock\",\"unit\":\"Unix Timestamp: seconds since Jan 01 1970. (UTC); 0 = missing\",\"format\":\"integer\",\"key\":\"real_time_clock\",\"colId\":4},");
  output.print("{\"name\":\"Temperature\",\"unit\":\"DegreesCelcius\",\"format\":\"float\",\"key\":\"temperature\",\"colId\":5},");
  output.print("{\"name\":\"Pressure\",\"unit\":\"Hectopascals\",\"format\":\"float\",\"key\":\"pressure\",\"colId\":6},");
  output.print("{\"name\":\"Relative Humidity\",\"unit\":\"Percent\",\"format\":\"float\",\"key\":\"relative_humidity\",\"colId\":7},");
  output.print("{\"name\":\"Resistance Gassensor\",\"unit\":\"Ohms\",\"format\":\"float\",\"key\":\"resistance_gassensor\",\"colId\":8},");
  output.print("{\"name\":\"Heater Profile Step Index\",\"unit\":\"\",\"format\":\"integer\",\"key\":\"heater_profile_step_index\",\"colId\":9},");
  output.print("{\"name\":\"Scanning Mode Enabled\",\"unit\":\"\",\"format\":\"boolean\",\"key\":\"scanning_enabled\",\"colId\":10},");
  output.print("{\"name\":\"Scanning Cycle Index\",\"unit\":\"\",\"format\":\"integer\",\"key\":\"scanning_cycle_index\",\"colId\":11},");
  output.print("{\"name\":\"Label Tag\",\"unit\":\"\",\"format\":\"integer\",\"key\":\"label_tag\",\"colId\":12},");
  output.print("{\"name\":\"Error Code\",\"unit\":\"\",\"format\":\"integer\",\"key\":\"error_code\",\"colId\":13}],\"dataBlock\":[");

  bool first = true;
  while (rows.available()) {
    String line = rows.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;
    if (!first) output.print(',');
    output.print(line);
    first = false;
  }
  output.print("]}}\n");
  rows.close();
  output.close();

  if (!LittleFS.exists(tempPath)) return false;
  if (LittleFS.exists(finalPath_)) LittleFS.remove(finalPath_);
  return LittleFS.rename(tempPath, finalPath_);
}

uint32_t CaptureMode::countRows() const {
  File rows = LittleFS.open(rowsPath_, FILE_READ);
  if (!rows) return 0;
  uint32_t count = 0;
  while (rows.available()) if (rows.read() == '\n') count++;
  rows.close();
  return count;
}

void CaptureMode::saveCaptureMetadata(bool open) {
  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  prefs.putBool("capOpen", open);
  if (open) {
    prefs.putUInt("capId", captureId_);
    prefs.putString("capLabel", label_);
    prefs.putString("capRows", rowsPath_);
    prefs.putString("capFinal", finalPath_);
    prefs.putULong64("capStart", startEpoch_);
    prefs.putString("capStartIso", startIso_);
  }
  prefs.end();
}

String CaptureMode::safeLabel(String label) {
  label.trim();
  label.replace(',', '_');
  label.replace('"', '_');
  label.replace('\n', ' ');
  label.replace('\r', ' ');
  if (label.length() > 32) label.remove(32);
  return label;
}
