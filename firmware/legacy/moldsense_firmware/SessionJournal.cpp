#include "SessionJournal.h"

#include <LittleFS.h>
#include <Preferences.h>

bool SessionJournal::begin(PersistentClock &clock) {
  clock_ = &clock;

  if (!LittleFS.exists(MoldSenseConfig::SESSION_FILE)) {
    File file = LittleFS.open(MoldSenseConfig::SESSION_FILE, FILE_WRITE);
    if (!file) return false;
    file.println("event,session_id,mode,label,iso_utc,unix_epoch,uptime_ms,data_file,rows,clock_quality,reason");
    file.close();
  }

  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  bool previousOpen = prefs.getBool("sessionOpen", false);
  if (previousOpen) {
    id_ = prefs.getUInt("sessionId", 0);
    mode_ = static_cast<DeviceMode>(prefs.getUChar("sessionMode", 0));
    label_ = prefs.getString("sessionLabel", "unknown");
    dataFile_ = prefs.getString("sessionFile", "");
    rows_ = prefs.getUInt("sessionRows", 0);
    active_ = true;
    append("END", "POWER_LOSS_OR_RESET");
    active_ = false;
    prefs.putBool("sessionOpen", false);
  }
  prefs.end();
  return true;
}

uint32_t SessionJournal::start(DeviceMode mode, const String &label, const String &dataFile) {
  if (active_) end("REPLACED");

  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  id_ = prefs.getUInt("nextSession", 0) + 1;
  prefs.putUInt("nextSession", id_);
  mode_ = mode;
  label_ = safeCsv(label);
  dataFile_ = dataFile;
  rows_ = 0;
  active_ = true;
  prefs.putBool("sessionOpen", true);
  prefs.putUInt("sessionId", id_);
  prefs.putUChar("sessionMode", static_cast<uint8_t>(mode_));
  prefs.putString("sessionLabel", label_);
  prefs.putString("sessionFile", dataFile_);
  prefs.putUInt("sessionRows", rows_);
  prefs.end();

  append("START", "");
  checkpoint();
  return id_;
}

void SessionJournal::checkpoint(uint32_t rows) {
  if (!active_) return;
  if (rows > 0) rows_ = rows;
  clock_->checkpoint();

  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  prefs.putUInt("sessionRows", rows_);
  prefs.putULong64("sessionEpoch", clock_->now());
  prefs.end();
}

void SessionJournal::end(const String &reason) {
  if (!active_) return;
  checkpoint(rows_);
  append("END", reason);
  active_ = false;

  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  prefs.putBool("sessionOpen", false);
  prefs.end();
}

bool SessionJournal::active() const {
  return active_;
}

uint32_t SessionJournal::id() const {
  return id_;
}

void SessionJournal::append(const String &event, const String &reason) {
  File file = LittleFS.open(MoldSenseConfig::SESSION_FILE, FILE_APPEND);
  if (!file) return;
  file.print(event); file.print(',');
  file.print(id_); file.print(',');
  file.print(modeName(mode_)); file.print(',');
  file.print(label_); file.print(',');
  file.print(clock_->iso8601()); file.print(',');
  file.print(clock_->now()); file.print(',');
  file.print(millis()); file.print(',');
  file.print(dataFile_); file.print(',');
  file.print(rows_); file.print(',');
  file.print(clock_->quality()); file.print(',');
  file.println(safeCsv(reason));
  file.close();
}

String SessionJournal::modeName(DeviceMode mode) {
  switch (mode) {
    case DeviceMode::CAPTURE: return "CAPTURE";
    case DeviceMode::TEST: return "TEST";
    default: return "LOG";
  }
}

String SessionJournal::safeCsv(String value) {
  value.replace(',', '_');
  value.replace('\n', ' ');
  value.replace('\r', ' ');
  return value;
}
