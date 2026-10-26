import time
from datetime import datetime
import serial
import serial.tools.list_ports

BAUD = 115200
START = "-----BME688_LOG_BEGIN-----"
END = "-----BME688_LOG_END-----"

def find_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        d = (p.description or "").lower()
        if any(x in d for x in ("cp210", "ch340", "usb serial", "uart", "silicon labs")):
            return p.device
    return ports[0].device if ports else None

def main():
    port = find_port()
    if not port:
        raise SystemExit("No ESP32 serial port found.")
    output = f"bme688_log_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with serial.Serial(port, BAUD, timeout=2) as ser:
        time.sleep(2)
        ser.reset_input_buffer()
        ser.write(b"DUMP\n")
        collecting, lines = False, []
        deadline = time.time() + 60
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if line == START:
                collecting = True
            elif line == END:
                break
            elif collecting:
                lines.append(line)
    if not lines:
        raise SystemExit("No log data received.")
    with open(output, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved {len(lines)-1} readings to {output}")

if __name__ == "__main__":
    main()
