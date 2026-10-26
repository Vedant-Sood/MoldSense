#pragma once
#include <stdint.h>
#include <stddef.h>
// tools/import_model.py creates MoldModelData.h from an explicitly selected export.
// No historical Chai/other classifier is silently relabelled as mold.
#if __has_include("MoldModelData.h")
#include "MoldModelData.h"
#else
namespace moldmodel {
constexpr bool installed = false, validated = false;
constexpr uint8_t moldClass = 0, classCount = 0;
constexpr float validationQuality = 0;
constexpr uint32_t staleMs = 45000;
constexpr const char *name = "NOT TRAINED";
constexpr const char *sha256 = "NONE";
constexpr const char *validationReference = "NONE";
constexpr uint8_t data[] = {0};
constexpr size_t size = 0;
} // namespace moldmodel
#endif
