"""Back up files exposed by the one-shot firmware's FILE_READ protocol."""

import argparse
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import serial


BEGIN_FILES = b"-----FILES_BEGIN-----"
END_FILES = b"-----FILES_END-----"
BEGIN_FILE = b"-----FILE_BEGIN-----\r\n"
END_FILE = b"\r\n-----FILE_END-----"


def read_until(connection: serial.Serial, marker: bytes, timeout: float = 8.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while marker not in data:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {marker!r}")
        data.extend(connection.read(connection.in_waiting or 1))
    return bytes(data)


def inventory(connection: serial.Serial) -> list[tuple[str, int]]:
    connection.reset_input_buffer()
    connection.write(b"FILES\n")
    connection.flush()
    raw = read_until(connection, END_FILES)
    section = raw.split(BEGIN_FILES, 1)[1].split(END_FILES, 1)[0]
    files = []
    for raw_line in section.splitlines():
        line = raw_line.decode("utf-8", errors="strict").strip()
        if not line:
            continue
        name, size = line.rsplit(",", 1)
        files.append((name.lstrip("/"), int(size)))
    return files


def download(connection: serial.Serial, name: str, expected_size: int) -> bytes:
    connection.reset_input_buffer()
    connection.write(f"FILE_READ /{name}\n".encode("ascii"))
    connection.flush()
    raw = read_until(connection, END_FILE, timeout=20.0)
    payload = raw.split(BEGIN_FILE, 1)[1].split(END_FILE, 1)[0]
    if len(payload) != expected_size:
        raise RuntimeError(
            f"Size mismatch for /{name}: expected {expected_size}, got {len(payload)}"
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "old_data")
    args = parser.parse_args()

    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    destination = args.output / f"esp32_backup_{stamp}"
    destination.mkdir(parents=True, exist_ok=False)

    manifest = {
        "created_local": dt.datetime.now().astimezone().isoformat(),
        "port": args.port,
        "files": [],
    }
    with serial.Serial(args.port, 115200, timeout=0.2) as connection:
        time.sleep(2.0)
        for name, expected_size in inventory(connection):
            payload = download(connection, name, expected_size)
            (destination / name).write_bytes(payload)
            manifest["files"].append(
                {
                    "remote": f"/{name}",
                    "expected_size": expected_size,
                    "actual_size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )

    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"BACKUP_VERIFIED {destination}")
    for item in manifest["files"]:
        print(f"{item['remote']} {item['actual_size']} {item['sha256']}")


if __name__ == "__main__":
    main()
