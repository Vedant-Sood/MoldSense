#include "PersistentClock.h"

#include <Preferences.h>
#include <sys/time.h>
#include <time.h>

#include "MoldSenseConfig.h"

namespace {
constexpr uint64_t MIN_REASONABLE_EPOCH = 1704067200ULL;  // 2024-01-01 UTC

void applyEpoch(uint64_t epoch) {
  timeval value{};
  value.tv_sec = static_cast<time_t>(epoch);
  settimeofday(&value, nullptr);
}
}

void PersistentClock::begin() {
  uint64_t live = static_cast<uint64_t>(time(nullptr));
  if (live >= MIN_REASONABLE_EPOCH) {
    valid_ = true;
    quality_ = "RTC";
    return;
  }

  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, true);
  uint64_t saved = prefs.getULong64("clockEpoch", 0);
  prefs.end();

  if (saved >= MIN_REASONABLE_EPOCH) {
    applyEpoch(saved);
    valid_ = true;
    quality_ = "RESTORED_ESTIMATE";
  }
}

bool PersistentClock::setUnixTime(uint64_t epoch) {
  if (epoch < MIN_REASONABLE_EPOCH) return false;
  applyEpoch(epoch);
  valid_ = true;
  quality_ = "MANUAL";
  checkpoint();
  return true;
}

bool PersistentClock::valid() const {
  return valid_;
}

uint64_t PersistentClock::now() const {
  return valid_ ? static_cast<uint64_t>(time(nullptr)) : 0;
}

String PersistentClock::iso8601() const {
  if (!valid_) return "UNSET";
  time_t value = static_cast<time_t>(now());
  tm utc{};
  gmtime_r(&value, &utc);
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utc);
  return String(buffer);
}

String PersistentClock::quality() const {
  return quality_;
}

void PersistentClock::checkpoint() {
  if (!valid_) return;
  Preferences prefs;
  prefs.begin(MoldSenseConfig::PREFS_NAMESPACE, false);
  prefs.putULong64("clockEpoch", now());
  prefs.end();
}
