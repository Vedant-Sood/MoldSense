#include "App.h"
#include "../Config.h"
#include "Core/Switches.h"
#include "Sensors/BMEManager.h"
#include "Sensors/WallMoisture.h"
#include "Calibration/BaselineManager.h"
#include "Analysis/MoldRiskEngine.h"
#include "UI/OLEDUI.h"
#include "UI/Console.h"
#include "UI/ResearchProtocol.h"
#include "Models/MoldModelConfig.h"
#include <esp_system.h>
#include <string.h>
using namespace ms;
namespace {
StorageManager store;
BMEManager bme;
WallMoisture wall;
BaselineManager calibration;
MoldRiskEngine riskEngine;
MoldVOCClassifier classifier;
OLEDUI oled;
Console console;
ResearchProtocol protocol;
uint32_t streamInterval = cfg::telemetryDefaultMs, lastStream = 0, lastProgress = 0,
         lastFaultMask = UINT32_MAX;
DebouncedSwitch baselineSwitch, detailSwitch;
Baseline baseline;
bool baselineValid = false, offSeen = false, holdTriggered = false, switchCalibration = false;
uint32_t holdStart = 0, lastAnalysis = 0, lastLog = 0, lastMillis = 0, lastBaselineWrite = 0,
         bootAt = 0;
bool wroteBaseline = false, dumpRequested = false, structuredDumpRequested = false;
uint32_t dumpOffset = 0;
uint64_t uptimeMs = 0;
uint32_t session = 0, site = 1, armToken = 0, armAt = 0;
RiskResult risk;
VocResult voc;
Mode mode = Mode::Boot;
const char *calibrationStatus = "IDLE";
enum class Action { None, Calibrate, ClearLog, FormatLogs, NewSite };
Action armed = Action::None;
void beginCalibration(bool physical) {
  uint32_t now = millis();
  if (wroteBaseline && !elapsed(now, lastBaselineWrite, cfg::baselineWriteCooldownMs)) {
    console.print("CALIBRATION cooldown\n");
    return;
  }
  if (!wall.reading().valid || !bme.reading().valid) {
    console.print("CALIBRATION requires valid wall and air readings\n");
    return;
  }
  if (calibration.start(now)) {
    switchCalibration = physical;
    calibrationStatus = "CALIBRATING";
    console.print("CALIBRATING: hold on representative dry material; old baseline kept until "
                  "verified save\n");
  }
}
void arm(Action action, const char *name) {
  armed = action;
  armToken = esp_random();
  armAt = millis();
  console.print("ARMED %s; within %lus type CONFIRM %08lX\n", name,
                (unsigned long)(cfg::commandArmMs / 1000), (unsigned long)armToken);
}
void baselinePacket(const char *type) {
  protocol.packet(type, uptimeMs);
  protocol.boolean("valid", baselineValid);
  protocol.integer("baseline_id", baselineValid ? crc32(&baseline, sizeof(baseline)) : 0);
  protocol.number("mean", baseline.mean);
  protocol.number("median", baseline.median);
  protocol.number("stddev", baseline.stddev);
  protocol.integer("samples", baseline.count);
  protocol.integer("target", cfg::baselineDurationMs / cfg::baselineSampleMs);
  protocol.number("confidence", baseline.confidence);
  protocol.number("temperature_c", baseline.temperature);
  protocol.number("humidity_percent", baseline.humidity);
  protocol.text("status", calibrationStatus);
  protocol.boolean("success", !strcmp(calibrationStatus, "SAVED / VERIFIED"));
  protocol.finish();
}
bool researchCommand(const char *line) {
  uint32_t request = 0;
  const char *cmd = line;
  if (line[0] == '@') {
    char *end = nullptr;
    unsigned long id = strtoul(line + 1, &end, 10);
    if (end == line + 1 || *end != ' ' || id > UINT32_MAX)
      return false;
    request = id;
    cmd = end + 1;
  }
  if (!strcmp(cmd, "PING") || !strcmp(cmd, "DEVICE_INFO")) {
    protocol.packet("device_info", uptimeMs);
    protocol.text("product", "MoldSense");
    protocol.integer("sample_interval_ms", streamInterval);
    protocol.text("bsec_version", "3.3.0.0");
    protocol.text("model_sha256", moldmodel::sha256);
    protocol.integer("wall_setup_id", wallIdentity());
    protocol.number("wall_ema_alpha", cfg::wallEmaAlpha);
    protocol.number("wall_deadband_fraction", cfg::dryDeadbandFraction);
    protocol.number("wall_span_fraction", cfg::wetSpanFraction);
    protocol.number("wet_direction", cfg::wetDirection);
    protocol.number("environment_weight", cfg::risk.environmentWeight);
    protocol.number("wall_weight", cfg::risk.wallWeight);
    protocol.number("condensation_weight", cfg::risk.condensationWeight);
    protocol.number("voc_weight", cfg::risk.vocWeight);
    protocol.integer("configuration_id", crc32(&cfg::risk, sizeof(cfg::risk)));
    protocol.number("rh_caution", cfg::risk.rhCaution);
    protocol.number("rh_severe", cfg::risk.rhSevere);
    protocol.number("air_persistence_hours", cfg::risk.airPersistenceHours);
    protocol.number("wall_persistence_hours", cfg::risk.wallPersistenceHours);
    protocol.number("condensation_hours", cfg::risk.condensationHours);
    protocol.number("decay_hours", cfg::risk.decayHours);
    protocol.number("instant_fraction", cfg::risk.instantFraction);
    protocol.number("critical_hold_hours", cfg::risk.criticalHoldHours);
    protocol.number("elevated_threshold", cfg::risk.elevatedThreshold);
    protocol.number("high_threshold", cfg::risk.highThreshold);
    protocol.number("critical_threshold", cfg::risk.criticalThreshold);
    protocol.number("near_dewpoint_c", cfg::risk.nearDewPointC);
    protocol.number("wall_abnormal", cfg::risk.wallAbnormal);
    protocol.number("bme_temperature_offset", cfg::bmeTemperatureOffset);
    protocol.integer("wall_sample_ms", cfg::wallSampleMs);
    protocol.integer("baseline_duration_ms", cfg::baselineDurationMs);
    protocol.text("time_source", "UPTIME_ONLY");
    protocol.text("gas_profile", bme.modelAccepted() ? "AI_SCAN" : "IAQ_LP_3S");
    protocol.finish();
  } else if (!strcmp(cmd, "STATUS")) {
    protocol.packet("status", uptimeMs);
    protocol.boolean("bme_ready", bme.ready());
    protocol.boolean("air_valid", bme.reading().valid);
    protocol.text("wall_status", wallName(wall.reading().status));
    protocol.boolean("baseline_valid", baselineValid);
    protocol.boolean("nvs_ok", store.nvsOk());
    protocol.boolean("filesystem_ok", store.fsOk());
    protocol.boolean("storage_fault", store.fault());
    protocol.boolean("oled_ok", oled.ok());
    protocol.integer("free_heap_bytes", ESP.getFreeHeap());
    protocol.integer("minimum_free_heap_bytes", ESP.getMinFreeHeap());
    protocol.integer("reset_reason", esp_reset_reason());
    protocol.number("bsec_status", bme.reading().bsecStatus);
    protocol.number("bme_status", bme.reading().bmeStatus);
    protocol.integer("serial_dropped", console.dropped());
    protocol.text("bsec_state", bme.stateStatus());
    protocol.integer("iaq_accuracy", bme.reading().iaqAccuracy);
    protocol.integer("run_in_status", bme.reading().runIn);
    protocol.integer("stabilization_status", bme.reading().stabilization);
    protocol.finish();
  } else if (!strcmp(cmd, "GET_BASELINE")) {
    baselinePacket("baseline_info");
  } else if (!strcmp(cmd, "MODEL_INFO")) {
    protocol.packet("model_info", uptimeMs);
    protocol.text("name", moldmodel::name);
    protocol.text("sha256", moldmodel::sha256);
    protocol.text("validation_reference", moldmodel::validationReference);
    protocol.boolean("validated", moldmodel::validated);
    protocol.boolean("accepted", bme.modelAccepted());
    protocol.text("status", voc.status);
    protocol.text("bsec_state", bme.stateStatus());
    protocol.finish();
  } else if (!strcmp(cmd, "START_BASELINE") || !strcmp(cmd, "CLEAR_LOG") ||
             !strcmp(cmd, "NEW_SITE")) {
    if (calibration.active()) {
      protocol.ack(cmd, request, false, "CALIBRATION_ALREADY_ACTIVE", uptimeMs);
      return true;
    }
    armed = !strcmp(cmd, "START_BASELINE") ? Action::Calibrate
            : !strcmp(cmd, "CLEAR_LOG")    ? Action::ClearLog
                                           : Action::NewSite;
    armToken = esp_random();
    if (!armToken)
      armToken = 1;
    armAt = millis();
    protocol.ack(cmd, request, true, "CONFIRMATION_REQUIRED", uptimeMs, armToken);
    return true;
  } else if (!strncmp(cmd, "CONFIRM ", 8)) {
    char *end = nullptr;
    uint32_t token = strtoul(cmd + 8, &end, 16);
    Action action = armed;
    armed = Action::None;
    if (strlen(cmd + 8) != 8 || !end || *end || token != armToken || action == Action::None ||
        elapsed(millis(), armAt, cfg::commandArmMs)) {
      protocol.ack("CONFIRM", request, false, "TOKEN_INVALID_OR_EXPIRED", uptimeMs);
      return true;
    }
    bool ok = true;
    if (action == Action::Calibrate) {
      beginCalibration(false);
      ok = calibration.active();
    } else if (action == Action::ClearLog)
      ok = store.clearLog();
    else if (action == Action::NewSite) {
      riskEngine.newSite();
      ++site;
    } else if (action == Action::FormatLogs)
      ok = store.formatLogs();
    protocol.ack("CONFIRM", request, ok, ok ? "COMPLETED_OR_STARTED" : "ACTION_FAILED", uptimeMs);
    return true;
  } else if (!strcmp(cmd, "STOP_BASELINE")) {
    calibration.cancel();
    calibrationStatus = "CANCELLED";
    baselinePacket("calibration_complete");
  } else if (!strncmp(cmd, "SET_SAMPLE_INTERVAL ", 20)) {
    char *end = nullptr;
    unsigned long value = strtoul(cmd + 20, &end, 10);
    if (!end || *end || value < cfg::telemetryMinMs || value > cfg::telemetryMaxMs) {
      protocol.ack("SET_SAMPLE_INTERVAL", request, false, "RANGE_1000_TO_60000_MS", uptimeMs);
      return true;
    }
    streamInterval = value;
  } else if (!strcmp(cmd, "DUMP_LOG")) {
    dumpRequested = true;
    structuredDumpRequested = true;
    protocol.ack(cmd, request, true, "NDJSON_LOG_CHUNKS_FOLLOW", uptimeMs);
    return true;
  } else if (!strcmp(cmd, "STOP_DUMP")) {
    store.cancelDump();
    dumpRequested = false;
  } else if (!strcmp(cmd, "HELP")) {
    protocol.packet("status", uptimeMs);
    protocol.text("commands",
                  "PING STATUS DEVICE_INFO GET_BASELINE START_BASELINE STOP_BASELINE CONFIRM "
                  "MODEL_INFO DUMP_LOG STOP_DUMP CLEAR_LOG NEW_SITE SET_SAMPLE_INTERVAL HELP");
    protocol.finish();
  } else {
    if (line[0] == '@') {
      protocol.ack(cmd, request, false, "UNKNOWN_COMMAND", uptimeMs);
      return true;
    }
    return false;
  }
  protocol.ack(cmd, request, true, "OK", uptimeMs);
  return true;
}
void command(const char *cmd) {
  if (researchCommand(cmd))
    return;
  if (store.dumpActive()) {
    if (!strcmp(cmd, "STOP_DUMP")) {
      store.cancelDump();
      console.print("DUMP CANCELLED\n");
    }
    return;
  }
  if (!strcmp(cmd, "HELP")) {
    console.print(
        "STATUS EXPLAIN BASELINE CALIBRATE CANCEL DUMP STOP_DUMP CLEAR_LOG FORMAT_LOGS NEW_SITE "
        "MODEL_INFO SENSOR_INFO HELP\nDestructive/baseline actions return a one-use CONFIRM token. "
        "Switch: baseline ON 2s after OFF observed; other switch ON=DETAIL.\nNEW_SITE clears "
        "exposure history for a new scan position. Uptime is not UTC.\n");
  } else if (!strcmp(cmd, "STATUS") || !strcmp(cmd, "EXPLAIN")) {
    auto rolling = riskEngine.rolling();
    console.print("Mold Probability Index (UNVALIDATED screening index): %.2f%%\nRisk %s valid=%u "
                  "degraded=%u confidence=%.1f%%\nContributors (fixed order; sum to index):\n "
                  "Environment +%.2f (component %.1f)\n Wall +%.2f (component %.1f)\n Condensation "
                  "+%.2f (component %.1f)\n VOC +%.2f (component %.1f)\n",
                  risk.probability, riskName(risk.level), risk.valid, risk.degraded,
                  risk.confidence, risk.contributions[0], risk.environment, risk.contributions[1],
                  risk.wall, risk.contributions[2], risk.condensation, risk.contributions[3],
                  risk.voc);
    console.print(
        "Air T=%.2f RH=%.2f dewpoint=%.2f surfaceRH=%.2f (no surface probe by default)\nObserved "
        "hours RH>60=%.3f wall=%.3f condensation=%.3f consecutiveHigh=%.3f events=%lu "
        "highReadings=%lu\nRolling %u slots: RH=%.2f wall=%.2f cond=%.2f index=%.2f\nSession=%08lX "
        "site=%lu uptime_ms=%llu UTC=UNAVAILABLE\nNVS=%u FS=%u storageFault=%u "
        "corruptOrIncompatible=%u OLED=%u logDropped=%lu serialDropped=%lu\n%s\n",
        bme.reading().valid ? bme.reading().temperature : NAN,
        bme.reading().valid ? bme.reading().humidity : NAN, risk.dewPoint, risk.surfaceRh,
        risk.rhHours, risk.wallHours, risk.condensationHours, risk.elevatedHours,
        (unsigned long)risk.condensationEvents, (unsigned long)risk.consecutiveElevated,
        rolling.count, rolling.rh, rolling.wall, rolling.condensation, rolling.probability,
        (unsigned long)session, (unsigned long)site, (unsigned long long)uptimeMs, store.nvsOk(),
        store.fsOk(), store.fault(), store.corrupt(), oled.ok(), (unsigned long)store.dropped(),
        (unsigned long)console.dropped(), voc.status);
  } else if (!strcmp(cmd, "BASELINE"))
    console.print("Baseline valid=%u load=%s status=%s\nmean=%.3f median=%.3f stddev=%.3f n=%u/%u "
                  "confidence=%.1f T=%.2f RH=%.2f dew=%.2f typicalIndex=%.1f identity=%08lX\n",
                  baselineValid, store.wallLoadStatus, calibrationStatus, baseline.mean,
                  baseline.median, baseline.stddev, baseline.count, baseline.total,
                  baseline.confidence, baseline.temperature, baseline.humidity, baseline.dewPoint,
                  baseline.typicalMoisture, (unsigned long)baseline.setupId);
  else if (!strcmp(cmd, "MODEL_INFO")) {
    const auto &v = bme.version();
    console.print("%s\ninstalled=%u validated=%u accepted=%u name=%s\nsha256=%s\nvalidation=%s "
                  "class=%u count=%u quality=%.2f p=%.3f confidence=%.1f\nBSEC=%u.%u.%u.%u "
                  "state=%s fingerprint=%08lX sensor=%08lX\nIAQ and AI scan profiles are exclusive "
                  "on this sensor. Missing outputs are nan.\n",
                  voc.status, moldmodel::installed, moldmodel::validated, bme.modelAccepted(),
                  moldmodel::name, moldmodel::sha256, moldmodel::validationReference,
                  moldmodel::moldClass, moldmodel::classCount, moldmodel::validationQuality,
                  voc.probability, voc.confidence, v.major, v.minor, v.major_bugfix, v.minor_bugfix,
                  bme.stateStatus(), (unsigned long)bme.identity(), (unsigned long)bme.sensorId());
  } else if (!strcmp(cmd, "SENSOR_INFO")) {
    const auto &a = bme.reading();
    const auto &w = wall.reading();
    console.print(
        "BME ready=%u valid=%u status=%d BSEC=%d age=%lums\nrawT=%.3f compT=%.3f rawRH=%.3f "
        "compRH=%.3f pressurePa=%.1f gasOhm=%.1f\nIAQ=%.2f staticIAQ=%.2f IAQvalid=%u accuracy=%u "
        "eCO2ppm=%.2f bVOCppm=%.3f stabilize=%u runIn=%u gasAccuracy=%u\nWALL %s raw=%.1f "
        "filtered=%.1f baseline=%.1f delta=%.1f index=%.1f confidence=%.1f\nBackend=%s; touch "
        "connection/contact cannot be proven electrically. Surface temp unavailable.\n",
        bme.ready(), a.valid, a.bmeStatus, a.bsecStatus, (unsigned long)(millis() - a.sampleMs),
        a.rawTemperature, a.temperature, a.rawHumidity, a.humidity, a.pressure, a.gasOhms, a.iaq,
        a.staticIaq, a.iaqValid, a.iaqAccuracy, a.co2Equivalent, a.breathVocEquivalent,
        a.stabilization, a.runIn, a.gasAccuracy, wallName(w.status), w.raw, w.filtered, w.baseline,
        w.delta, w.index, w.confidence,
        cfg::wallBackend == cfg::WallBackend::Esp32Touch ? "ESP32 TOUCH" : "ADC VOLTAGE");
  } else if (!strcmp(cmd, "CALIBRATE"))
    arm(Action::Calibrate, "CALIBRATE DRY WALL");
  else if (!strcmp(cmd, "CLEAR_LOG"))
    arm(Action::ClearLog, "DELETE /ms_log.csv ONLY");
  else if (!strcmp(cmd, "FORMAT_LOGS")) {
    if (store.fsOk())
      console.print("REFUSED: filesystem already mounted\n");
    else
      arm(Action::FormatLogs, "FORMAT ENTIRE LITTLEFS PARTITION (ALL EXISTING FILES LOST)");
  } else if (!strcmp(cmd, "NEW_SITE"))
    arm(Action::NewSite, "RESET EXPOSURE HISTORY FOR NEW POSITION");
  else if (!strncmp(cmd, "CONFIRM ", 8)) {
    char *end = nullptr;
    unsigned long token = strtoul(cmd + 8, &end, 16);
    Action action = armed;
    armed = Action::None;
    if (strlen(cmd + 8) != 8 || !end || *end || token != armToken || action == Action::None ||
        elapsed(millis(), armAt, cfg::commandArmMs)) {
      console.print("CONFIRM rejected or expired\n");
      return;
    }
    switch (action) {
    case Action::Calibrate:
      beginCalibration(false);
      break;
    case Action::ClearLog:
      console.print("CLEAR_LOG %s\n", store.clearLog() ? "OK" : "FAIL");
      break;
    case Action::FormatLogs:
      console.print("FORMAT_LOGS %s\n", store.formatLogs() ? "OK" : "FAIL");
      break;
    case Action::NewSite:
      riskEngine.newSite();
      ++site;
      console.print("NEW_SITE %lu: observed history reset\n", (unsigned long)site);
      break;
    default:
      break;
    }
  } else if (!strcmp(cmd, "CANCEL")) {
    armed = Action::None;
    calibration.cancel();
    calibrationStatus = "CANCELLED";
    console.print("CANCELLED; prior baseline retained\n");
  } else if (!strcmp(cmd, "DUMP")) {
    structuredDumpRequested = false;
    dumpRequested = true;
    console.print("DUMP REQUESTED (readings continue)\n");
  } else if (!strcmp(cmd, "STOP_DUMP")) {
    dumpRequested = false;
  } else
    console.print("UNKNOWN COMMAND; type HELP\n");
}
} // namespace
void appSetup() {
  console.begin(command);
  session = esp_random();
  protocol.begin(console, session);
  bootAt = lastMillis = millis();
  console.print("MOLDSENSE v1.0-rc1 | UNVALIDATED screening index, not mold detection\n");
  store.begin();
  baselineValid = store.loadWall(baseline);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, cfg::i2cHz);
  Wire.setTimeOut(cfg::i2cTimeoutMs);
  bme.begin(store, millis());
  wall.begin();
  baselineSwitch.begin(SWITCH_BASELINE_PIN, millis());
  detailSwitch.begin(SWITCH_MODE_PIN, millis());
  offSeen = !baselineSwitch.active();
  mode = Mode::SelfTest;
  console.print("Storage NVS=%u FS=%u baseline=%s BME=%u. HELP for commands.\n", store.nvsOk(),
                store.fsOk(), store.wallLoadStatus, bme.ready());
}
void appLoop() {
  uint32_t now = millis();
  uptimeMs += uint32_t(now - lastMillis);
  lastMillis = now;
  console.tick(store.dumpActive() && !store.structuredDump());
  bme.tick(now);
  wall.tick(now, baselineValid ? &baseline : nullptr);
  bool changed = baselineSwitch.tick(now);
  detailSwitch.tick(now);
  if (!baselineSwitch.active()) {
    offSeen = true;
    holdTriggered = false;
    if (changed && switchCalibration && calibration.active()) {
      calibration.cancel();
      calibrationStatus = "CANCELLED";
    }
  } else if (offSeen) {
    if (changed)
      holdStart = now;
    if (!holdTriggered && elapsed(now, holdStart, cfg::switchArmMs)) {
      holdTriggered = true;
      beginCalibration(true);
    }
  }
  bool wasCalibrating = calibration.active();
  calibration.tick(now, wall.reading(), bme.reading());
  if (wasCalibrating && !calibration.active()) {
    Baseline next;
    calibrationStatus = calibration.status();
    if (calibration.takeResult(next)) {
      if (store.saveWall(next)) {
        baseline = next;
        baselineValid = true;
        lastBaselineWrite = now;
        wroteBaseline = true;
        calibrationStatus = "SAVED / VERIFIED";
        riskEngine.newSite();
        ++site;
      } else
        calibrationStatus = "SAVE FAILED - OLD KEPT";
    }
    console.print("CALIBRATION %s n=%u\n", calibrationStatus, calibration.count());
    baselinePacket("calibration_complete");
  }
  if (elapsed(now, lastAnalysis, cfg::analysisMs)) {
    lastAnalysis = now;
    voc = classifier.evaluate(bme.reading(), bme.metadata(), bme.modelAccepted(), now);
    risk = riskEngine.update(bme.reading(), wall.reading(), SurfaceReading{}, voc, now,
                             !calibration.active());
  }
  mode = calibration.active()          ? Mode::BaselineCalibration
         : !elapsed(now, bootAt, 2000) ? Mode::SelfTest
         : detailSwitch.active()       ? Mode::DetailView
         : !risk.valid                 ? Mode::SensorError
                                       : Mode::NormalScan;
  ViewState view;
  view.mode = mode;
  view.air = bme.reading();
  view.wall = wall.reading();
  view.voc = voc;
  view.risk = risk;
  view.bmeReady = bme.ready();
  view.storage = store.nvsOk() && !store.fault();
  view.baseline = baselineValid;
  view.progress = calibration.progress(now);
  view.uptimeMs = uptimeMs;
  view.baselineId = baselineValid ? crc32(&baseline, sizeof(baseline)) : 0;
  view.calibration = calibrationStatus;
  view.bsecState = bme.stateStatus();
  oled.tick(now, view);
  if (cfg::loggingEnabled && elapsed(now, lastLog, cfg::logIntervalMs)) {
    lastLog = now;
    char line[640];
    const auto &a = bme.reading();
    const auto &w = wall.reading();
    int n = snprintf(line, sizeof(line),
                     "%08lX,%lu,%llu,,%.2f,%.2f,%.1f,%.2f,%.1f,%.2f,%u,%.1f,%.1f,%.1f,%.1f,%.2f,%."
                     "2f,%.2f,%.4f,%.2f,%.1f,%s",
                     (unsigned long)session, (unsigned long)site, (unsigned long long)uptimeMs,
                     a.valid ? a.temperature : NAN, a.valid ? a.humidity : NAN,
                     a.valid ? a.pressure : NAN, risk.dewPoint, a.valid ? a.gasOhms : NAN,
                     a.iaqValid ? a.iaq : NAN, a.iaqAccuracy, w.raw, w.valid ? w.filtered : NAN,
                     w.baseline, w.valid ? w.delta : NAN, w.valid ? w.index : NAN, risk.environment,
                     risk.condensation, voc.valid ? voc.probability : NAN,
                     risk.valid ? risk.probability : NAN, risk.confidence, riskName(risk.level));
    if (n > 0 && size_t(n) < sizeof(line))
      store.appendLog(line);
  }
  uint32_t faultMask = (!view.air.valid ? 1u : 0u) | (!view.wall.valid ? 2u : 0u) |
                       (!baselineValid ? 4u : 0u) | (!view.storage ? 8u : 0u) |
                       (!oled.ok() ? 16u : 0u) | (!voc.valid ? 32u : 0u);
  if (faultMask != lastFaultMask && console.idle() && !store.dumpActive()) {
    lastFaultMask = faultMask;
    protocol.packet(faultMask ? "warning" : "status", uptimeMs);
    protocol.integer("fault_mask", faultMask);
    protocol.text("reason",
                  "FAULT_CHANGE bits:1=air 2=wall 4=baseline 8=storage 16=OLED 32=VOC unavailable");
    protocol.finish();
  }
  if (dumpRequested && console.idle()) {
    dumpRequested = false;
    if (!store.startDump(structuredDumpRequested)) {
      protocol.packet("error", uptimeMs);
      protocol.text("reason", "DUMP_UNAVAILABLE");
      protocol.finish();
    }
    dumpOffset = 0;
  }
  if ((!store.dumpActive() || store.structuredDump()) && !dumpRequested &&
      elapsed(now, lastStream, streamInterval)) {
    lastStream = now;
    protocol.reading(view, site, uptimeMs, streamInterval);
  }
  if (calibration.active() && elapsed(now, lastProgress, 1000)) {
    lastProgress = now;
    protocol.packet("calibration_progress", uptimeMs);
    protocol.integer("samples", calibration.count());
    protocol.integer("target", cfg::baselineDurationMs / cfg::baselineSampleMs);
    protocol.integer("progress", calibration.progress(now));
    Baseline progressStats = calibration.statistics();
    protocol.number("mean", progressStats.mean);
    protocol.number("median", progressStats.median);
    protocol.number("stddev", progressStats.stddev);
    protocol.text("status", calibration.status());
    protocol.finish();
  }
  if (store.dumpActive() && store.structuredDump() && console.idle()) {
    uint8_t bytes[64];
    size_t n = store.readDumpChunk(bytes, sizeof(bytes));
    char hex[129];
    for (size_t i = 0; i < n; i++)
      snprintf(hex + i * 2, 3, "%02X", bytes[i]);
    hex[n * 2] = 0;
    if (n) {
      protocol.packet("log_chunk", uptimeMs);
      protocol.integer("offset", dumpOffset);
      protocol.integer("crc32", crc32(bytes, n));
      protocol.text("hex", hex);
      protocol.finish();
      dumpOffset += n;
    }
    if (!store.dumpActive()) {
      protocol.packet(store.dumpFailed() ? "error" : "log_complete", uptimeMs);
      protocol.integer("bytes", dumpOffset);
      protocol.integer("expected_bytes", store.dumpSize());
      protocol.text("reason", store.dumpFailed() ? "LOG_READ_FAILED" : "OK");
      protocol.finish();
    }
  }
  store.tick(now);
  yield();
}
