#include <Arduino.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <Wire.h>

#include "BsecMode.h"
#include "CaptureMode.h"
#include "Dht22Verifier.h"
#include "MoldSenseConfig.h"
#include "OledDisplay.h"
#include "PersistentClock.h"
#include "SerialFileStore.h"
#include "SessionJournal.h"

PersistentClock deviceClock;
SessionJournal sessionJournal;
CaptureMode captureMode;
BsecMode bsecMode;
SerialFileStore fileStore;
OledDisplay oled;
Dht22Verifier dht22;

DeviceMode currentMode = DeviceMode::LOG;
uint32_t bootId = 0;

String modeName(DeviceMode mode) {
  switch (mode) {
    case DeviceMode::CAPTURE: return "CAPTURE";
    case DeviceMode::TEST: return "TEST";
    default: return "LOG";
  }
}

float currentBmeTemperature() {
  return currentMode == DeviceMode::CAPTURE
    ? captureMode.temperature()
    : bsecMode.temperature();
}

float currentBmeHumidity() {
  return currentMode == DeviceMode::CAPTURE
    ? captureMode.humidity()
    : bsecMode.humidity();
}

bool parseMode(String value, DeviceMode &mode) {
  value.trim();
  value.toUpperCase();
  if (value == "LOG") mode = DeviceMode::LOG;
  else if (value == "CAPTURE") mode = DeviceMode::CAPTURE;
  else if (value == "TEST") mode = DeviceMode::TEST;
  else return false;
  return true;
}

void persistMode(DeviceMode mode) {
  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  prefs.putUChar("mode", static_cast<uint8_t>(mode));
  prefs.end();
}

void switchMode(DeviceMode next) {
  if (next == currentMode) {
    Serial.println("MODE already active.");
    return;
  }

  if (currentMode == DeviceMode::CAPTURE && captureMode.active()) {
    if (!captureMode.stop("MODE_CHANGE")) {
      Serial.println("MODE ERROR: active capture could not be finalized.");
      return;
    }
  } else if (sessionJournal.active()) {
    if (bsecMode.ready()) bsecMode.saveState();
    sessionJournal.end("MODE_CHANGE");
  }

  deviceClock.checkpoint();
  persistMode(next);
  Serial.print("MODE SAVED: ");
  Serial.print(modeName(next));
  Serial.println(". Restarting...");
  delay(250);
  ESP.restart();
}

void printHelp() {
  Serial.println("Commands:");
  Serial.println("  MODE | MODE LOG | MODE CAPTURE | MODE TEST");
  Serial.println("  STATUS");
  Serial.println("  CLOCK_SET <unix_epoch_utc> | CLOCK_INFO");
  Serial.println("  CAPTURE_START <label> | CAPTURE_STOP | CAPTURE_STATUS");
  Serial.println("  SAVE_STATE | BSEC_STATUS | DHT_STATUS | MODEL_INFO");
  Serial.println("  FILES | FILE_READ /path | FILE_DUMP /path");
  Serial.println("  FILE_DELETE /user_name");
  Serial.println("  FILE_UPLOAD_BEGIN /name bytes");
  Serial.println("  FILE_UPLOAD_HEX <hex> | FILE_UPLOAD_END | FILE_UPLOAD_ABORT");
  Serial.println("  HELP | RESTART");
  Serial.println("Writable upload targets: /bsec_model.bin and /user_* files.");
}

void printStatus() {
  Serial.print("mode="); Serial.println(modeName(currentMode));
  Serial.print("boot_id="); Serial.println(bootId);
  Serial.print("clock="); Serial.println(deviceClock.iso8601());
  Serial.print("clock_quality="); Serial.println(deviceClock.quality());
  Serial.print("session_active="); Serial.println(sessionJournal.active() ? "YES" : "NO");
  Serial.print("session_id="); Serial.println(sessionJournal.id());
  if (currentMode == DeviceMode::CAPTURE) captureMode.printStatus();
  else bsecMode.printStatus();
  dht22.printStatus(currentBmeTemperature(), currentBmeHumidity());
}

void handleCommand(String command) {
  command.trim();
  if (command.length() == 0) return;

  if (command == "HELP") {
    printHelp();
  } else if (command == "MODE") {
    Serial.println(modeName(currentMode));
  } else if (command.startsWith("MODE ")) {
    DeviceMode next;
    if (!parseMode(command.substring(5), next)) Serial.println("MODE ERROR: use LOG, CAPTURE, or TEST.");
    else switchMode(next);
  } else if (command == "STATUS") {
    printStatus();
  } else if (command == "CLOCK_INFO") {
    Serial.print("clock="); Serial.println(deviceClock.iso8601());
    Serial.print("unix_epoch="); Serial.println(deviceClock.now());
    Serial.print("quality="); Serial.println(deviceClock.quality());
  } else if (command.startsWith("CLOCK_SET ")) {
    if (currentMode == DeviceMode::CAPTURE && captureMode.active()) {
      Serial.println("CLOCK ERROR: stop capture before changing time.");
    } else {
      uint64_t epoch = strtoull(command.substring(10).c_str(), nullptr, 10);
      Serial.println(deviceClock.setUnixTime(epoch) ? "CLOCK SET." : "CLOCK ERROR: invalid epoch.");
    }
  } else if (command.startsWith("CAPTURE_START ")) {
    if (currentMode != DeviceMode::CAPTURE) Serial.println("CAPTURE ERROR: switch to MODE CAPTURE first.");
    else captureMode.start(command.substring(14));
  } else if (command == "CAPTURE_STOP") {
    if (currentMode != DeviceMode::CAPTURE || !captureMode.stop()) Serial.println("CAPTURE ERROR: no active capture or finalization failed.");
  } else if (command == "CAPTURE_STATUS") {
    if (currentMode == DeviceMode::CAPTURE) captureMode.printStatus();
    else Serial.println("CAPTURE mode is not active.");
  } else if (command == "SAVE_STATE") {
    if (currentMode == DeviceMode::CAPTURE) Serial.println("STATE ERROR: BSEC is not running in CAPTURE mode.");
    else if (!bsecMode.saveState()) Serial.println("STATE ERROR: save failed.");
  } else if (command == "BSEC_STATUS") {
    if (currentMode == DeviceMode::CAPTURE) Serial.println("BSEC is not running in CAPTURE mode.");
    else bsecMode.printStatus();
  } else if (command == "DHT_STATUS") {
    dht22.printStatus(currentBmeTemperature(), currentBmeHumidity());
  } else if (command == "MODEL_INFO") {
    File model = LittleFS.open(MoldSenseConfig::MODEL_FILE, FILE_READ);
    Serial.print("model_file="); Serial.println(model ? MoldSenseConfig::MODEL_FILE : "MISSING");
    Serial.print("model_bytes="); Serial.println(model ? model.size() : 0);
    Serial.print("maximum_bytes="); Serial.println(BSEC_MAX_PROPERTY_BLOB_SIZE);
    if (model) model.close();
  } else if (command == "RESTART") {
    if (currentMode == DeviceMode::CAPTURE && captureMode.active()) captureMode.stop("RESTART_COMMAND");
    else if (sessionJournal.active()) sessionJournal.end("RESTART_COMMAND");
    deviceClock.checkpoint();
    delay(200);
    ESP.restart();
  } else if (!fileStore.handle(command)) {
    Serial.println("UNKNOWN COMMAND. Type HELP.");
  }
}

void setup() {
  Serial.begin(MoldSenseConfig::SERIAL_BAUD);
  Serial.setTimeout(1000);
  delay(500);
  Wire.begin();
  dht22.begin();
  if (!oled.begin(Wire)) Serial.println("OLED not found at 0x3C or 0x3D; continuing without display.");

  Serial.println();
  Serial.println("========================================");
  Serial.println("MoldSense three-mode firmware starting");
  Serial.println("========================================");

  // Never auto-format: preservation is more important than silently erasing
  // states, captures, and model files after a mount problem.
  if (!LittleFS.begin(false)) {
    Serial.println("FATAL: LittleFS mount failed; storage was NOT formatted.");
    return;
  }

  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  bootId = prefs.getUInt("bootId", 0) + 1;
  prefs.putUInt("bootId", bootId);
  uint8_t savedMode = prefs.getUChar("mode", static_cast<uint8_t>(DeviceMode::LOG));
  prefs.end();
  if (savedMode > static_cast<uint8_t>(DeviceMode::TEST)) savedMode = 0;
  currentMode = static_cast<DeviceMode>(savedMode);

  deviceClock.begin();
  if (!sessionJournal.begin(deviceClock)) {
    Serial.println("FATAL: session journal could not be opened.");
    return;
  }

  Serial.print("Mode: "); Serial.println(modeName(currentMode));
  Serial.print("Clock: "); Serial.print(deviceClock.iso8601());
  Serial.print(" ("); Serial.print(deviceClock.quality()); Serial.println(')');
  oled.showBoot(modeName(currentMode), "Starting sensor...");

  bool initialized = currentMode == DeviceMode::CAPTURE
    ? captureMode.begin(deviceClock, sessionJournal, bootId)
    : bsecMode.begin(currentMode, deviceClock, sessionJournal);
  if (!initialized) Serial.println("MODE INITIALIZATION FAILED; command interface remains available.");
  else oled.showBoot(modeName(currentMode), "Sensor ready");
  printHelp();
}

void loop() {
  if (currentMode == DeviceMode::CAPTURE) captureMode.loop();
  else bsecMode.loop();
  dht22.loop(currentBmeTemperature(), currentBmeHumidity());
  oled.update(currentMode, bsecMode, captureMode);

  if (Serial.available()) {
    handleCommand(Serial.readStringUntil('\n'));
  }
  delay(1);
}
