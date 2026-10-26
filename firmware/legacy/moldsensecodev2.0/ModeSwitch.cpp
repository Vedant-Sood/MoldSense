#include "ModeSwitch.h"

void ModeSwitch::begin() {
  pinMode(MoldSenseConfig::LOG_SWITCH_PIN, INPUT_PULLUP);
  pinMode(MoldSenseConfig::INITIALIZE_SWITCH_PIN, INPUT_PULLUP);
  pinMode(MoldSenseConfig::TEST_SWITCH_PIN, INPUT_PULLUP);

  candidate_ = readCode();
  stable_ = candidate_;
  candidateSinceMs_ = millis();
}

uint8_t ModeSwitch::readCode() const {
  const bool logSelected = digitalRead(MoldSenseConfig::LOG_SWITCH_PIN) == LOW;
  const bool initializeSelected = digitalRead(MoldSenseConfig::INITIALIZE_SWITCH_PIN) == LOW;
  const bool testSelected = digitalRead(MoldSenseConfig::TEST_SWITCH_PIN) == LOW;
  const uint8_t selectedCount = logSelected + initializeSelected + testSelected;

  // "None selected" and "multiple selected" are both invalid. This avoids
  // changing mode while a physical switch is between positions.
  if (selectedCount != 1) return INVALID_SELECTION;
  if (logSelected) return static_cast<uint8_t>(DeviceMode::LOG);
  if (initializeSelected) return static_cast<uint8_t>(DeviceMode::CAPTURE);
  return static_cast<uint8_t>(DeviceMode::TEST);
}

bool ModeSwitch::read(DeviceMode &mode) const {
  const uint8_t code = readCode();
  if (code == INVALID_SELECTION) return false;
  mode = static_cast<DeviceMode>(code);
  return true;
}

bool ModeSwitch::changed(DeviceMode currentMode, DeviceMode &nextMode) {
  const uint8_t code = readCode();
  if (code != candidate_) {
    candidate_ = code;
    candidateSinceMs_ = millis();
    return false;
  }

  if (millis() - candidateSinceMs_ < MoldSenseConfig::MODE_SWITCH_DEBOUNCE_MS) return false;
  if (candidate_ == stable_) return false;

  stable_ = candidate_;
  if (stable_ == INVALID_SELECTION || stable_ == static_cast<uint8_t>(currentMode)) return false;
  nextMode = static_cast<DeviceMode>(stable_);
  return true;
}

String ModeSwitch::status() const {
  const uint8_t code = readCode();
  if (code == static_cast<uint8_t>(DeviceMode::LOG)) return "LOG";
  if (code == static_cast<uint8_t>(DeviceMode::CAPTURE)) return "INITIALIZE";
  if (code == static_cast<uint8_t>(DeviceMode::TEST)) return "TEST";
  return "INVALID";
}
