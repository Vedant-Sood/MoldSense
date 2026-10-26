#pragma once
#include <stdint.h>
#include <stddef.h>
#include <algorithm>
#include <string>
struct FakeSerial {
  void begin(unsigned long) {}
  int available() {
    return 0;
  }
  int read() {
    return -1;
  }
  std::string output;
  int availableForWrite() {
    return 64;
  }
  size_t write(const uint8_t *p, size_t n) {
    output.append((const char *)p, n);
    return n;
  }
  void println(const char *p) {
    output += p;
    output += '\n';
  }
};
inline FakeSerial Serial;

struct FakeESP {
  uint64_t getEfuseMac() {
    return 0x112233445566ULL;
  }
};
inline FakeESP ESP;
