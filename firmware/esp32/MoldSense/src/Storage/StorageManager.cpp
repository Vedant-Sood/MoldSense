#include "StorageManager.h"
namespace ms {
bool StorageManager::begin() {
  bool w = wall_.begin("ms_wall_v1", false), b = bsec_.begin("ms_bsec_v1", false);
  nvsOk_ = w && b;
  // Never format implicitly: an existing device may contain irreplaceable captures.
  fsOk_ = LittleFS.begin(false);
  fault_ = !nvsOk_ || (cfg::loggingEnabled && !fsOk_);
  return nvsOk_;
}
bool StorageManager::load(Preferences &p, uint32_t id, void *out, size_t n, const char *&status) {
  if (!nvsOk_ || n > 512) {
    status = "STORAGE ERROR";
    return false;
  }
  Record a{}, b{};
  size_t la = p.getBytesLength("a"), lb = p.getBytesLength("b");
  bool va = la == sizeof(a) && p.getBytes("a", &a, sizeof(a)) == sizeof(a) && recordValid(a, id, n);
  bool vb = lb == sizeof(b) && p.getBytes("b", &b, sizeof(b)) == sizeof(b) && recordValid(b, id, n);
  if ((la && !va) || (lb && !vb))
    corrupt_ = true;
  if (!va && !vb) {
    status = (la || lb) ? "CORRUPT / INCOMPATIBLE" : "MISSING";
    return false;
  }
  const Record &r = vb && (!va || newer(b.sequence, a.sequence)) ? b : a;
  memcpy(out, r.payload, n);
  status = (la && !va) || (lb && !vb) ? "RECOVERED OTHER SLOT" : "RESTORED";
  return true;
}
bool StorageManager::save(Preferences &p, uint32_t id, const void *input, size_t n) {
  if (!nvsOk_ || n > 512)
    return false;
  Record a{}, b{}, r{};
  bool va = p.getBytesLength("a") == sizeof(a) && p.getBytes("a", &a, sizeof(a)) == sizeof(a) &&
            recordValid(a, id, n);
  bool vb = p.getBytesLength("b") == sizeof(b) && p.getBytes("b", &b, sizeof(b)) == sizeof(b) &&
            recordValid(b, id, n);
  bool useA = va && (!vb || newer(a.sequence, b.sequence));
  const char *key = useA ? "b" : "a";
  r.identity = id;
  r.length = n;
  r.sequence = (useA ? a.sequence : vb ? b.sequence : 0) + 1;
  memcpy(r.payload, input, n);
  r.crc = crc32(&r, offsetof(Record, crc));
  bool ok = p.putBytes(key, &r, sizeof(r)) == sizeof(r);
  Record check{};
  ok = ok && p.getBytes(key, &check, sizeof(check)) == sizeof(check) && recordValid(check, id, n) &&
       memcmp(&r, &check, sizeof(r)) == 0;
  if (!ok)
    fault_ = true;
  return ok;
}
bool StorageManager::loadWall(Baseline &b) {
  if (!load(wall_, wallIdentity(), &b, sizeof(b), wallLoadStatus))
    return false;
  bool valid = b.setupId == wallIdentity() && b.count >= 3 && b.count <= b.total &&
               b.total <= cfg::baselineCapacity && finite(b.median) && b.median > cfg::wallRawMin &&
               b.median < cfg::wallRawMax && finite(b.mean) && finite(b.stddev) && b.stddev >= 0 &&
               finite(b.confidence) && b.confidence > 0 && b.confidence <= 100 &&
               finite(b.humidity) && b.humidity > 0 && b.humidity <= 100 && finite(b.temperature);
  if (!valid) {
    wallLoadStatus = "INVALID CONTENT";
    corrupt_ = true;
  }
  return valid;
}
bool StorageManager::saveWall(const Baseline &b) {
  return save(wall_, wallIdentity(), &b, sizeof(b));
}
bool StorageManager::loadBsec(void *b, size_t n, uint32_t id) {
  return load(bsec_, id, b, n, bsecLoadStatus);
}
bool StorageManager::saveBsec(const void *b, size_t n, uint32_t id) {
  return save(bsec_, id, b, n);
}
void StorageManager::appendLog(const char *line) {
  if (!cfg::loggingEnabled || !fsOk_)
    return;
  size_t n = strlen(line);
  if (n + 1 > sizeof(buffer_) - used_) {
    ++dropped_;
    return;
  }
  memcpy(buffer_ + used_, line, n);
  used_ += n;
  buffer_[used_++] = '\n';
}
bool StorageManager::flush() {
  if (!used_)
    return true;
  if (!fsOk_ || dump_)
    return false;
  File check = LittleFS.open("/ms_log.csv", "r");
  size_t size = check ? check.size() : 0;
  check.close();
  // Bounded log; stop on full. No automatic removal of any existing log.
  if (size + used_ > cfg::logMaxBytes ||
      LittleFS.totalBytes() - LittleFS.usedBytes() < used_ + 8192) {
    fault_ = true;
    return false;
  }
  File f = LittleFS.open("/ms_log.csv", "a");
  if (!f) {
    fault_ = true;
    return false;
  }
  if (size == 0)
    f.println("session,site,uptime_ms,utc_unix_s,temp_c,rh_pct,pressure_pa,dewpoint_c,gas_ohm,iaq,"
              "iaq_accuracy,wall_raw,wall_filtered,baseline,delta,wall_index,environment,"
              "condensation,voc_probability,index_pct,confidence,risk");
  bool ok = f.write(reinterpret_cast<const uint8_t *>(buffer_), used_) == used_;
  f.flush();
  f.close();
  // On ambiguous/partial writes don't retry rows: a power cut may truncate the last row.
  used_ = 0;
  if (!ok)
    fault_ = true;
  return ok;
}
void StorageManager::tick(uint32_t now) {
  if (dump_ && !structuredDump_) {
    int capacity = Serial.availableForWrite();
    uint8_t bytes[64];
    size_t n = fminf(fminf(capacity, sizeof(bytes)), dumpRemaining_);
    if (n) {
      n = dump_.read(bytes, n);
      if (n) {
        Serial.write(bytes, n);
        dumpRemaining_ -= n;
      } else
        dumpRemaining_ = 0;
    }
    if (!dumpRemaining_) {
      dump_.close();
      Serial.println("\nDUMP END");
    }
  }
  if (elapsed(now, lastFlush_, cfg::logFlushMs)) {
    lastFlush_ = now;
    if (!dump_)
      flush();
  }
}
bool StorageManager::startDump(bool structured) {
  if (dump_ || !fsOk_)
    return false;
  if (!flush())
    return false;
  dump_ = LittleFS.open("/ms_log.csv", "r");
  if (!dump_)
    return false;
  structuredDump_ = structured;
  dumpFailed_ = false;
  dumpSize_ = dumpRemaining_ = dump_.size();
  return true;
}
size_t StorageManager::readDumpChunk(uint8_t *bytes, size_t capacity) {
  if (!dump_ || !structuredDump_)
    return 0;
  size_t n = dump_.read(bytes, std::min(capacity, dumpRemaining_));
  dumpRemaining_ -= n;
  if (!n && dumpRemaining_) {
    dumpFailed_ = true;
    fault_ = true;
  }
  if (!dumpRemaining_ || !n)
    dump_.close();
  return n;
}
void StorageManager::cancelDump() {
  if (dump_)
    dump_.close();
  dumpRemaining_ = 0;
}
bool StorageManager::clearLog() {
  if (!fsOk_ || dump_)
    return false;
  used_ = 0;
  bool ok = !LittleFS.exists("/ms_log.csv") || LittleFS.remove("/ms_log.csv");
  if (!ok)
    fault_ = true;
  return ok;
}
bool StorageManager::formatLogs() {
  if (fsOk_ || dump_)
    return false;
  if (!LittleFS.format())
    return false;
  fsOk_ = LittleFS.begin(false);
  return fsOk_;
}
} // namespace ms
