#pragma once

#include <Arduino.h>
#include <FS.h>

class SerialFileStore {
 public:
  bool handle(const String &command);
  void listFiles();
  void dumpHex(const String &path);
  void readText(const String &path);

 private:
  File upload_;
  bool uploading_ = false;
  String target_;
  String temporary_;
  size_t expected_ = 0;
  size_t written_ = 0;

  void beginUpload(String arguments);
  void appendHex(String hex);
  void endUpload();
  void abortUpload();
  static int hexValue(char value);
  static bool userWritable(const String &path);
};
