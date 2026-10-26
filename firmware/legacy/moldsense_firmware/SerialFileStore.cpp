#include "SerialFileStore.h"

#include <LittleFS.h>
#include <bsec3.h>

#include "MoldSenseConfig.h"

bool SerialFileStore::handle(const String &command) {
  if (command == "FILES") {
    listFiles();
  } else if (command.startsWith("FILE_DUMP ")) {
    dumpHex(command.substring(10));
  } else if (command.startsWith("FILE_READ ")) {
    readText(command.substring(10));
  } else if (command.startsWith("FILE_DELETE ")) {
    String path = command.substring(12);
    path.trim();
    if (!userWritable(path)) Serial.println("FILE_ERROR: protected or invalid path.");
    else Serial.println(LittleFS.remove(path) ? "FILE_DELETED" : "FILE_ERROR: delete failed.");
  } else if (command.startsWith("FILE_UPLOAD_BEGIN ")) {
    beginUpload(command.substring(18));
  } else if (command.startsWith("FILE_UPLOAD_HEX ")) {
    appendHex(command.substring(16));
  } else if (command == "FILE_UPLOAD_END") {
    endUpload();
  } else if (command == "FILE_UPLOAD_ABORT") {
    abortUpload();
  } else {
    return false;
  }
  return true;
}

void SerialFileStore::listFiles() {
  File root = LittleFS.open("/", FILE_READ);
  File file = root.openNextFile();
  Serial.println("-----FILES_BEGIN-----");
  while (file) {
    Serial.print(file.name()); Serial.print(','); Serial.println(file.size());
    file = root.openNextFile();
  }
  Serial.println("-----FILES_END-----");
}

void SerialFileStore::dumpHex(const String &path) {
  File file = LittleFS.open(path, FILE_READ);
  if (!file) {
    Serial.println("FILE_NOT_FOUND");
    return;
  }
  Serial.println("-----FILE_HEX_BEGIN-----");
  uint16_t lineBytes = 0;
  while (file.available()) {
    uint8_t value = file.read();
    if (value < 16) Serial.print('0');
    Serial.print(value, HEX);
    if (++lineBytes == 64) {
      Serial.println();
      lineBytes = 0;
    }
  }
  if (lineBytes) Serial.println();
  Serial.println("-----FILE_HEX_END-----");
  file.close();
}

void SerialFileStore::readText(const String &path) {
  File file = LittleFS.open(path, FILE_READ);
  if (!file) {
    Serial.println("FILE_NOT_FOUND");
    return;
  }
  Serial.println("-----FILE_TEXT_BEGIN-----");
  while (file.available()) Serial.write(file.read());
  Serial.println();
  Serial.println("-----FILE_TEXT_END-----");
  file.close();
}

void SerialFileStore::beginUpload(String arguments) {
  int split = arguments.lastIndexOf(' ');
  if (split <= 1) {
    Serial.println("UPLOAD_ERROR: FILE_UPLOAD_BEGIN /name bytes");
    return;
  }
  String path = arguments.substring(0, split);
  path.trim();
  size_t bytes = strtoul(arguments.substring(split + 1).c_str(), nullptr, 10);
  if (!userWritable(path) || bytes == 0 || bytes > MoldSenseConfig::MAX_UPLOAD_BYTES) {
    Serial.println("UPLOAD_ERROR: invalid path or size.");
    return;
  }
  if (path == MoldSenseConfig::MODEL_FILE && bytes > BSEC_MAX_PROPERTY_BLOB_SIZE) {
    Serial.println("UPLOAD_ERROR: BSEC model is too large.");
    return;
  }
  abortUpload();
  target_ = path;
  temporary_ = path + ".uploading";
  expected_ = bytes;
  written_ = 0;
  LittleFS.remove(temporary_);
  upload_ = LittleFS.open(temporary_, FILE_WRITE);
  if (!upload_) {
    Serial.println("UPLOAD_ERROR: cannot create temporary file.");
    return;
  }
  uploading_ = true;
  Serial.println("UPLOAD_READY");
}

void SerialFileStore::appendHex(String hex) {
  if (!uploading_) {
    Serial.println("UPLOAD_ERROR: no upload active.");
    return;
  }
  hex.trim();
  hex.replace(" ", "");
  if (hex.length() == 0 || hex.length() > 512 || (hex.length() % 2) != 0) {
    Serial.println("UPLOAD_ERROR: chunk must contain 2-512 hex characters.");
    return;
  }
  size_t byteCount = hex.length() / 2;
  if (written_ + byteCount > expected_) {
    Serial.println("UPLOAD_ERROR: declared size exceeded.");
    return;
  }
  uint8_t buffer[256];
  for (size_t i = 0; i < byteCount; i++) {
    int high = hexValue(hex[i * 2]);
    int low = hexValue(hex[i * 2 + 1]);
    if (high < 0 || low < 0) {
      Serial.println("UPLOAD_ERROR: invalid hexadecimal data.");
      return;
    }
    buffer[i] = (high << 4) | low;
  }
  if (upload_.write(buffer, byteCount) != byteCount) {
    Serial.println("UPLOAD_ERROR: flash write failed.");
    return;
  }
  written_ += byteCount;
  Serial.print("UPLOAD_PROGRESS "); Serial.print(written_); Serial.print('/'); Serial.println(expected_);
}

void SerialFileStore::endUpload() {
  if (!uploading_) {
    Serial.println("UPLOAD_ERROR: no upload active.");
    return;
  }
  upload_.close();
  uploading_ = false;
  if (written_ != expected_) {
    LittleFS.remove(temporary_);
    Serial.println("UPLOAD_ERROR: incomplete upload discarded.");
    return;
  }
  if (LittleFS.exists(target_)) LittleFS.remove(target_);
  if (!LittleFS.rename(temporary_, target_)) {
    Serial.println("UPLOAD_ERROR: final rename failed.");
    return;
  }
  Serial.print("UPLOAD_SAVED "); Serial.println(target_);
}

void SerialFileStore::abortUpload() {
  if (uploading_) upload_.close();
  if (temporary_.length()) LittleFS.remove(temporary_);
  uploading_ = false;
}

int SerialFileStore::hexValue(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  return -1;
}

bool SerialFileStore::userWritable(const String &path) {
  if (!path.startsWith("/") || path.indexOf("..") >= 0 || path.indexOf("//") >= 0) return false;
  return path == MoldSenseConfig::MODEL_FILE || path.startsWith("/user_");
}
