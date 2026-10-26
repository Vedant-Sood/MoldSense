#pragma once
#include "Record.h"
#include <Arduino.h>
#include <Preferences.h>
#include <LittleFS.h>
namespace ms {
class StorageManager {
public:
  bool begin();
  bool loadWall(Baseline &);
  bool saveWall(const Baseline &);
  bool loadBsec(void *bytes, size_t size, uint32_t identity);
  bool saveBsec(const void *bytes, size_t size, uint32_t identity);
  void appendLog(const char *line);
  void tick(uint32_t now);
  bool startDump(bool structured = false);
  size_t readDumpChunk(uint8_t *bytes, size_t capacity);
  bool structuredDump() const {
    return structuredDump_;
  }
  size_t dumpSize() const {
    return dumpSize_;
  }
  bool dumpFailed() const {
    return dumpFailed_;
  }
  void cancelDump();
  bool clearLog();
  bool formatLogs();
  bool nvsOk() const {
    return nvsOk_;
  }
  bool fsOk() const {
    return fsOk_;
  }
  bool fault() const {
    return fault_;
  }
  bool corrupt() const {
    return corrupt_;
  }
  bool dumpActive() const {
    return bool(dump_);
  }
  uint32_t dropped() const {
    return dropped_;
  }
  const char *wallLoadStatus = "NOT LOADED";
  const char *bsecLoadStatus = "NOT LOADED";

private:
  bool load(Preferences &, uint32_t, void *, size_t, const char *&);
  bool save(Preferences &, uint32_t, const void *, size_t);
  bool flush();
  Preferences wall_, bsec_;
  bool nvsOk_ = false, fsOk_ = false, fault_ = false, corrupt_ = false;
  char buffer_[cfg::logBufferBytes]{};
  size_t used_ = 0;
  uint32_t lastFlush_ = 0, dropped_ = 0;
  bool structuredDump_ = false, dumpFailed_ = false;
  File dump_;
  size_t dumpRemaining_ = 0, dumpSize_ = 0;
};
} // namespace ms
