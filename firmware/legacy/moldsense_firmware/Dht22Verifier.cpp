#include "Dht22Verifier.h"

#include "MoldSenseConfig.h"

void Dht22Verifier::begin() {
  pinMode(MoldSenseConfig::DHT22_PIN, INPUT_PULLUP);
  lastAttemptMs_ = millis();
  Serial.print("DHT22 verifier enabled on GPIO ");
  Serial.println(MoldSenseConfig::DHT22_PIN);
}

void Dht22Verifier::loop(float bmeTemperature, float bmeHumidity) {
  if (millis() - lastAttemptMs_ < MoldSenseConfig::DHT22_READ_INTERVAL_MS) return;
  lastAttemptMs_ = millis();

  float temperature = NAN;
  float humidity = NAN;
  if (!readSensor(temperature, humidity)) {
    valid_ = false;
    failedReads_++;
    Serial.println("VERIFY | DHT22=READ_ERROR | check power, GPIO, and pull-up resistor");
    return;
  }

  temperature_ = temperature;
  humidity_ = humidity;
  valid_ = true;
  lastSuccessMs_ = millis();
  successfulReads_++;
  printComparison(bmeTemperature, bmeHumidity);
}

bool Dht22Verifier::readSensor(float &temperature, float &humidity) {
  uint8_t bytes[5]{};
  uint32_t durationUs = 0;

  // DHT22 start signal: pull DATA low for at least 1 ms, then release it.
  pinMode(MoldSenseConfig::DHT22_PIN, OUTPUT);
  digitalWrite(MoldSenseConfig::DHT22_PIN, LOW);
  delayMicroseconds(1100);
  digitalWrite(MoldSenseConfig::DHT22_PIN, HIGH);
  delayMicroseconds(30);
  pinMode(MoldSenseConfig::DHT22_PIN, INPUT_PULLUP);

  noInterrupts();
  bool timingOk =
    measureLevel(HIGH, 120, durationUs) &&
    measureLevel(LOW, 120, durationUs) &&
    measureLevel(HIGH, 120, durationUs);

  for (uint8_t bit = 0; bit < 40 && timingOk; bit++) {
    timingOk = measureLevel(LOW, 100, durationUs) &&
               measureLevel(HIGH, 120, durationUs);
    if (timingOk && durationUs > 50) {
      bytes[bit / 8] |= static_cast<uint8_t>(1U << (7 - (bit % 8)));
    }
  }
  interrupts();

  if (!timingOk) return false;
  if (static_cast<uint8_t>(bytes[0] + bytes[1] + bytes[2] + bytes[3]) != bytes[4]) {
    return false;
  }

  uint16_t rawHumidity = (static_cast<uint16_t>(bytes[0]) << 8) | bytes[1];
  uint16_t rawTemperature =
    (static_cast<uint16_t>(bytes[2] & 0x7F) << 8) | bytes[3];
  humidity = rawHumidity * 0.1f;
  temperature = rawTemperature * 0.1f;
  if (bytes[2] & 0x80) temperature = -temperature;

  return temperature >= -40.0f && temperature <= 80.0f &&
         humidity >= 0.0f && humidity <= 100.0f;
}

bool Dht22Verifier::measureLevel(uint8_t level, uint32_t timeoutUs, uint32_t &durationUs) {
  uint32_t startedUs = micros();
  while (digitalRead(MoldSenseConfig::DHT22_PIN) == level) {
    durationUs = micros() - startedUs;
    if (durationUs > timeoutUs) return false;
  }
  durationUs = micros() - startedUs;
  return true;
}

void Dht22Verifier::printComparison(float bmeTemperature, float bmeHumidity) const {
  Serial.print("VERIFY | BME688 temp=");
  if (isnan(bmeTemperature)) Serial.print("NA");
  else Serial.print(bmeTemperature, 2);
  Serial.print("C rh=");
  if (isnan(bmeHumidity)) Serial.print("NA");
  else Serial.print(bmeHumidity, 2);
  Serial.print("% | DHT22 temp=");
  Serial.print(temperature_, 2);
  Serial.print("C rh=");
  Serial.print(humidity_, 2);
  Serial.print('%');

  if (!isnan(bmeTemperature) && !isnan(bmeHumidity)) {
    float temperatureDelta = temperature_ - bmeTemperature;
    float humidityDelta = humidity_ - bmeHumidity;
    bool temperatureAgrees = fabsf(temperatureDelta) <= MoldSenseConfig::DHT22_TEMP_TOLERANCE_C;
    bool humidityAgrees = fabsf(humidityDelta) <= MoldSenseConfig::DHT22_HUMIDITY_TOLERANCE_PERCENT;
    Serial.print(" | delta_temp="); Serial.print(temperatureDelta, 2); Serial.print('C');
    Serial.print(" delta_rh="); Serial.print(humidityDelta, 2); Serial.print('%');
    Serial.print(" | temp_check="); Serial.print(temperatureAgrees ? "PASS" : "WARN");
    Serial.print(" rh_check="); Serial.print(humidityAgrees ? "PASS" : "WARN");
  } else {
    Serial.print(" | check=WAITING_FOR_BME688");
  }
  Serial.println();
}

void Dht22Verifier::printStatus(float bmeTemperature, float bmeHumidity) const {
  Serial.print("dht22_pin="); Serial.println(MoldSenseConfig::DHT22_PIN);
  Serial.print("dht22_valid="); Serial.println(valid_ ? "YES" : "NO");
  Serial.print("dht22_successful_reads="); Serial.println(successfulReads_);
  Serial.print("dht22_failed_reads="); Serial.println(failedReads_);
  Serial.print("dht22_last_success_ms_ago=");
  if (lastSuccessMs_ == 0) Serial.println("NA");
  else Serial.println(millis() - lastSuccessMs_);
  if (valid_) printComparison(bmeTemperature, bmeHumidity);
}
