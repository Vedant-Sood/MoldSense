#pragma once
#include <string>
#include <map>
#include <memory>
#include <algorithm>
#include <cstring>
struct File {
  inline static bool failRead = false;
  std::shared_ptr<std::string> data;
  size_t position = 0;
  operator bool() const {
    return bool(data);
  }
  size_t size() {
    return data ? data->size() : 0;
  }
  void close() {
    data.reset();
  }
  size_t read(uint8_t *out, size_t n) {
    if (!data || failRead)
      return 0;
    n = std::min(n, data->size() - position);
    memcpy(out, data->data() + position, n);
    position += n;
    return n;
  }
  size_t write(const uint8_t *in, size_t n) {
    if (!data)
      return 0;
    data->append((const char *)in, n);
    return n;
  }
  void println(const char *s) {
    if (data) {
      *data += s;
      *data += '\n';
    }
  }
  void flush() {}
};
struct FakeFS {
  std::map<std::string, std::shared_ptr<std::string>> files;
  bool mounted = true;
  bool begin(bool format) {
    return mounted || format;
  }
  bool format() {
    files.clear();
    mounted = true;
    return true;
  }
  File open(const char *name, const char *mode) {
    if (!mounted)
      return {};
    if (*mode == 'a' && !files.count(name))
      files[name] = std::make_shared<std::string>();
    if (!files.count(name))
      return {};
    File f;
    f.data = files[name];
    return f;
  }
  bool exists(const char *name) {
    return files.count(name);
  }
  bool remove(const char *name) {
    return files.erase(name) > 0;
  }
  size_t totalBytes() {
    return 1024 * 1024;
  }
  size_t usedBytes() {
    size_t n = 0;
    for (auto &kv : files)
      n += kv.second->size();
    return n;
  }
};
inline FakeFS LittleFS;
