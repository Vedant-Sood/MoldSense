"""Upload or download a LittleFS file through the BME688 logger serial protocol.

Examples:
  python transfer_bme688_file.py upload model.bin /bsec_model.bin
  python transfer_bme688_file.py download /bsec_model.bin copied_model.bin

For an AI-Studio export, use the raw byte configuration represented by its
generated C array.  Do not upload a .h or .c source file as the model itself.
"""

import argparse
import re
import time
from pathlib import Path

import serial
import serial.tools.list_ports

BAUD = 115200
CHUNK_BYTES = 96


def find_port():
    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        text = (port.description or "").lower()
        if any(token in text for token in ("cp210", "ch340", "usb serial", "uart", "silicon labs")):
            return port.device
    return ports[0].device if ports else None


def read_until(ser, expected, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if not line:
            continue
        print(line)
        if line == expected or line.startswith("UPLOAD_ERROR") or line.startswith("MODEL_ERROR"):
            return line
    raise TimeoutError(f"Timed out waiting for {expected}")


def upload(ser, source, remote):
    payload = source.read_bytes()
    ser.write(f"FILE_UPLOAD_BEGIN {remote} {len(payload)}\n".encode())
    if read_until(ser, "UPLOAD_READY") != "UPLOAD_READY":
        raise SystemExit("ESP32 rejected the upload.")

    for offset in range(0, len(payload), CHUNK_BYTES):
        chunk = payload[offset: offset + CHUNK_BYTES]
        ser.write(b"FILE_UPLOAD_HEX " + chunk.hex().encode() + b"\n")
        result = read_until(ser, f"UPLOAD_PROGRESS {min(offset + len(chunk), len(payload))}/{len(payload)}")
        if result.startswith("UPLOAD_ERROR"):
            raise SystemExit("Upload failed; temporary data was not activated.")

    ser.write(b"FILE_UPLOAD_END\n")
    result = read_until(ser, f"UPLOAD_SAVED {remote}")
    if result != f"UPLOAD_SAVED {remote}":
        raise SystemExit("ESP32 did not finalize the file.")


def download(ser, remote, destination):
    ser.write(f"FILE_DUMP {remote}\n".encode())
    collecting, chunks = False, []
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if not line:
            continue
        if line == "-----FILE_HEX_BEGIN-----":
            collecting = True
        elif line == "-----FILE_HEX_END-----":
            destination.write_bytes(bytes.fromhex("".join(chunks)))
            print(f"Saved {destination}")
            return
        elif line == "FILE_NOT_FOUND":
            raise SystemExit("Remote file does not exist.")
        elif collecting:
            chunks.append(line)
    raise TimeoutError("Timed out while downloading file")


def c_array_to_binary(source, destination):
    text = source.read_text(encoding="utf-8", errors="ignore")
    values = re.findall(r"0x([0-9a-fA-F]{1,2})", text)
    if not values:
        raise SystemExit("No hexadecimal byte array found in the source file.")
    destination.write_bytes(bytes(int(value, 16) for value in values))
    print(f"Extracted {len(values)} config bytes to {destination}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("upload", "download", "c-array-to-bin"))
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--port", help="ESP32 serial port, for example COM3")
    args = parser.parse_args()

    source, destination = Path(args.source), Path(args.destination)
    if args.action == "c-array-to-bin":
        c_array_to_binary(source, destination)
        return

    port = args.port or find_port()
    if not port:
        raise SystemExit("No ESP32 serial port found.")

    with serial.Serial(port, BAUD, timeout=1) as ser:
        time.sleep(2)  # ESP32 boards commonly reset on serial open.
        ser.reset_input_buffer()
        if args.action == "upload":
            if not source.is_file():
                raise SystemExit(f"Local source file not found: {source}")
            upload(ser, source, args.destination)
        else:
            download(ser, args.source, destination)


if __name__ == "__main__":
    main()
