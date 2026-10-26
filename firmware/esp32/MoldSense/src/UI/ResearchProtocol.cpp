#include "ResearchProtocol.h"
#include "../Models/MoldModelConfig.h"
#include <stdarg.h>
namespace ms {
void ResearchProtocol::begin(Console &c, uint32_t session) {
  console_ = &c;
  boot_ = session;
  snprintf(device_, sizeof(device_), "MOLDSENSE_%012llX", (unsigned long long)ESP.getEfuseMac());
}
void ResearchProtocol::add(const char *format, ...) {
  if (overflow_)
    return;
  va_list args;
  va_start(args, format);
  int n = vsnprintf(packet_ + used_, sizeof(packet_) - used_, format, args);
  va_end(args);
  if (n < 0 || size_t(n) >= sizeof(packet_) - used_) {
    overflow_ = true;
    return;
  }
  used_ += n;
}
void ResearchProtocol::packet(const char *type, uint64_t uptime) {
  used_ = 0;
  overflow_ = false;
  add("{\"type\":\"%s\",\"protocol_version\":1,\"device_id\":\"%s\",\"firmware_version\":\"1.0.0-"
      "rc1\",\"boot_id\":\"%08lX\",\"sequence\":%llu,\"uptime_ms\":%llu",
      type, device_, (unsigned long)boot_, (unsigned long long)sequence_++,
      (unsigned long long)uptime);
}
void ResearchProtocol::number(const char *key, double value) {
  if (isfinite(value))
    add(",\"%s\":%.6g", key, value);
  else
    add(",\"%s\":null", key);
}
void ResearchProtocol::integer(const char *key, uint64_t value) {
  add(",\"%s\":%llu", key, (unsigned long long)value);
}
void ResearchProtocol::boolean(const char *key, bool value) {
  add(",\"%s\":%s", key, value ? "true" : "false");
}
void ResearchProtocol::text(const char *key, const char *value) {
  add(",\"%s\":\"", key);
  for (size_t i = 0; value && value[i]; i++) {
    unsigned char c = value[i];
    if (c == '"' || c == '\\')
      add("\\%c", c);
    else if (c >= 32 && c < 127)
      add("%c", c);
    else
      add("?");
  }
  add("\"");
}
void ResearchProtocol::finish() {
  add("}\n");
  if (!overflow_)
    console_->print("%s", packet_);
}
void ResearchProtocol::ack(const char *command, uint32_t request, bool success, const char *reason,
                           uint64_t uptime, uint32_t token) {
  packet("command_ack", uptime);
  integer("request_id", request);
  text("command", command);
  boolean("success", success);
  text("reason", reason);
  if (token) {
    char value[9];
    snprintf(value, sizeof(value), "%08lX", (unsigned long)token);
    text("confirmation_token", value);
  }
  finish();
}
void ResearchProtocol::reading(const ViewState &v, uint32_t site, uint64_t uptime,
                               uint32_t interval) {
  packet("reading", uptime);
  integer("site_id", site);
  integer("sample_interval_ms", interval);
  number("temperature_c", v.air.valid ? v.air.temperature : NAN);
  number("raw_temperature_c", v.air.rawTemperature);
  number("humidity_percent", v.air.valid ? v.air.humidity : NAN);
  number("raw_humidity_percent", v.air.rawHumidity);
  number("pressure_pa", v.air.valid ? v.air.pressure : NAN);
  number("dew_point_c", v.risk.dewPoint);
  number("gas_resistance_ohms", v.air.valid ? v.air.gasOhms : NAN);
  integer("gas_observation_id", v.air.observationId);
  integer("gas_heater_index", v.air.heaterIndex);
  integer("gas_sample_uptime_ms", v.air.gasObservationMs);
  integer("air_sample_uptime_ms", v.air.sampleMs);
  integer("wall_sample_uptime_ms", v.wall.sampleMs);
  number("wall_cap_raw", v.wall.raw);
  number("wall_cap_filtered", v.wall.valid ? v.wall.filtered : NAN);
  number("wall_moisture_index", v.wall.valid ? v.wall.index : NAN);
  number("wall_baseline", v.wall.baseline);
  number("wall_deviation", v.wall.valid ? v.wall.delta : NAN);
  number("wall_calibration_confidence", v.wall.confidence);
  number("iaq", v.air.iaqValid ? v.air.iaq : NAN);
  number("static_iaq", v.air.iaqValid ? v.air.staticIaq : NAN);
  integer("iaq_accuracy", v.air.iaqAccuracy);
  number("co2_equivalent_ppm", v.air.iaqValid ? v.air.co2Equivalent : NAN);
  number("breath_voc_equivalent_ppm", v.air.iaqValid ? v.air.breathVocEquivalent : NAN);
  integer("stabilization_status", v.air.stabilization);
  integer("run_in_status", v.air.runIn);
  number("mold_probability", v.risk.valid ? v.risk.probability : NAN);
  number("confidence", v.risk.confidence);
  text("risk_level", riskName(v.risk.level));
  text("score_semantics", "UNVALIDATED_SCREENING_INDEX");
  number("environment_risk", v.risk.environment);
  number("condensation_risk", v.risk.condensation);
  number("voc_mold_probability", v.voc.probability);
  number("environment_contribution", v.risk.contributions[0]);
  number("wall_contribution", v.risk.contributions[1]);
  number("condensation_contribution", v.risk.contributions[2]);
  number("voc_contribution", v.risk.contributions[3]);
  number("rh_exposure_hours", v.risk.rhHours);
  number("wall_exposure_hours", v.risk.wallHours);
  boolean("air_valid", v.air.valid);
  boolean("wall_valid", v.wall.valid);
  boolean("baseline_valid", v.baseline);
  text("wall_status", wallName(v.wall.status));
  text("model_status", v.voc.status);
  text("model_sha256", moldmodel::sha256);
  integer("baseline_id", v.baselineId);
  text("data_quality", !v.air.valid || !v.wall.valid ? "SENSOR_ERROR"
                       : v.air.runIn == 0            ? "WARMING_UP"
                                                     : "VALID");
  finish();
}
} // namespace ms
