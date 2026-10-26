#include <Arduino.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <Wire.h>
#include <bme68xLibrary.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

namespace Config {
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint8_t BME_ADDRESS_PRIMARY = 0x76;
constexpr uint8_t BME_ADDRESS_ALTERNATE = 0x77;
constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;
constexpr uint32_t POLL_MS = 140;
constexpr uint32_t OLED_REFRESH_MS = 500;
constexpr char PREFS[] = "bme_ai_once";
constexpr char FIRMWARE[] = "MoldSense-OneShot-AI-1.0";
constexpr uint16_t HEATER_TEMPERATURES[10] = {
  320, 100, 100, 100, 200, 200, 200, 320, 320, 320
};
constexpr uint16_t HEATER_MULTIPLIERS[10] = {
  5, 2, 10, 30, 5, 5, 5, 5, 5, 5
};
constexpr uint8_t HEATER_STEPS = 10;
}

constexpr uint8_t REQUIRED_DATA_STATUS =
  BME68X_GASM_VALID_MSK | BME68X_HEAT_STAB_MSK | BME68X_NEW_DATA_MSK;

Bme68x sensor;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
bool storageReady = false;
bool captureActive = false;
bool oledReady = false;
uint32_t captureId = 0;
uint32_t bootId = 0;
uint32_t sensorId = 0;
uint8_t bmeAddress = 0;
uint32_t rowCount = 0;
uint32_t cycleIndex = 0;
uint8_t lastGasIndex = 255;
unsigned long lastPollMs = 0;
unsigned long lastOledMs = 0;
float latestTemperature = NAN;
float latestHumidity = NAN;
float latestPressure = NAN;
float latestGas = NAN;
String captureLabel;
String rowsPath;
String finalPath;

void showOledMessage(const String &title, const String &line1 = "",
                     const String &line2 = "", const String &line3 = "") {
  if (!oledReady) return;
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.println(title);
  if (line1.length()) oled.println(line1);
  if (line2.length()) oled.println(line2);
  if (line3.length()) oled.println(line3);
  oled.display();
}

bool addressResponds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void printI2cScan() {
  Serial.print("I2C_SCAN_FOUND");
  uint8_t count = 0;
  for (uint8_t address = 1; address < 127; address++) {
    if (addressResponds(address)) {
      Serial.print(" 0x");
      if (address < 16) Serial.print('0');
      Serial.print(address, HEX);
      count++;
    }
  }
  if (!count) Serial.print(" NONE");
  Serial.println();
}

void beginOled() {
  uint8_t address = addressResponds(0x3C) ? 0x3C :
                    (addressResponds(0x3D) ? 0x3D : 0);
  if (address && oled.begin(SSD1306_SWITCHCAPVCC, address, false, false)) {
    oledReady = true;
    showOledMessage("MoldSense BME688", "Starting...");
  } else {
    Serial.println("OLED_NOT_FOUND: continuing with Serial Monitor.");
  }
}

void showLiveReadings() {
  if (!oledReady || millis() - lastOledMs < Config::OLED_REFRESH_MS) return;
  lastOledMs = millis();
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.println("READING BME688");
  oled.print("Rows: "); oled.println(rowCount);
  oled.print("T: "); oled.print(latestTemperature, 1); oled.println(" C");
  oled.print("RH: "); oled.print(latestHumidity, 1); oled.println(" %");
  oled.print("P: "); oled.print(latestPressure, 1); oled.println(" hPa");
  oled.print("Gas: "); oled.print(latestGas / 1000.0f, 1); oled.println(" kOhm");
  oled.display();
}

String safeLabel(String label) {
  label.trim();
  label.replace(',', '_');
  label.replace('"', '_');
  label.replace('\n', ' ');
  label.replace('\r', ' ');
  if (label.length() > 32) label.remove(32);
  return label;
}

uint32_t countRows(const String &path) {
  File rows = LittleFS.open(path, FILE_READ);
  if (!rows) return 0;
  uint32_t count = 0;
  while (rows.available()) if (rows.read() == '\n') count++;
  rows.close();
  return count;
}

void saveOpenCapture(bool open) {
  Preferences prefs;
  prefs.begin(Config::PREFS, false);
  prefs.putBool("capOpen", open);
  if (open) {
    prefs.putUInt("capId", captureId);
    prefs.putUInt("capBoot", bootId);
    prefs.putUInt("sensorId", sensorId);
    prefs.putString("capLabel", captureLabel);
    prefs.putString("capRows", rowsPath);
    prefs.putString("capFinal", finalPath);
  }
  prefs.end();
}

bool finalizeRows(const String &sourceRows, const String &targetFile,
                  uint32_t savedCaptureId, uint32_t savedBootId,
                  uint32_t savedSensorId) {
  if (!LittleFS.exists(sourceRows)) return false;
  File rows = LittleFS.open(sourceRows, FILE_READ);
  if (!rows) return false;

  String tempPath = targetFile + ".tmp";
  LittleFS.remove(tempPath);
  File output = LittleFS.open(tempPath, FILE_WRITE);
  if (!output) {
    rows.close();
    return false;
  }

  // This is the same HP-354, 13-column structure used by the earlier
  // MoldSense captures, with board_8 for direct BME AI-Studio import.
  output.print("{\"configHeader\":{");
  output.print("\"dateCreated_ISO\":\"UNSET\",");
  output.print("\"appVersion\":\""); output.print(Config::FIRMWARE); output.print("\",");
  output.print("\"boardType\":\"board_8\",\"boardMode\":\"heater_profile_exploration\",\"boardLayout\":\"grouped\"},");
  output.print("\"configBody\":{\"heaterProfiles\":[{\"id\":\"heater_354\",\"timeBase\":140,");
  output.print("\"temperatureTimeVectors\":[[320,5],[100,2],[100,10],[100,30],[200,5],[200,5],[200,5],[320,5],[320,5],[320,5]]}],");
  output.print("\"dutyCycleProfiles\":[{\"id\":\"duty_1\",\"numberScanningCycles\":1,\"numberSleepingCycles\":0}],");
  output.print("\"sensorConfigurations\":[{\"sensorIndex\":0,\"heaterProfile\":\"heater_354\",\"dutyCycleProfile\":\"duty_1\"}]},");
  output.print("\"rawDataHeader\":{\"counterPowerOnOff\":"); output.print(savedBootId);
  output.print(",\"seedPowerOnOff\":\"capture_"); output.print(savedCaptureId); output.print("\",");
  output.print("\"counterFileLimit\":0,\"dateCreated\":\"0\",\"dateCreated_ISO\":\"UNSET\",");
  output.print("\"firmwareVersion\":\""); output.print(Config::FIRMWARE); output.print("\",\"boardId\":\"");
  output.print(savedSensorId, HEX); output.print("\"},");
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

  if (LittleFS.exists(targetFile)) LittleFS.remove(targetFile);
  if (!LittleFS.rename(tempPath, targetFile)) return false;
  LittleFS.remove(sourceRows);
  return true;
}

bool recoverInterruptedCapture() {
  Preferences prefs;
  prefs.begin(Config::PREFS, true);
  bool wasOpen = prefs.getBool("capOpen", false);
  uint32_t oldCaptureId = prefs.getUInt("capId", 0);
  uint32_t oldBootId = prefs.getUInt("capBoot", 0);
  uint32_t oldSensorId = prefs.getUInt("sensorId", 0);
  String oldRows = prefs.getString("capRows", "");
  String oldFinal = prefs.getString("capFinal", "");
  prefs.end();

  if (!wasOpen) return false;
  uint32_t recoveredRows = countRows(oldRows);
  if (oldRows.length() && oldFinal.length() &&
      finalizeRows(oldRows, oldFinal, oldCaptureId, oldBootId, oldSensorId)) {
    Serial.print("READINGS_ENDED file=");
    Serial.print(oldFinal);
    Serial.print(" rows=");
    Serial.println(recoveredRows);
    saveOpenCapture(false);
    showOledMessage("READINGS ENDED", oldFinal, "Rows: " + String(recoveredRows), "System idle");
    return true;
  } else {
    Serial.println("RECOVERY_ERROR: raw rows were kept; do not format storage.");
    showOledMessage("RECOVERY ERROR", "Raw rows preserved", "Do not format");
    return false;
  }
}

bool beginSensor() {
  showOledMessage("WAITING FOR BME688", "Trying 0x76 / 0x77", "Up to 5 seconds");
  for (uint8_t attempt = 0; attempt < 50 && !bmeAddress; attempt++) {
    bmeAddress = addressResponds(Config::BME_ADDRESS_PRIMARY)
      ? Config::BME_ADDRESS_PRIMARY
      : (addressResponds(Config::BME_ADDRESS_ALTERNATE)
         ? Config::BME_ADDRESS_ALTERNATE : 0);
    if (!bmeAddress) delay(100);
  }
  if (!bmeAddress) {
    Serial.println("BME688_START_ERROR: no sensor found at 0x76 or 0x77.");
    printI2cScan();
    showOledMessage("BME688 NOT FOUND", "Check 3V3 and GND", "SDA21 / SCL22", "Tried 0x76, 0x77");
    return false;
  }
  Serial.print("BME688_FOUND address=0x");
  Serial.println(bmeAddress, HEX);
  sensor.begin(bmeAddress, Wire);
  if (sensor.checkStatus() == BME68X_ERROR) {
    Serial.print("BME688_START_ERROR: ");
    Serial.println(sensor.statusString());
    showOledMessage("BME688 ERROR", "Sensor responded", "Driver init failed", "See Serial Monitor");
    return false;
  }
  sensor.setTPH();
  uint16_t temperatures[Config::HEATER_STEPS];
  uint16_t multipliers[Config::HEATER_STEPS];
  memcpy(temperatures, Config::HEATER_TEMPERATURES, sizeof(temperatures));
  memcpy(multipliers, Config::HEATER_MULTIPLIERS, sizeof(multipliers));
  uint32_t tphMs = sensor.getMeasDur(BME68X_PARALLEL_MODE) / 1000UL;
  uint16_t sharedDuration = Config::POLL_MS > tphMs ? Config::POLL_MS - tphMs : 1;
  sensor.setHeaterProf(temperatures, multipliers, sharedDuration, Config::HEATER_STEPS);
  sensor.setOpMode(BME68X_PARALLEL_MODE);
  sensorId = sensor.getUniqueId();
  return true;
}

bool startArmedCapture(const String &label) {
  if (!beginSensor()) return false;
  Preferences prefs;
  prefs.begin(Config::PREFS, false);
  captureId = prefs.getUInt("capCount", 0) + 1;
  prefs.putUInt("capCount", captureId);
  prefs.end();

  captureLabel = safeLabel(label);
  rowsPath = "/cap_" + String(captureId) + ".rows";
  finalPath = "/cap_" + String(captureId) + ".bmerawdata";
  LittleFS.remove(rowsPath);
  File rows = LittleFS.open(rowsPath, FILE_WRITE);
  if (!rows) {
    Serial.println("CAPTURE_FILE_ERROR: could not create raw data file.");
    showOledMessage("STORAGE ERROR", "Cannot create", rowsPath);
    return false;
  }
  rows.close();
  rowCount = 0;
  cycleIndex = 0;
  lastGasIndex = 255;
  captureActive = true;
  saveOpenCapture(true);
  Serial.print("READINGS_STARTED file="); Serial.print(rowsPath);
  Serial.print(" label="); Serial.println(captureLabel);
  Serial.print("AI_CAPTURE_STARTED label="); Serial.print(captureLabel);
  Serial.print(" raw="); Serial.print(rowsPath);
  Serial.println(" | power off when the sample run is finished");
  showOledMessage("READINGS STARTED", captureLabel, rowsPath, "Collecting BME...");
  return true;
}

void captureLoop() {
  if (!captureActive || millis() - lastPollMs < Config::POLL_MS) return;
  lastPollMs = millis();
  if (!sensor.fetchData()) return;

  bme68xData data{};
  uint8_t fieldsLeft = 0;
  do {
    fieldsLeft = sensor.getData(data);
    if ((data.status & REQUIRED_DATA_STATUS) != REQUIRED_DATA_STATUS) continue;
    latestTemperature = data.temperature;
    latestHumidity = data.humidity;
    latestPressure = data.pressure / 100.0f;
    latestGas = data.gas_resistance;
    if (lastGasIndex != 255 && data.gas_index == 0 && lastGasIndex != 0) cycleIndex++;
    lastGasIndex = data.gas_index;

    File rows = LittleFS.open(rowsPath, FILE_APPEND);
    if (!rows) {
      Serial.println("CAPTURE_WRITE_ERROR");
      continue;
    }
    rows.print("[0,");
    rows.print(sensorId); rows.print(',');
    rows.print(millis()); rows.print(',');
    rows.print(0); rows.print(',');
    rows.print(data.temperature, 6); rows.print(',');
    rows.print(data.pressure / 100.0f, 6); rows.print(',');
    rows.print(data.humidity, 6); rows.print(',');
    rows.print(data.gas_resistance, 6); rows.print(',');
    rows.print(data.gas_index); rows.print(',');
    rows.print("true,");
    rows.print(cycleIndex); rows.print(',');
    rows.print(1); rows.print(',');
    rows.println("0]");
    rows.close();
    rowCount++;

    Serial.print("BME | row="); Serial.print(rowCount);
    Serial.print(" step="); Serial.print(data.gas_index);
    Serial.print(" temp_c="); Serial.print(data.temperature, 2);
    Serial.print(" rh="); Serial.print(data.humidity, 2);
    Serial.print(" pressure_hpa="); Serial.print(data.pressure / 100.0f, 2);
    Serial.print(" gas_ohms="); Serial.println(data.gas_resistance, 0);
    showLiveReadings();
  } while (fieldsLeft);
}

void listFiles() {
  File root = LittleFS.open("/", FILE_READ);
  File file = root.openNextFile();
  Serial.println("-----FILES_BEGIN-----");
  while (file) {
    Serial.print(file.name()); Serial.print(','); Serial.println(file.size());
    file = root.openNextFile();
  }
  Serial.println("-----FILES_END-----");
}

void dumpFile(const String &path) {
  if (!path.startsWith("/") || path.indexOf("..") >= 0 || !LittleFS.exists(path)) {
    Serial.println("FILE_NOT_FOUND");
    return;
  }
  File file = LittleFS.open(path, FILE_READ);
  Serial.println("-----FILE_BEGIN-----");
  while (file.available()) Serial.write(file.read());
  Serial.println();
  Serial.println("-----FILE_END-----");
  file.close();
}

void printHelp() {
  Serial.println("Commands:");
  Serial.println("  ARM_INITIALIZE <label>  (arms one capture for the next boot)");
  Serial.println("  ARM_STATUS | DISARM | STATUS");
  Serial.println("  STOP_FINALIZE  (optional clean stop without powering off)");
  Serial.println("  FILES | FILE_READ /cap_N.bmerawdata");
  Serial.println("  RESTART  (software reboot; useful after arming)");
  Serial.println("  FORMAT_STORAGE CONFIRM  (only if a blank filesystem cannot mount)");
}

void handleCommand(String command) {
  command.trim();
  if (!command.length()) return;
  if (command.startsWith("ARM_INITIALIZE ")) {
    if (captureActive) {
      Serial.println("ARM_ERROR: a capture is already running.");
      return;
    }
    String label = safeLabel(command.substring(15));
    if (!label.length()) {
      Serial.println("ARM_ERROR: label is required.");
      return;
    }
    Preferences prefs;
    prefs.begin(Config::PREFS, false);
    prefs.putString("armLabel", label);
    prefs.putBool("armed", true);
    prefs.end();
    Serial.print("ARMED_FOR_NEXT_BOOT label="); Serial.println(label);
    Serial.println("Power off now. The next power-on will capture once.");
    showOledMessage("ARMED NEXT BOOT", label, "Power off now");
  } else if (command == "ARM_STATUS") {
    Preferences prefs;
    prefs.begin(Config::PREFS, true);
    Serial.print("armed="); Serial.println(prefs.getBool("armed", false) ? "YES" : "NO");
    Serial.print("label="); Serial.println(prefs.getString("armLabel", ""));
    prefs.end();
  } else if (command == "DISARM") {
    Preferences prefs;
    prefs.begin(Config::PREFS, false);
    prefs.putBool("armed", false);
    prefs.end();
    Serial.println("DISARMED");
    showOledMessage("DISARMED", "System idle");
  } else if (command == "STATUS") {
    Serial.print("storage="); Serial.println(storageReady ? "READY" : "NOT_MOUNTED");
    Serial.print("capture_active="); Serial.println(captureActive ? "YES" : "NO");
    Serial.print("capture_id="); Serial.println(captureId);
    Serial.print("label="); Serial.println(captureLabel);
    Serial.print("rows="); Serial.println(rowCount);
  } else if (command == "STOP_FINALIZE") {
    if (!captureActive) {
      Serial.println("STOP_ERROR: no active capture.");
    } else if (finalizeRows(rowsPath, finalPath, captureId, bootId, sensorId)) {
      captureActive = false;
      saveOpenCapture(false);
      Serial.print("READINGS_ENDED file="); Serial.print(finalPath);
      Serial.print(" rows="); Serial.println(rowCount);
      showOledMessage("READINGS ENDED", finalPath, "Rows: " + String(rowCount), "System idle");
    } else {
      Serial.println("FINALIZE_ERROR: raw rows were kept.");
    }
  } else if (command == "FILES") {
    if (storageReady) listFiles(); else Serial.println("STORAGE_NOT_MOUNTED");
  } else if (command.startsWith("FILE_READ ")) {
    if (storageReady) dumpFile(command.substring(10)); else Serial.println("STORAGE_NOT_MOUNTED");
  } else if (command == "RESTART") {
    Serial.println("RESTARTING");
    Serial.flush();
    delay(100);
    ESP.restart();
  } else if (command == "FORMAT_STORAGE CONFIRM") {
    if (storageReady) {
      Serial.println("FORMAT_REFUSED: storage already mounts; preserve its files.");
    } else if (LittleFS.format()) {
      Serial.println("STORAGE_FORMATTED. Restart the board, then arm the capture.");
    } else {
      Serial.println("FORMAT_FAILED");
    }
  } else if (command == "HELP") {
    printHelp();
  } else {
    Serial.println("UNKNOWN_COMMAND. Type HELP.");
  }
}

void setup() {
  Serial.begin(Config::SERIAL_BAUD);
  Serial.setTimeout(1000);
  delay(500);
  Serial.println("\nMoldSense one-shot BME688 AI capture");
  Serial.println("DHT22 support: NOT INCLUDED");

  Wire.begin(Config::SDA_PIN, Config::SCL_PIN);
  beginOled();

  storageReady = LittleFS.begin(false);
  if (!storageReady) {
    Serial.println("STORAGE_NOT_MOUNTED: no data was erased.");
    Serial.println("For a truly blank board only, type FORMAT_STORAGE CONFIRM.");
    showOledMessage("STORAGE ERROR", "Nothing erased", "See Serial Monitor");
    printHelp();
    return;
  }

  Preferences prefs;
  prefs.begin(Config::PREFS, false);
  bootId = prefs.getUInt("bootId", 0) + 1;
  prefs.putUInt("bootId", bootId);
  prefs.end();

  // A power-off capture is intentionally completed on the next normal boot.
  bool recovered = recoverInterruptedCapture();

  prefs.begin(Config::PREFS, false);
  bool armed = prefs.getBool("armed", false);
  String armedLabel = prefs.getString("armLabel", "baseline");
  if (armed) prefs.putBool("armed", false);  // one-shot: consume before starting
  prefs.end();

  if (armed) {
    if (!startArmedCapture(armedLabel)) {
      Serial.println("CAPTURE_START_FAILED. Check BME688 power and I2C wiring.");
      // beginSensor() or the storage path has already placed the specific
      // failure on the OLED; do not leave the display saying Starting.
    }
  } else {
    Serial.println("IDLE: no capture armed. Type ARM_INITIALIZE <label>.");
    if (!recovered) showOledMessage("IDLE", "No capture armed", "Use Serial Monitor");
  }
  printHelp();
}

void loop() {
  captureLoop();
  if (Serial.available()) handleCommand(Serial.readStringUntil('\n'));
  delay(1);
}
