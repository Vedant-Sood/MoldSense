"""PC companion for the MoldSense ESP32 serial command interface."""

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
        description = (port.description or "").lower()
        if any(name in description for name in ("cp210", "ch340", "usb serial", "uart", "silicon labs")):
            return port.device
    return ports[0].device if ports else None


def open_serial(port):
    connection = serial.Serial(port, BAUD, timeout=0.3)
    time.sleep(2.0)
    connection.reset_input_buffer()
    return connection


def send_line(connection, command):
    connection.write((command + "\n").encode("utf-8"))
    connection.flush()


def read_lines(connection, duration=2.0):
    deadline = time.monotonic() + duration
    lines = []
    while time.monotonic() < deadline:
        raw = connection.readline()
        if raw:
            line = raw.decode("utf-8", errors="replace").rstrip()
            print(line)
            lines.append(line)
    return lines


def sync_clock(connection):
    send_line(connection, f"CLOCK_SET {int(time.time())}")
    read_lines(connection, 1.0)


def wait_for(connection, expected, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = connection.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        print(line)
        if line == expected:
            return
        if "ERROR" in line:
            raise RuntimeError(line)
    raise TimeoutError(f"Timed out waiting for: {expected}")


def upload(connection, payload, remote_path):
    send_line(connection, f"FILE_UPLOAD_BEGIN {remote_path} {len(payload)}")
    wait_for(connection, "UPLOAD_READY")
    for offset in range(0, len(payload), CHUNK_BYTES):
        chunk = payload[offset:offset + CHUNK_BYTES]
        send_line(connection, "FILE_UPLOAD_HEX " + chunk.hex())
        progress = min(offset + len(chunk), len(payload))
        wait_for(connection, f"UPLOAD_PROGRESS {progress}/{len(payload)}")
    send_line(connection, "FILE_UPLOAD_END")
    wait_for(connection, f"UPLOAD_SAVED {remote_path}")


def download(connection, remote_path, local_path):
    send_line(connection, f"FILE_DUMP {remote_path}")
    collecting = False
    chunks = []
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        raw = connection.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="ignore").strip()
        if line == "-----FILE_HEX_BEGIN-----":
            collecting = True
        elif line == "-----FILE_HEX_END-----":
            local_path.write_bytes(bytes.fromhex("".join(chunks)))
            print(f"Saved {local_path} ({local_path.stat().st_size} bytes)")
            return
        elif line == "FILE_NOT_FOUND":
            raise FileNotFoundError(remote_path)
        elif collecting:
            chunks.append(line)
    raise TimeoutError("Download did not finish")


def extract_bsec_array(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    # AI-Studio exports have used both hexadecimal and decimal uint8_t array
    # initializers. Parse the initializer itself so unrelated numbers in the
    # C source (such as the declared array length) are never included.
    match = re.search(
        r"(?:const\s+)?uint8_t\s+\w+\s*\[\s*\d*\s*\]\s*=\s*\{(.*?)\}\s*;",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("No uint8_t configuration array found in the AI-Studio export")

    initializer = re.sub(r"/\*.*?\*/|//[^\r\n]*", "", match.group(1), flags=re.DOTALL)
    values = []
    for token in initializer.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token, 0)
        if not 0 <= value <= 255:
            raise ValueError(f"Configuration byte is outside uint8_t range: {value}")
        values.append(value)

    if not values:
        raise ValueError("The AI-Studio configuration array is empty")
    return bytes(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial port such as COM3")
    sub = parser.add_subparsers(dest="action", required=True)

    command_parser = sub.add_parser("command")
    command_parser.add_argument("text", nargs="+")

    mode_parser = sub.add_parser("mode")
    mode_parser.add_argument("name", choices=("LOG", "CAPTURE", "TEST"))

    start_parser = sub.add_parser("capture-start")
    start_parser.add_argument("label")
    sub.add_parser("capture-stop")
    sub.add_parser("status")
    sub.add_parser("files")
    sub.add_parser("clock-sync")

    upload_parser = sub.add_parser("upload")
    upload_parser.add_argument("local", type=Path)
    upload_parser.add_argument("remote")

    download_parser = sub.add_parser("download")
    download_parser.add_argument("remote")
    download_parser.add_argument("local", type=Path)

    model_parser = sub.add_parser("model-upload")
    model_parser.add_argument("ai_studio_c_file", type=Path)

    args = parser.parse_args()
    port = args.port or find_port()
    if not port:
        raise SystemExit("No serial device found; pass --port COM3 explicitly")

    with open_serial(port) as connection:
        if args.action == "clock-sync":
            sync_clock(connection)
        elif args.action == "command":
            send_line(connection, " ".join(args.text))
            read_lines(connection, 3.0)
        elif args.action == "mode":
            sync_clock(connection)
            send_line(connection, f"MODE {args.name}")
            read_lines(connection, 3.0)
        elif args.action == "capture-start":
            sync_clock(connection)
            send_line(connection, f"CAPTURE_START {args.label}")
            read_lines(connection, 3.0)
        elif args.action == "capture-stop":
            send_line(connection, "CAPTURE_STOP")
            read_lines(connection, 10.0)
        elif args.action == "status":
            send_line(connection, "STATUS")
            read_lines(connection, 3.0)
        elif args.action == "files":
            send_line(connection, "FILES")
            read_lines(connection, 3.0)
        elif args.action == "upload":
            upload(connection, args.local.read_bytes(), args.remote)
        elif args.action == "download":
            download(connection, args.remote, args.local)
        elif args.action == "model-upload":
            payload = extract_bsec_array(args.ai_studio_c_file)
            print(f"Extracted {len(payload)} BSEC configuration bytes")
            upload(connection, payload, "/bsec_model.bin")
            print("Model stored. Run: moldsense_cli.py mode TEST")


if __name__ == "__main__":
    main()
