#pragma once
#include <map>
#include <string>
#include <vector>
#include <cstring>
struct Preferences {
  inline static std::map<std::string, std::map<std::string, std::vector<uint8_t>>> db;
  inline static bool failWrite = false, tearWrite = false;
  std::string name;
  bool begin(const char *n, bool) {
    name = n;
    return true;
  }
  size_t getBytesLength(const char *key) {
    return db[name][key].size();
  }
  size_t getBytes(const char *key, void *out, size_t n) {
    auto &v = db[name][key];
    if (v.size() > n)
      return 0;
    memcpy(out, v.data(), v.size());
    return v.size();
  }
  size_t putBytes(const char *key, const void *ptr, size_t n) {
    if (failWrite)
      return 0;
    const uint8_t *p = (const uint8_t *)ptr;
    size_t written = tearWrite ? n / 2 : n;
    db[name][key] = std::vector<uint8_t>(p, p + written);
    return written;
  }
};
