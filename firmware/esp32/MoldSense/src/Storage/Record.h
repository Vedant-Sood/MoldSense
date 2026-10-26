#pragma once
#include "../Core/Math.h"
#include <string.h>
#include <stddef.h>
namespace ms {
// Fixed records are committed with one NVS blob operation. Inactive slot first.
struct Record {
  uint32_t magic = 0x4d534e31, schema = 1, sequence = 0, identity = 0, length = 0;
  uint8_t payload[512]{};
  uint32_t crc = 0;
};
inline bool recordValid(const Record &r, uint32_t id, size_t bytes) {
  return r.magic == 0x4d534e31 && r.schema == 1 && r.identity == id && r.length == bytes &&
         bytes <= sizeof(r.payload) && r.crc == crc32(&r, offsetof(Record, crc));
}
inline bool newer(uint32_t a, uint32_t b) {
  return int32_t(a - b) > 0;
}
} // namespace ms
