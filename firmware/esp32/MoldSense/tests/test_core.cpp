#include "../src/Analysis/MoldRiskEngine.h"
#include "../src/Analysis/MoldVOCClassifier.h"
#include "../src/Sensors/WallMoisture.h"
#include "../src/Calibration/BaselineManager.h"
#include "../src/Storage/StorageManager.h"
#include "../src/Core/Switches.h"
#include <cstdio>
#include <fstream>
#include "../src/UI/ResearchProtocol.h"
#include <cstdlib>
#include <cstring>
using namespace ms;
static int checks = 0;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    ++checks;                                                                                      \
    if (!(x)) {                                                                                    \
      std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x);                                    \
      std::exit(1);                                                                                \
    }                                                                                              \
  } while (0)
AirReading air(float rh = 50) {
  AirReading a;
  a.valid = true;
  a.temperature = 25;
  a.humidity = rh;
  a.pressure = 101325;
  return a;
}
WallReading wallInput(float value = 0) {
  WallReading w;
  w.valid = w.baselineValid = true;
  w.index = value;
  w.confidence = 90;
  return w;
}
Baseline base() {
  Baseline b;
  b.setupId = wallIdentity();
  b.mean = b.median = 100;
  b.stddev = .2;
  b.count = b.total = 120;
  b.confidence = 100;
  b.temperature = 25;
  b.humidity = 50;
  return b;
}
RiskResult step(MoldRiskEngine &e, AirReading &a, WallReading &w, uint32_t t,
                const SurfaceReading &s = {}, const VocResult &v = {}) {
  a.sampleMs = w.sampleMs = t;
  return e.update(a, w, s, v, t);
}
int main() {
  CHECK(fabsf(dewPoint(25, 60) - 16.70f) < .1f);
  CHECK(!ms::finite(dewPoint(25, 0)));
  CHECK(surfaceRH(25, 50, 10) == 100);
  CHECK(elapsed(30, 0xfffffff0, 40));
  CHECK(!elapsed(30, 0xfffffff0, 50));
  DebouncedSwitch sw;
  sw.begin(25, false, 0);
  CHECK(!sw.update(true, 1));
  CHECK(!sw.update(false, 20));
  CHECK(!sw.update(true, 40));
  CHECK(!sw.update(true, 90));
  CHECK(sw.update(true, 101));
  CHECK(sw.active());
  MoldRiskEngine dry;
  auto a = air();
  auto w = wallInput();
  auto r = step(dry, a, w, 0);
  CHECK(r.valid && r.probability == 0 && r.level == RiskLevel::Low);
  CHECK(r.confidence < 100);
  CHECK(!ms::finite(r.condensation));
  float initial = r.probability;
  a.gasOhms = 1;
  r = step(dry, a, w, 1000);
  CHECK(r.probability == initial);
  a.gasOhms = 10000000;
  r = step(dry, a, w, 2000);
  CHECK(r.probability == initial);
  MoldRiskEngine wet;
  auto aw = air();
  auto ww = wallInput(100);
  r = step(wet, aw, ww, 0);
  CHECK(r.probability > 25 && r.level != RiskLevel::Critical);
  MoldRiskEngine humid;
  auto ah = air(95);
  auto wh = wallInput();
  float spike = 0;
  for (uint32_t i = 0; i <= 30; i++)
    spike = step(humid, ah, wh, i * 1000).probability;
  CHECK(spike < 25);
  for (uint32_t i = 31; i <= 48 * 3600; i++)
    r = step(humid, ah, wh, i * 1000);
  CHECK(r.probability > spike + 20);
  CHECK(r.level != RiskLevel::Critical);
  MoldRiskEngine persistent;
  auto ap = air(95);
  auto wp = wallInput(100);
  for (uint32_t i = 0; i <= 48 * 3600; i++)
    r = step(persistent, ap, wp, i * 1000);
  CHECK(r.probability >= 75 && r.level == RiskLevel::Critical);
  CHECK(r.wallHours > 47.8 && r.rhHours > 47.8);
  float sum = 0;
  for (auto c : r.contributions)
    sum += c;
  CHECK(fabsf(sum - r.probability) < .001f);
  printf("Persistent damp 48h: index=%.2f confidence=%.1f risk=%s\n", r.probability, r.confidence,
         riskName(r.level));
  auto missingAir = AirReading{};
  auto missingWall = WallReading{};
  r = persistent.update(missingAir, missingWall, {}, VocResult{}, 172801000);
  CHECK(!r.valid && !ms::finite(r.probability) && r.level == RiskLevel::Unknown &&
        r.confidence == 0);
  persistent.newSite();
  r = step(persistent, ap, wp, 200000000);
  CHECK(r.wallHours == 0 && r.level != RiskLevel::Critical);
  MoldRiskEngine wrap;
  uint32_t t = 0xfffff000;
  auto ax = air(90);
  auto wx = wallInput(50);
  for (int i = 0; i < 12; i++)
    r = step(wrap, ax, wx, t + uint32_t(i * 1000));
  CHECK(r.rhHours > .002f && r.rhHours < .004f);
  float before = r.rhHours;
  r = step(wrap, ax, wx, t + 1000000);
  CHECK(r.rhHours == before);
  r = wrap.update(ax, wx, {}, VocResult{}, t + 1001000, false);
  CHECK(r.rhHours == before && !r.valid);
  MoldRiskEngine cond;
  SurfaceReading surface;
  surface.valid = true;
  surface.temperature = 20;
  auto ac = air(70);
  auto wc = wallInput();
  step(cond, ac, wc, 0, surface);
  surface.temperature = 10;
  r = step(cond, ac, wc, 1000, surface);
  CHECK(r.condensationEvents == 1 && r.surfaceRh == 100);
  r = step(cond, ac, wc, 2000, surface);
  CHECK(r.condensationEvents == 1);
  CHECK(r.level != RiskLevel::Critical);
  MoldVOCClassifier classifier;
  ModelMetadata m;
  auto av = air();
  av.gasValid = true;
  av.gasAccuracy = 3;
  av.classes[0] = .2;
  av.classes[1] = .8;
  auto v = classifier.evaluate(av, m, true, 0);
  CHECK(!v.valid && !ms::finite(v.probability));
  m.installed = true;
  m.classCount = 2;
  m.moldClass = 1;
  m.validationQuality = .9;
  CHECK(!classifier.evaluate(av, m, true, 0).valid);
  m.validated = true;
  v = classifier.evaluate(av, m, true, 0);
  CHECK(v.valid && v.probability == .8f && v.confidence == 90);
  CHECK(!classifier.evaluate(av, m, false, 0).valid);
  CHECK(!classifier.evaluate(av, m, true, 50000).valid);
  av.classes[0] = .9;
  CHECK(!classifier.evaluate(av, m, true, 0).valid);
  av.classes[0] = NAN;
  CHECK(!classifier.evaluate(av, m, true, 0).valid);
  av.classes[0] = .2;
  av.gasAccuracy = 0;
  CHECK(!classifier.evaluate(av, m, true, 0).valid);
  WallMoisture filter;
  auto b = base();
  for (uint32_t i = 0; i < 100; i++)
    filter.ingest(100, i * 100, &b);
  CHECK(filter.reading().valid && filter.reading().index == 0);
  filter.ingest(2.1f, 10000, &b);
  CHECK(filter.reading().valid && filter.reading().index < 1);
  for (uint32_t i = 0; i < 100; i++)
    filter.ingest(65, 10100 + i * 100, &b);
  CHECK(filter.reading().index > 99);
  filter.ingest(0, 21000, &b);
  CHECK(!filter.reading().valid && !ms::finite(filter.reading().index));
  for (uint32_t i = 0; i < 8; i++)
    filter.ingest(100, 22000 + i * 100, &b);
  CHECK(filter.reading().valid && filter.reading().index == 0);
  filter.ingest(100, 23000, nullptr);
  CHECK(filter.reading().valid && !filter.reading().baselineValid &&
        !ms::finite(filter.reading().index));
  BaselineManager cal;
  CHECK(cal.start(0));
  auto ca = air();
  WallReading cw;
  cw.valid = true;
  for (uint32_t t = 500; t <= 60000; t += 500) {
    ca.sampleMs = cw.sampleMs = t;
    cw.filtered = t == 10000 ? 500 : 100 + float(int(t / 500) % 3 - 1) * .1f;
    cal.tick(t, cw, ca);
  }
  Baseline result;
  CHECK(cal.takeResult(result));
  CHECK(result.count >= 96 && result.count < 120);
  CHECK(fabsf(result.mean - 100) < .05);
  CHECK(result.stddev < .2);
  CHECK(result.confidence > 90);
  CHECK(cal.start(0));
  for (uint32_t t = 500; t <= 60000; t += 500) {
    ca.sampleMs = cw.sampleMs = t;
    cw.filtered = 100 + t * .005f;
    cal.tick(t, cw, ca);
  }
  CHECK(!cal.takeResult(result));
  CHECK(cal.start(0));
  ca.valid = false;
  for (uint32_t t = 500; t <= 60000; t += 500)
    cal.tick(t, cw, ca);
  CHECK(!cal.takeResult(result));
  Record record;
  record.identity = 123;
  record.length = 3;
  memcpy(record.payload, "abc", 3);
  record.crc = crc32(&record, offsetof(Record, crc));
  CHECK(recordValid(record, 123, 3));
  CHECK(!recordValid(record, 124, 3));
  for (size_t i = 0; i < sizeof(record); i++) {
    Record corrupted = record;
    reinterpret_cast<uint8_t *>(&corrupted)[i] ^= 1;
    CHECK(!recordValid(corrupted, 123, 3));
  }
  CHECK(newer(0, UINT32_MAX));
  Preferences::db.clear();
  StorageManager storage;
  CHECK(storage.begin());
  CHECK(!storage.loadWall(result));
  CHECK(storage.saveWall(b));
  CHECK(storage.loadWall(result) && result.median == 100);
  uint8_t blob[255];
  memset(blob, 42, sizeof(blob));
  CHECK(storage.saveBsec(blob, sizeof(blob), 987));
  auto bsecBefore = Preferences::db["ms_bsec_v1"];
  b.median = b.mean = 110;
  CHECK(storage.saveWall(b));
  CHECK(Preferences::db["ms_bsec_v1"] == bsecBefore);
  CHECK(storage.loadWall(result) && result.median == 110);
  // Latest slot b corrupted: previous intact a must be restored.
  Preferences::db["ms_wall_v1"]["b"][30] ^= 1;
  CHECK(storage.loadWall(result) && result.median == 100);
  CHECK(storage.corrupt());
  Preferences::tearWrite = true;
  b.median = b.mean = 120;
  CHECK(!storage.saveWall(b));
  Preferences::tearWrite = false;
  CHECK(storage.loadWall(result) && result.median == 100);
  uint8_t restored[255]{};
  CHECK(storage.loadBsec(restored, sizeof(restored), 987) && !memcmp(blob, restored, sizeof(blob)));
  CHECK(!storage.loadBsec(restored, sizeof(restored), 988));
  LittleFS.files["/other_capture.bin"] = std::make_shared<std::string>("preserve");
  LittleFS.files["/ms_log.csv"] = std::make_shared<std::string>("test\n");
  CHECK(storage.startDump());
  CHECK(!storage.clearLog());
  for (int i = 0; i < 3; i++)
    storage.tick(i);
  CHECK(!storage.dumpActive());
  CHECK(storage.clearLog());
  CHECK(LittleFS.exists("/other_capture.bin"));
  CHECK(!storage.formatLogs());
  LittleFS.files["/ms_log.csv"] = std::make_shared<std::string>("abcdef");
  CHECK(storage.startDump(true));
  CHECK(storage.dumpSize() == 6);
  CHECK(!storage.startDump(false) && storage.structuredDump());
  uint8_t chunk[4];
  CHECK(storage.readDumpChunk(chunk, 4) == 4 && storage.dumpActive());
  CHECK(storage.readDumpChunk(chunk, 4) == 2 && !storage.dumpActive() && !storage.dumpFailed());
  CHECK(storage.startDump(true));
  File::failRead = true;
  CHECK(storage.readDumpChunk(chunk, 4) == 0 && storage.dumpFailed());
  File::failRead = false;
  Serial.output.clear();
  Console console;
  console.begin(nullptr);
  ResearchProtocol protocol;
  protocol.begin(console, 123);
  ViewState view;
  protocol.reading(view, 1, 5000, 1000);
  while (!console.idle())
    console.tick(false);
  CHECK(Serial.output.find("nan") == std::string::npos);
  CHECK(Serial.output.find("null") != std::string::npos);
  view.air = air();
  view.air.gasOhms = 420000;
  view.wall = wallInput(12);
  view.wall.raw = 99;
  view.wall.filtered = 99;
  view.wall.baseline = 100;
  view.baseline = true;
  view.baselineId = 1234;
  protocol.reading(view, 1, 6000, 1000);
  while (!console.idle())
    console.tick(false);
  std::ofstream telemetry("firmware_readings.ndjson");
  telemetry << Serial.output;
  telemetry.close();
  CHECK(Serial.output.find("MOLDSENSE_112233445566") != std::string::npos);
  printf("PASS: %d assertions (science, fusion, timing, classifier, calibration, filter, NVS and "
         "log isolation)\n",
         checks);
  return 0;
}
