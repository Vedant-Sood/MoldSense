#include "../../Config.h"
#include "Console.h"
#include <stdarg.h>
namespace ms {
void Console::print(const char *fmt, ...) {
  if (txRead_ == txUsed_)
    txRead_ = txUsed_ = 0;
  va_list args;
  va_start(args, fmt);
  int n = vsnprintf(tx_ + txUsed_, sizeof(tx_) - txUsed_, fmt, args);
  va_end(args);
  if (n < 0 || size_t(n) >= sizeof(tx_) - txUsed_) {
    ++dropped_;
    return;
  }
  txUsed_ += n;
}
void Console::tick(bool pumpingDump) {
  for (uint8_t n = 0; n < 32 && Serial.available(); n++) {
    char c = Serial.read();
    if (c == '\r')
      continue;
    if (c == '\n') {
      if (!overflow_ && inputUsed_) {
        input_[inputUsed_] = 0;
        if (handler_)
          handler_(input_);
      } else if (overflow_)
        print("ERROR command too long\n");
      inputUsed_ = 0;
      overflow_ = false;
    } else if (c >= 32 && c <= 126) {
      if (inputUsed_ + 1 < sizeof(input_))
        input_[inputUsed_++] = c;
      else
        overflow_ = true;
    }
  }
  if (!pumpingDump && txUsed_ > txRead_) {
    size_t n = std::min(size_t(Serial.availableForWrite()), txUsed_ - txRead_);
    if (n) {
      Serial.write(reinterpret_cast<const uint8_t *>(tx_ + txRead_), n);
      txRead_ += n;
    }
  }
}
} // namespace ms
