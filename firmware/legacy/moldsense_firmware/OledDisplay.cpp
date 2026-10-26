#include "OledDisplay.h"

bool OledDisplay::begin(TwoWire &wire) {
  if (respondsAt(wire, MoldSenseConfig::OLED_ADDRESS_PRIMARY) &&
      display_.begin(SSD1306_SWITCHCAPVCC, MoldSenseConfig::OLED_ADDRESS_PRIMARY, false, false)) {
    available_ = true;
  } else if (respondsAt(wire, MoldSenseConfig::OLED_ADDRESS_ALTERNATE) &&
             display_.begin(SSD1306_SWITCHCAPVCC, MoldSenseConfig::OLED_ADDRESS_ALTERNATE, false, false)) {
    available_ = true;
  }
  if (available_) {
    display_.clearDisplay();
    display_.setTextColor(SSD1306_WHITE);
    display_.setTextSize(1);
    display_.display();
  }
  return available_;
}

bool OledDisplay::respondsAt(TwoWire &wire, uint8_t address) {
  wire.beginTransmission(address);
  return wire.endTransmission() == 0;
}

void OledDisplay::beginFrame(const String &title) {
  display_.clearDisplay();
  display_.setTextColor(SSD1306_WHITE);
  display_.setTextSize(1);
  display_.setCursor(0, 0);
  display_.println(title);
}

void OledDisplay::printValueOrDash(float value, uint8_t decimals) {
  if (isnan(value)) display_.print("--");
  else display_.print(value, decimals);
}

void OledDisplay::showBoot(const String &mode, const String &message) {
  if (!available_) return;
  beginFrame("MoldSense OLED");
  display_.print("Mode: "); display_.println(mode);
  display_.println(message);
  display_.display();
}

void OledDisplay::update(DeviceMode mode, const BsecMode &bsec, const CaptureMode &capture) {
  if (!available_ || millis() - lastRefreshMs_ < MoldSenseConfig::OLED_REFRESH_MS) return;
  lastRefreshMs_ = millis();

  if (mode == DeviceMode::CAPTURE) {
    beginFrame("CAPTURE");
    display_.print(capture.active() ? "REC " : "READY ");
    display_.print("rows:"); display_.println(capture.rows());
    display_.print("cycles:"); display_.println(capture.cycles());
    display_.print("T:"); printValueOrDash(capture.temperature()); display_.print("C ");
    display_.print("RH:"); printValueOrDash(capture.humidity()); display_.println('%');
    display_.print("Gas:");
    if (isnan(capture.gas())) display_.println("--");
    else { display_.print(capture.gas() / 1000.0f, 1); display_.println("k"); }
  } else if (mode == DeviceMode::TEST) {
    beginFrame("TEST  BSEC3");
    display_.print("T:"); printValueOrDash(bsec.temperature()); display_.print("C ");
    display_.print("RH:"); printValueOrDash(bsec.humidity()); display_.println('%');
    display_.print("C1:"); printValueOrDash(bsec.classProbability(0) * 100.0f, 0);
    display_.print("% C2:"); printValueOrDash(bsec.classProbability(1) * 100.0f, 0); display_.println('%');
    display_.print("C3:"); printValueOrDash(bsec.classProbability(2) * 100.0f, 0);
    display_.print("% C4:"); printValueOrDash(bsec.classProbability(3) * 100.0f, 0); display_.println('%');
    display_.print("Model acc:"); display_.println(bsec.modelAccuracy());
  } else {
    beginFrame("LOG  BSEC3");
    display_.print("T:"); printValueOrDash(bsec.temperature()); display_.print("C ");
    display_.print("RH:"); printValueOrDash(bsec.humidity()); display_.println('%');
    display_.print("IAQ:"); printValueOrDash(bsec.iaq(), 0);
    display_.print(" Acc:"); display_.println(bsec.iaqAccuracy());
    display_.print("Gas:");
    if (isnan(bsec.gas())) display_.println("--");
    else { display_.print(bsec.gas() / 1000.0f, 1); display_.println("kOhm"); }
  }
  display_.display();
}
