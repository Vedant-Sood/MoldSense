#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <time.h>
#include <bsec2.h>

// =====================================================
// USER SETTINGS
// =====================================================

#define BME688_I2C_ADDR BME68X_I2C_ADDR_LOW

// New filename so your existing CSV is not destroyed.
// v2 keeps older logs intact while adding AI-model columns below.
#define LOG_FILE   "/bme688_sessions_v2.csv"
#define STATE_FILE "/bsec_state.bin"
#define STATE_TEMP "/bsec_state.tmp"
#define MODEL_FILE "/bsec_model.bin"
#define MODEL_TEMP "/bsec_model.tmp"
#define MODEL_STATE_FILE "/bsec_model_state.bin"
#define MODEL_STATE_TEMP "/bsec_model_state.tmp"

// Serial file uploads are deliberately capped.  This is enough for a BSEC
// configuration and prevents an accidental paste from filling LittleFS.
const size_t MAX_SERIAL_UPLOAD_BYTES = 256UL * 1024UL;

// Your Wi-Fi is only used briefly at startup to obtain time.
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// India = UTC + 5:30
const long GMT_OFFSET_SECONDS = 19800;
const int DAYLIGHT_OFFSET_SECONDS = 0;

// Record one CSV row every 60 seconds.
const unsigned long LOG_INTERVAL_MS =
  60UL * 1000UL;

// Once a good baseline exists, refresh it every 6 hours.
// Bosch's own example uses periodic state persistence rather
// than writing continuously.
const unsigned long STATE_SAVE_INTERVAL_MS =
  6UL * 60UL * 60UL * 1000UL;

// =====================================================
// BSEC
// =====================================================

Bsec2 envSensor;

uint8_t bsecState[BSEC_MAX_STATE_BLOB_SIZE];
uint8_t bsecModel[BSEC_MAX_PROPERTY_BLOB_SIZE];

bool storedStateExists = false;
bool modelRequested = false;
bool modelActive = false;

File uploadFile;
String uploadTarget;
String uploadTemp;
size_t uploadExpectedBytes = 0;
size_t uploadWrittenBytes = 0;
bool uploadInProgress = false;

unsigned long lastLogMs = 0;
unsigned long lastStateSaveMs = 0;

uint32_t bootID = 0;

// =====================================================
// TIME
// =====================================================

bool clockSynced = false;

// =====================================================
// LATEST SENSOR VALUES
// =====================================================

bool haveReading = false;

float latestIAQ = NAN;
int latestIAQAccuracy = -1;

float latestStaticIAQ = NAN;

float latestRawTemperature = NAN;
float latestRawPressure = NAN;
float latestRawHumidity = NAN;
float latestRawGas = NAN;

float latestCompTemperature = NAN;
float latestCompHumidity = NAN;

float latestCO2Equivalent = NAN;
float latestBreathVOC = NAN;

float latestGasPercentage = NAN;
float latestCompensatedGas = NAN;

float latestStabilization = NAN;
float latestRunIn = NAN;

float latestRawGasIndex = NAN;
float latestClassProbability[4] = {NAN, NAN, NAN, NAN};
int latestModelAccuracy = -1;

// =====================================================
// STATUS
// =====================================================

void checkBsecStatus(Bsec2& bsec) {

  if (bsec.status < BSEC_OK) {
    Serial.println(
      "BSEC ERROR: " + String(bsec.status)
    );
  }
  else if (bsec.status > BSEC_OK) {
    Serial.println(
      "BSEC warning: " + String(bsec.status)
    );
  }

  if (bsec.sensor.status < BME68X_OK) {
    Serial.println(
      "BME68X ERROR: " +
      String(bsec.sensor.status)
    );
  }
  else if (bsec.sensor.status > BME68X_OK) {
    Serial.println(
      "BME68X warning: " +
      String(bsec.sensor.status)
    );
  }
}

// =====================================================
// BOOT COUNTER
// =====================================================

void incrementBootID() {

  Preferences prefs;

  prefs.begin("bme688", false);

  bootID = prefs.getUInt("bootID", 0);
  bootID++;

  prefs.putUInt("bootID", bootID);

  prefs.end();

  Serial.print("Boot ID: ");
  Serial.println(bootID);
}

// =====================================================
// NTP / CLOCK
// =====================================================

bool syncClock() {

  if (strlen(WIFI_SSID) == 0 ||
      String(WIFI_SSID) == "YOUR_WIFI_NAME") {

    Serial.println(
      "WiFi not configured - timestamps will be UNSYNCED."
    );

    return false;
  }

  Serial.print("Connecting to WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - start < 20000
  ) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {

    Serial.println("WiFi connection failed.");

    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);

    return false;
  }

  Serial.println("WiFi connected. Syncing clock...");

  configTime(
    GMT_OFFSET_SECONDS,
    DAYLIGHT_OFFSET_SECONDS,
    "pool.ntp.org",
    "time.google.com",
    "time.cloudflare.com"
  );

  struct tm info;

  start = millis();

  while (millis() - start < 15000) {

    if (getLocalTime(&info, 1000)) {

      clockSynced = true;

      Serial.println("Clock synchronized.");

      WiFi.disconnect(true);
      WiFi.mode(WIFI_OFF);

      return true;
    }
  }

  Serial.println("NTP synchronization failed.");

  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);

  return false;
}

// =====================================================
// TIMESTAMP
// =====================================================

String getTimestamp() {

  if (!clockSynced) {
    return "UNSYNCED";
  }

  struct tm info;

  if (!getLocalTime(&info, 100)) {
    return "UNSYNCED";
  }

  char buf[32];

  snprintf(
    buf,
    sizeof(buf),
    "%04d-%02d-%02dT%02d:%02d:%02d+05:30",
    info.tm_year + 1900,
    info.tm_mon + 1,
    info.tm_mday,
    info.tm_hour,
    info.tm_min,
    info.tm_sec
  );

  return String(buf);
}

// =====================================================
// BSEC STATE FILE
// =====================================================

const char* activeStateFile() {
  return modelActive ? MODEL_STATE_FILE : STATE_FILE;
}

const char* activeStateTempFile() {
  return modelActive ? MODEL_STATE_TEMP : STATE_TEMP;
}

// A BSEC configuration exported by AI-Studio is stored as raw bytes in
// MODEL_FILE.  It is loaded before state restoration and before subscriptions.
// The configuration must match the BSEC version printed at boot.
bool loadRequestedModel() {
  Preferences prefs;
  prefs.begin("bme688", true);
  modelRequested = prefs.getBool("modelOn", false);
  prefs.end();

  if (!modelRequested) {
    return false;
  }

  if (!LittleFS.exists(MODEL_FILE)) {
    Serial.println("MODEL ERROR: selected model file is missing.");
    return false;
  }

  File file = LittleFS.open(MODEL_FILE, FILE_READ);
  if (!file || file.size() == 0 || file.size() > BSEC_MAX_PROPERTY_BLOB_SIZE) {
    Serial.println("MODEL ERROR: invalid model file size.");
    if (file) file.close();
    return false;
  }

  memset(bsecModel, 0, sizeof(bsecModel));
  size_t bytesRead = file.read(bsecModel, file.size());
  file.close();

  if (bytesRead == 0 || !envSensor.setConfig(bsecModel)) {
    Serial.println("MODEL ERROR: BSEC rejected the uploaded configuration.");
    checkBsecStatus(envSensor);
    return false;
  }

  modelActive = true;
  Serial.println("AI-STUDIO MODEL ACTIVE.");
  return true;
}

bool writeStateBlobToFile(
  const uint8_t* blob
) {

  File temp =
    LittleFS.open(activeStateTempFile(), FILE_WRITE);

  if (!temp) {
    Serial.println(
      "ERROR: Cannot create temporary BSEC state."
    );
    return false;
  }

  size_t written =
    temp.write(
      blob,
      BSEC_MAX_STATE_BLOB_SIZE
    );

  temp.close();

  if (written != BSEC_MAX_STATE_BLOB_SIZE) {

    Serial.println(
      "ERROR: Incomplete BSEC state write."
    );

    LittleFS.remove(activeStateTempFile());

    return false;
  }

  // Replace old state only after new state
  // has been successfully written.

  if (LittleFS.exists(activeStateFile())) {
    LittleFS.remove(activeStateFile());
  }

  if (!LittleFS.rename(
        activeStateTempFile(),
        activeStateFile()
      )) {

    Serial.println(
      "ERROR: Could not finalize state file."
    );

    return false;
  }

  storedStateExists = true;

  return true;
}

// =====================================================
// SAVE BSEC STATE
// =====================================================

bool saveBsecState() {

  if (!envSensor.getState(bsecState)) {

    Serial.println(
      "ERROR: BSEC getState() failed."
    );

    checkBsecStatus(envSensor);

    return false;
  }

  if (!writeStateBlobToFile(bsecState)) {
    return false;
  }

  lastStateSaveMs = millis();

  Serial.println();
  Serial.println(
    "================================="
  );
  Serial.println(
    "BSEC CALIBRATION STATE SAVED"
  );
  Serial.println(
    "================================="
  );

  return true;
}

// =====================================================
// LOAD BSEC STATE
// =====================================================

bool loadBsecState() {

  if (!LittleFS.exists(activeStateFile())) {

    Serial.println(
      "No permanent BSEC state found."
    );

    storedStateExists = false;

    return false;
  }

  File file =
    LittleFS.open(activeStateFile(), FILE_READ);

  if (!file) {

    Serial.println(
      "ERROR: Cannot open BSEC state."
    );

    return false;
  }

  if (
    file.size() != BSEC_MAX_STATE_BLOB_SIZE
  ) {

    Serial.println(
      "ERROR: Stored BSEC state has wrong size."
    );

    Serial.print("Expected: ");
    Serial.println(
      BSEC_MAX_STATE_BLOB_SIZE
    );

    Serial.print("Found: ");
    Serial.println(file.size());

    file.close();

    return false;
  }

  size_t bytesRead =
    file.read(
      bsecState,
      BSEC_MAX_STATE_BLOB_SIZE
    );

  file.close();

  if (
    bytesRead != BSEC_MAX_STATE_BLOB_SIZE
  ) {

    Serial.println(
      "ERROR: State file read incomplete."
    );

    return false;
  }

  if (!envSensor.setState(bsecState)) {

    Serial.println(
      "ERROR: BSEC rejected stored state."
    );

    checkBsecStatus(envSensor);

    Serial.println(
      "Possible BSEC version/config mismatch."
    );

    return false;
  }

  storedStateExists = true;
  lastStateSaveMs = millis();

  Serial.println();
  Serial.println(
    "================================="
  );
  Serial.println(
    "BSEC CALIBRATION STATE RESTORED"
  );
  Serial.println(
    "================================="
  );

  return true;
}

// =====================================================
// AUTOMATIC STATE MANAGEMENT
// =====================================================

void maybeSaveBsecState() {

  int confidence = modelActive ? latestModelAccuracy : latestIAQAccuracy;

  // No state exists yet:
  // wait for highest IAQ confidence.

  if (!storedStateExists) {

    if (confidence >= 3) {

      Serial.println(
        "Accuracy 3 reached."
      );

      Serial.println(
        "Creating first permanent baseline..."
      );

      saveBsecState();
    }

    return;
  }

  // State already exists.
  // Refresh periodically only when BSEC
  // has reasonable confidence.

  if (
    millis() - lastStateSaveMs >=
    STATE_SAVE_INTERVAL_MS
  ) {

    if (confidence >= 2) {

      Serial.println(
        "Refreshing BSEC state..."
      );

      saveBsecState();
    }
    else {

      Serial.println(
        "State refresh skipped: accuracy < 2."
      );

      lastStateSaveMs = millis();
    }
  }
}

// =====================================================
// CSV FILE
// =====================================================

void createLogFile() {

  File file =
    LittleFS.open(LOG_FILE, FILE_WRITE);

  if (!file) {

    Serial.println(
      "ERROR: Cannot create CSV."
    );

    return;
  }

  file.println(
    "timestamp,"
    "unix_epoch,"
    "boot_id,"
    "uptime_ms,"
    "iaq,"
    "iaq_accuracy,"
    "static_iaq,"
    "raw_temperature_c,"
    "raw_humidity_percent,"
    "raw_pressure_pa,"
    "raw_gas_ohms,"
    "comp_temperature_c,"
    "comp_humidity_percent,"
    "co2_equivalent_ppm,"
    "breath_voc_equivalent,"
    "gas_percentage,"
    "compensated_gas,"
    "stabilization_status,"
    "run_in_status"
    ",raw_gas_index"
    ",model_active"
    ",model_accuracy"
    ",class_1_probability"
    ",class_2_probability"
    ",class_3_probability"
    ",class_4_probability"
  );

  file.close();
}

// =====================================================
// CSV HELPER
// =====================================================

void printFloatOrBlank(
  File& file,
  float value,
  int decimals
) {

  if (!isnan(value)) {
    file.print(value, decimals);
  }
}

// =====================================================
// LOG MEASUREMENT
// =====================================================

void logCurrentReading() {

  if (!haveReading) {
    return;
  }

  File file =
    LittleFS.open(LOG_FILE, FILE_APPEND);

  if (!file) {

    Serial.println(
      "ERROR: Cannot append CSV."
    );

    return;
  }

  // Absolute timestamp
  file.print(getTimestamp());
  file.print(",");

  // Unix timestamp
  if (clockSynced) {
    file.print(
      (unsigned long)time(nullptr)
    );
  }

  file.print(",");

  // Unique power-cycle/session number
  file.print(bootID);
  file.print(",");

  file.print(millis());
  file.print(",");

  printFloatOrBlank(
    file,
    latestIAQ,
    2
  );
  file.print(",");

  file.print(latestIAQAccuracy);
  file.print(",");

  printFloatOrBlank(
    file,
    latestStaticIAQ,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestRawTemperature,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestRawHumidity,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestRawPressure,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestRawGas,
    0
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestCompTemperature,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestCompHumidity,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestCO2Equivalent,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestBreathVOC,
    3
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestGasPercentage,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestCompensatedGas,
    2
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestStabilization,
    0
  );
  file.print(",");

  printFloatOrBlank(
    file,
    latestRunIn,
    0
  );

  file.print(",");
  printFloatOrBlank(file, latestRawGasIndex, 0);
  file.print(",");
  file.print(modelActive ? 1 : 0);
  file.print(",");
  file.print(latestModelAccuracy);

  for (uint8_t i = 0; i < 4; i++) {
    file.print(",");
    printFloatOrBlank(file, latestClassProbability[i], 5);
  }

  file.println();
  file.close();

  Serial.print("[LOG] ");
  Serial.print(getTimestamp());

  Serial.print(" | IAQ=");
  Serial.print(latestIAQ, 2);

  Serial.print(" | Acc=");
  Serial.print(latestIAQAccuracy);

  Serial.print(" | Gas=");
  Serial.print(latestRawGas, 0);

  Serial.print(" | Stab=");
  Serial.print(latestStabilization, 0);

  Serial.print(" | RunIn=");
  Serial.println(latestRunIn, 0);
}

// =====================================================

void maybeLogCurrentReading() {

  if (
    millis() - lastLogMs >=
    LOG_INTERVAL_MS
  ) {

    lastLogMs = millis();

    logCurrentReading();
  }
}

// =====================================================
// CALLBACK
// =====================================================

void newDataCallback(
  const bme68xData data,
  const bsecOutputs outputs,
  Bsec2 bsec
) {

  if (!outputs.nOutputs) {
    return;
  }

  for (
    uint8_t i = 0;
    i < outputs.nOutputs;
    i++
  ) {

    const bsecData output =
      outputs.output[i];

    switch (output.sensor_id) {

      case BSEC_OUTPUT_IAQ:

        latestIAQ = output.signal;

        latestIAQAccuracy =
          output.accuracy;

        haveReading = true;

        break;


      case BSEC_OUTPUT_STATIC_IAQ:

        latestStaticIAQ =
          output.signal;

        break;


      case BSEC_OUTPUT_RAW_TEMPERATURE:

        latestRawTemperature =
          output.signal;

        break;


      case BSEC_OUTPUT_RAW_PRESSURE:

        latestRawPressure =
          output.signal;

        break;


      case BSEC_OUTPUT_RAW_HUMIDITY:

        latestRawHumidity =
          output.signal;

        break;


      case BSEC_OUTPUT_RAW_GAS:

        latestRawGas =
          output.signal;

        haveReading = true;

        break;


      case BSEC_OUTPUT_RAW_GAS_INDEX:

        latestRawGasIndex = output.signal;

        break;


      case BSEC_OUTPUT_GAS_ESTIMATE_1:
      case BSEC_OUTPUT_GAS_ESTIMATE_2:
      case BSEC_OUTPUT_GAS_ESTIMATE_3:
      case BSEC_OUTPUT_GAS_ESTIMATE_4: {

        uint8_t classIndex =
          output.sensor_id - BSEC_OUTPUT_GAS_ESTIMATE_1;

        latestClassProbability[classIndex] = output.signal;
        latestModelAccuracy = output.accuracy;

        break;
      }


      case
      BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_TEMPERATURE:

        latestCompTemperature =
          output.signal;

        break;


      case
      BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_HUMIDITY:

        latestCompHumidity =
          output.signal;

        break;


      case BSEC_OUTPUT_CO2_EQUIVALENT:

        latestCO2Equivalent =
          output.signal;

        break;


      case
      BSEC_OUTPUT_BREATH_VOC_EQUIVALENT:

        latestBreathVOC =
          output.signal;

        break;


      case BSEC_OUTPUT_GAS_PERCENTAGE:

        latestGasPercentage =
          output.signal;

        break;


      case BSEC_OUTPUT_COMPENSATED_GAS:

        latestCompensatedGas =
          output.signal;

        break;


      case
      BSEC_OUTPUT_STABILIZATION_STATUS:

        latestStabilization =
          output.signal;

        break;


      case BSEC_OUTPUT_RUN_IN_STATUS:

        latestRunIn =
          output.signal;

        break;
    }
  }

  Serial.print("IAQ: ");
  Serial.print(latestIAQ, 2);

  Serial.print(" | Acc: ");
  Serial.print(latestIAQAccuracy);

  Serial.print(" | Gas: ");
  Serial.print(latestRawGas, 0);

  Serial.print(" | Temp: ");
  Serial.print(latestCompTemperature, 2);

  Serial.print(" | RH: ");
  Serial.print(latestCompHumidity, 2);

  Serial.print(" | CO2eq: ");
  Serial.print(latestCO2Equivalent, 0);

  Serial.print(" | bVOC: ");
  Serial.print(latestBreathVOC, 3);

  Serial.print(" | Stab: ");
  Serial.print(latestStabilization, 0);

  Serial.print(" | RunIn: ");
  Serial.print(latestRunIn, 0);

  if (modelActive) {
    Serial.print(" | ModelAcc: ");
    Serial.print(latestModelAccuracy);
    for (uint8_t i = 0; i < 4; i++) {
      Serial.print(" | C");
      Serial.print(i + 1);
      Serial.print(": ");
      if (isnan(latestClassProbability[i])) Serial.print("-");
      else Serial.print(latestClassProbability[i] * 100.0f, 1);
    }
  }

  Serial.println();
}

// =====================================================
// DUMP CSV
// =====================================================

void dumpLog() {

  File file =
    LittleFS.open(LOG_FILE, FILE_READ);

  if (!file) {

    Serial.println("NO_LOG_FILE");

    return;
  }

  Serial.println(
    "-----BME688_LOG_BEGIN-----"
  );

  while (file.available()) {
    Serial.write(file.read());
  }

  Serial.println();

  Serial.println(
    "-----BME688_LOG_END-----"
  );

  file.close();
}

// =====================================================
// DUMP STATE AS HEX
// =====================================================

void dumpState() {

  if (!LittleFS.exists(activeStateFile())) {

    Serial.println("NO_BSEC_STATE");

    return;
  }

  File file =
    LittleFS.open(activeStateFile(), FILE_READ);

  if (!file) {
    return;
  }

  Serial.println(
    "-----BSEC_STATE_BEGIN-----"
  );

  while (file.available()) {

    uint8_t value = file.read();

    if (value < 16) {
      Serial.print("0");
    }

    Serial.print(value, HEX);
  }

  Serial.println();

  Serial.println(
    "-----BSEC_STATE_END-----"
  );

  file.close();
}

// =====================================================
// HEX IMPORT
// =====================================================

int hexValue(char c) {

  if (c >= '0' && c <= '9')
    return c - '0';

  if (c >= 'A' && c <= 'F')
    return c - 'A' + 10;

  if (c >= 'a' && c <= 'f')
    return c - 'a' + 10;

  return -1;
}

// =====================================================

void importState(String hex) {

  hex.trim();
  hex.replace(" ", "");

  const size_t expected =
    BSEC_MAX_STATE_BLOB_SIZE * 2;

  if (hex.length() != expected) {

    Serial.print(
      "ERROR: Expected "
    );

    Serial.print(expected);

    Serial.print(
      " hex characters, received "
    );

    Serial.println(hex.length());

    return;
  }

  uint8_t imported[
    BSEC_MAX_STATE_BLOB_SIZE
  ];

  for (
    size_t i = 0;
    i < BSEC_MAX_STATE_BLOB_SIZE;
    i++
  ) {

    int high =
      hexValue(hex[i * 2]);

    int low =
      hexValue(hex[i * 2 + 1]);

    if (high < 0 || low < 0) {

      Serial.println(
        "ERROR: Invalid hexadecimal data."
      );

      return;
    }

    imported[i] =
      (high << 4) | low;
  }

  // Let BSEC validate the blob before
  // permanently saving it.

  if (!envSensor.setState(imported)) {

    Serial.println(
      "ERROR: BSEC rejected imported state."
    );

    checkBsecStatus(envSensor);

    return;
  }

  if (!writeStateBlobToFile(imported)) {

    Serial.println(
      "ERROR: Could not save imported state."
    );

    return;
  }

  memcpy(
    bsecState,
    imported,
    BSEC_MAX_STATE_BLOB_SIZE
  );

  storedStateExists = true;

  Serial.println();
  Serial.println(
    "BSEC STATE IMPORTED AND APPLIED."
  );
}

// =====================================================
// SERIAL FILE STORE
// =====================================================

bool isAllowedUserFile(String path) {
  if (!path.startsWith("/") || path.indexOf("..") >= 0 || path.indexOf("//") >= 0) {
    return false;
  }

  // BSEC state blobs are written only by BSEC validation code.
  return path != STATE_FILE && path != STATE_TEMP &&
         path != MODEL_STATE_FILE && path != MODEL_STATE_TEMP;
}

void listFiles() {
  File root = LittleFS.open("/", FILE_READ);
  File file = root.openNextFile();

  Serial.println("-----FILES_BEGIN-----");
  while (file) {
    Serial.print(file.name());
    Serial.print(",");
    Serial.println(file.size());
    file = root.openNextFile();
  }
  Serial.println("-----FILES_END-----");
}

void dumpFileHex(String path) {
  if (!LittleFS.exists(path)) {
    Serial.println("FILE_NOT_FOUND");
    return;
  }

  File file = LittleFS.open(path, FILE_READ);
  if (!file) {
    Serial.println("FILE_OPEN_FAILED");
    return;
  }

  Serial.println("-----FILE_HEX_BEGIN-----");
  while (file.available()) {
    uint8_t value = file.read();
    if (value < 16) Serial.print("0");
    Serial.print(value, HEX);
  }
  Serial.println();
  Serial.println("-----FILE_HEX_END-----");
  file.close();
}

void beginFileUpload(String args) {
  int split = args.lastIndexOf(' ');
  if (split <= 1) {
    Serial.println("UPLOAD_ERROR: use FILE_UPLOAD_BEGIN /name bytes");
    return;
  }

  String path = args.substring(0, split);
  path.trim();
  size_t expected = (size_t)strtoul(args.substring(split + 1).c_str(), nullptr, 10);

  if (!isAllowedUserFile(path) || expected == 0 || expected > MAX_SERIAL_UPLOAD_BYTES) {
    Serial.println("UPLOAD_ERROR: invalid path or byte count.");
    return;
  }

  if (path == MODEL_FILE && expected > BSEC_MAX_PROPERTY_BLOB_SIZE) {
    Serial.println("UPLOAD_ERROR: model is larger than BSEC_MAX_PROPERTY_BLOB_SIZE.");
    return;
  }

  if (uploadInProgress) {
    uploadFile.close();
    LittleFS.remove(uploadTemp);
  }

  uploadTarget = path;
  uploadTemp = path + ".uploading";
  uploadExpectedBytes = expected;
  uploadWrittenBytes = 0;
  LittleFS.remove(uploadTemp);
  uploadFile = LittleFS.open(uploadTemp, FILE_WRITE);

  if (!uploadFile) {
    Serial.println("UPLOAD_ERROR: cannot create temporary file.");
    return;
  }

  uploadInProgress = true;
  Serial.println("UPLOAD_READY");
}

void appendUploadHex(String hex) {
  if (!uploadInProgress) {
    Serial.println("UPLOAD_ERROR: no upload is active.");
    return;
  }

  hex.trim();
  hex.replace(" ", "");
  if (hex.length() == 0 || (hex.length() % 2) != 0 || hex.length() > 512) {
    Serial.println("UPLOAD_ERROR: chunk must be 2-512 hex characters.");
    return;
  }

  size_t bytes = hex.length() / 2;
  if (uploadWrittenBytes + bytes > uploadExpectedBytes) {
    Serial.println("UPLOAD_ERROR: chunk exceeds declared size.");
    return;
  }

  uint8_t decoded[256];
  for (size_t i = 0; i < bytes; i++) {
    int high = hexValue(hex[i * 2]);
    int low = hexValue(hex[i * 2 + 1]);
    if (high < 0 || low < 0) {
      Serial.println("UPLOAD_ERROR: non-hex character.");
      return;
    }
    decoded[i] = (high << 4) | low;
  }

  if (uploadFile.write(decoded, bytes) != bytes) {
    Serial.println("UPLOAD_ERROR: write failed.");
    return;
  }

  uploadWrittenBytes += bytes;
  Serial.print("UPLOAD_PROGRESS ");
  Serial.print(uploadWrittenBytes);
  Serial.print("/");
  Serial.println(uploadExpectedBytes);
}

void endFileUpload() {
  if (!uploadInProgress) {
    Serial.println("UPLOAD_ERROR: no upload is active.");
    return;
  }

  uploadFile.close();
  uploadInProgress = false;
  if (uploadWrittenBytes != uploadExpectedBytes) {
    LittleFS.remove(uploadTemp);
    Serial.println("UPLOAD_ERROR: incomplete upload discarded.");
    return;
  }

  if (LittleFS.exists(uploadTarget)) LittleFS.remove(uploadTarget);
  if (!LittleFS.rename(uploadTemp, uploadTarget)) {
    Serial.println("UPLOAD_ERROR: could not finalize file.");
    return;
  }

  Serial.print("UPLOAD_SAVED ");
  Serial.println(uploadTarget);
}

void setModelEnabled(bool enabled) {
  if (enabled) {
    File model = LittleFS.open(MODEL_FILE, FILE_READ);
    bool usable = model && model.size() > 0 && model.size() <= BSEC_MAX_PROPERTY_BLOB_SIZE;
    if (model) model.close();
    if (!usable) {
      Serial.println("MODEL_ERROR: upload a valid /bsec_model.bin first.");
      return;
    }
  }

  Preferences prefs;
  prefs.begin("bme688", false);
  prefs.putBool("modelOn", enabled);
  prefs.end();

  Serial.println(enabled ? "MODEL_SELECTED_RESTART_REQUIRED" : "MODEL_DISABLED_RESTART_REQUIRED");
}

// =====================================================
// SERIAL COMMANDS
// =====================================================

void handleSerialCommands() {

  if (!Serial.available()) {
    return;
  }

  String cmd =
    Serial.readStringUntil('\n');

  cmd.trim();

  if (cmd.length() == 0) {
    return;
  }

  if (cmd == "DUMP") {

    dumpLog();
  }

  else if (cmd == "DUMP_STATE") {

    dumpState();
  }

  else if (cmd == "SAVE_STATE") {

    if (latestIAQAccuracy >= 2) {

      saveBsecState();
    }
    else {

      Serial.println(
        "Refusing SAVE_STATE because "
        "accuracy is below 2."
      );
    }
  }

  else if (
    cmd.startsWith("IMPORT_STATE ")
  ) {

    String hex =
      cmd.substring(13);

    importState(hex);
  }

  else if (cmd == "STATE_INFO") {

    Serial.print("State file exists: ");
    Serial.println(
      LittleFS.exists(activeStateFile())
      ? "YES"
      : "NO"
    );

    Serial.print(
      "BSEC state bytes required: "
    );

    Serial.println(
      BSEC_MAX_STATE_BLOB_SIZE
    );

    Serial.print("Current confidence: ");
    Serial.println(modelActive ? latestModelAccuracy : latestIAQAccuracy);
  }

  else if (cmd == "SIZE") {

    File file =
      LittleFS.open(
        LOG_FILE,
        FILE_READ
      );

    if (file) {

      Serial.print(
        "LOG_SIZE_BYTES="
      );

      Serial.println(
        file.size()
      );

      file.close();
    }
  }

  else if (cmd == "CLEAR_LOG") {

    LittleFS.remove(LOG_FILE);
    createLogFile();

    Serial.println(
      "LOG CLEARED."
    );
  }

  else if (cmd == "CLEAR_STATE") {

    LittleFS.remove(activeStateFile());

    storedStateExists = false;

    Serial.println(
      "BSEC STATE DELETED."
    );
  }

  else if (cmd == "FILES") {

    listFiles();
  }

  else if (cmd.startsWith("FILE_DUMP ")) {

    dumpFileHex(cmd.substring(10));
  }

  else if (cmd.startsWith("FILE_DELETE ")) {

    String path = cmd.substring(12);
    path.trim();
    if (!isAllowedUserFile(path)) {
      Serial.println("FILE_DELETE_ERROR: protected or invalid path.");
    }
    else if (LittleFS.remove(path)) {
      Serial.println("FILE_DELETED");
    }
    else {
      Serial.println("FILE_DELETE_ERROR: file not found or delete failed.");
    }
  }

  else if (cmd.startsWith("FILE_UPLOAD_BEGIN ")) {

    beginFileUpload(cmd.substring(18));
  }

  else if (cmd.startsWith("FILE_UPLOAD_HEX ")) {

    appendUploadHex(cmd.substring(16));
  }

  else if (cmd == "FILE_UPLOAD_END") {

    endFileUpload();
  }

  else if (cmd == "FILE_UPLOAD_ABORT") {

    if (uploadInProgress) {
      uploadFile.close();
      LittleFS.remove(uploadTemp);
      uploadInProgress = false;
    }
    Serial.println("UPLOAD_ABORTED");
  }

  else if (cmd == "MODEL_ENABLE") {

    setModelEnabled(true);
  }

  else if (cmd == "MODEL_DISABLE") {

    setModelEnabled(false);
  }

  else if (cmd == "MODEL_INFO") {

    Serial.print("Model selected: ");
    Serial.println(modelRequested ? "YES" : "NO");
    Serial.print("Model active this boot: ");
    Serial.println(modelActive ? "YES" : "NO");
    Serial.print("Model file bytes: ");
    File model = LittleFS.open(MODEL_FILE, FILE_READ);
    Serial.println(model ? model.size() : 0);
    if (model) model.close();
  }

  else if (cmd == "HELP") {

    Serial.println();
    Serial.println("Commands:");

    Serial.println(
      "DUMP"
    );

    Serial.println(
      "DUMP_STATE"
    );

    Serial.println(
      "STATE_INFO"
    );

    Serial.println(
      "SAVE_STATE"
    );

    Serial.println(
      "IMPORT_STATE <hex>"
    );

    Serial.println(
      "SIZE"
    );

    Serial.println(
      "CLEAR_LOG"
    );

    Serial.println(
      "CLEAR_STATE"
    );

    Serial.println("FILES");
    Serial.println("FILE_DUMP /name");
    Serial.println("FILE_DELETE /name");
    Serial.println("FILE_UPLOAD_BEGIN /name bytes");
    Serial.println("FILE_UPLOAD_HEX hexbytes");
    Serial.println("FILE_UPLOAD_END");
    Serial.println("FILE_UPLOAD_ABORT");
    Serial.println("MODEL_ENABLE");
    Serial.println("MODEL_DISABLE");
    Serial.println("MODEL_INFO");
  }

  else {

    Serial.println(
      "Unknown command. Type HELP."
    );
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);
  delay(2000);

  Serial.println();
  Serial.println(
    "=================================="
  );
  Serial.println(
    "BME688 PERMANENT LOGGER STARTING"
  );
  Serial.println(
    "=================================="
  );

  Wire.begin();

  // ---------- LittleFS ----------

  if (!LittleFS.begin(true)) {

    Serial.println(
      "FATAL: LittleFS failed."
    );

    return;
  }

  incrementBootID();

  if (!LittleFS.exists(LOG_FILE)) {

    createLogFile();

    Serial.println(
      "Created permanent CSV."
    );
  }
  else {

    Serial.println(
      "Existing CSV found. Appending."
    );
  }

  // ---------- Real time ----------

  syncClock();

  Serial.print(
    "Current timestamp: "
  );

  Serial.println(
    getTimestamp()
  );

  // ---------- BSEC ----------

  if (!envSensor.begin(
        BME688_I2C_ADDR,
        Wire
      )) {

    Serial.println(
      "BSEC initialization failed."
    );

    checkBsecStatus(envSensor);

    return;
  }

  // A selected AI-Studio configuration changes the heater profile and must be
  // applied before its matching BSEC state is restored.
  loadRequestedModel();

  // Load the matching baseline BEFORE starting normal use.
  loadBsecState();

  // Bosch's standard generic BSEC output set.
  bsecSensor standardSensorList[] = {

    BSEC_OUTPUT_IAQ,

    BSEC_OUTPUT_RAW_TEMPERATURE,
    BSEC_OUTPUT_RAW_PRESSURE,
    BSEC_OUTPUT_RAW_HUMIDITY,
    BSEC_OUTPUT_RAW_GAS,

    BSEC_OUTPUT_STABILIZATION_STATUS,
    BSEC_OUTPUT_RUN_IN_STATUS,

    BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_TEMPERATURE,
    BSEC_OUTPUT_SENSOR_HEAT_COMPENSATED_HUMIDITY,

    BSEC_OUTPUT_STATIC_IAQ,

    BSEC_OUTPUT_CO2_EQUIVALENT,
    BSEC_OUTPUT_BREATH_VOC_EQUIVALENT,

    BSEC_OUTPUT_GAS_PERCENTAGE,
    BSEC_OUTPUT_COMPENSATED_GAS
  };

  // A trained AI-Studio classifier returns up to four class probabilities.
  // The class names stay on the PC with the AI-Studio project; map Class 1-4
  // in your documentation to the labels used during training.
  bsecSensor modelSensorList[] = {
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

  bsecSensor* sensorList = modelActive ? modelSensorList : standardSensorList;
  uint8_t sensorCount = modelActive
    ? sizeof(modelSensorList) / sizeof(modelSensorList[0])
    : sizeof(standardSensorList) / sizeof(standardSensorList[0]);
  float sampleRate = modelActive ? BSEC_SAMPLE_RATE_SCAN : BSEC_SAMPLE_RATE_LP;

  if (!envSensor.updateSubscription(
        sensorList,
        sensorCount,
        sampleRate
      )) {

    Serial.println(
      "BSEC subscription warning/error:"
    );

    checkBsecStatus(envSensor);
  }

  envSensor.attachCallback(
    newDataCallback
  );

  Serial.println();
  Serial.print(
    "BSEC version: "
  );

  Serial.print(
    envSensor.version.major
  );
  Serial.print(".");

  Serial.print(
    envSensor.version.minor
  );
  Serial.print(".");

  Serial.print(
    envSensor.version.major_bugfix
  );
  Serial.print(".");

  Serial.println(
    envSensor.version.minor_bugfix
  );

  Serial.println(
    "Logger ready."
  );

  Serial.println(
    "Type HELP for commands."
  );
}

// =====================================================
// LOOP
// =====================================================

void loop() {

  if (!envSensor.run()) {

    checkBsecStatus(envSensor);
  }

  maybeLogCurrentReading();

  maybeSaveBsecState();

  handleSerialCommands();
}
