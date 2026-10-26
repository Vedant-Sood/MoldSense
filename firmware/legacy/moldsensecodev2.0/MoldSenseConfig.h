#pragma once

#include <Arduino.h>

enum class DeviceMode : uint8_t {
  LOG = 0,
  CAPTURE = 1,
  TEST = 2
};

namespace MoldSenseConfig {
constexpr uint8_t BME_ADDRESS = 0x76;
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t LOG_INTERVAL_MS = 60UL * 1000UL;
constexpr uint32_t STATE_SAVE_INTERVAL_MS = 6UL * 60UL * 60UL * 1000UL;
constexpr uint32_t CAPTURE_POLL_MS = 140;
constexpr size_t MAX_UPLOAD_BYTES = 256UL * 1024UL;

// Common 0.8-inch monochrome OLED: SSD1306, 128x64, I2C. The display shares
// the BME688 I2C bus (GPIO 21 SDA / GPIO 22 SCL on the DevKit V1).
constexpr uint8_t OLED_WIDTH = 128;
constexpr uint8_t OLED_HEIGHT = 64;
constexpr uint8_t OLED_ADDRESS_PRIMARY = 0x3C;
constexpr uint8_t OLED_ADDRESS_ALTERNATE = 0x3D;
constexpr uint32_t OLED_REFRESH_MS = 500;

// Three active-low selector inputs. Wire each slide switch between its GPIO
// and GND. Exactly one switch should be ON at a time. These pins are ordinary
// GPIOs on the ESP32 DevKit V1 and do not conflict with the I2C bus.
constexpr uint8_t LOG_SWITCH_PIN = 25;
constexpr uint8_t INITIALIZE_SWITCH_PIN = 26;
constexpr uint8_t TEST_SWITCH_PIN = 27;
constexpr uint32_t MODE_SWITCH_DEBOUNCE_MS = 80;

constexpr const char *PREFS_NAMESPACE = "moldsense";
constexpr const char *SESSION_FILE = "/sessions.csv";
constexpr const char *LOG_FILE = "/environment.csv";
// BSEC state blobs are version-specific. Keep the old BSEC2 files untouched
// and start fresh BSEC3 state so an incompatible baseline is never restored.
constexpr const char *LOG_STATE_FILE = "/bsec3_state.bin";
constexpr const char *TEST_STATE_FILE = "/bsec3_model_state.bin";
constexpr const char *MODEL_FILE = "/bsec_model.bin";

// Bosch HP-354, the documented default profile. Each multiplier is applied
// to the 140 ms time base by the BME68x parallel-mode API.
constexpr uint16_t HEATER_TEMPERATURES[10] = {
  320, 100, 100, 100, 200, 200, 200, 320, 320, 320
};
constexpr uint16_t HEATER_MULTIPLIERS[10] = {
  5, 2, 10, 30, 5, 5, 5, 5, 5, 5
};
constexpr uint8_t HEATER_STEPS = 10;
constexpr const char *HEATER_PROFILE_ID = "heater_354";
constexpr const char *DUTY_PROFILE_ID = "duty_1";
constexpr const char *FIRMWARE_VERSION = "MoldSense-2.0.0-switch";
}
