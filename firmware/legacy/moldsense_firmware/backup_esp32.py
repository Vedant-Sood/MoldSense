#!/usr/bin/env python3
"""Back up every MoldSense LittleFS file and verify sizes and SHA-256 hashes."""

import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import serial


BAUD = 115200


def send_line(connection, line):
    connection.write((line + "\n").encode("ascii"))
    connection.flush()


def read_until(connection, ending, timeout):
    deadline = time.monotonic() + timeout
    lines = []
    while time.monotonic() < deadline:
        raw = connection.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="replace").strip()
        lines.append(line)
        if line == ending:
            return lines
    raise TimeoutError(f"Timed out waiting for {ending}")


def list_files(connection):
    send_line(connection, "FILES")
    lines = read_until(connection, "-----FILES_END-----", 15)
    files = []
    inside = False
    for line in lines:
        if line == "-----FILES_BEGIN-----":
            inside = True
        elif line == "-----FILES_END-----":
            inside = False
        elif inside and "," in line:
            name, size = line.rsplit(",", 1)
            files.append((name.lstrip("/"), int(size)))
    if not files:
        raise RuntimeError("ESP32 returned no files")
    return files


def download(connection, remote_name, destination, expected_size):
    send_line(connection, f"FILE_DUMP /{remote_name}")
    deadline = time.monotonic() + max(120, expected_size / 1500)
    collecting = False
    chunks = []
    while time.monotonic() < deadline:
        raw = connection.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="ignore").strip()
        if line == "-----FILE_HEX_BEGIN-----":
            collecting = True
        elif line == "-----FILE_HEX_END-----":
            payload = bytes.fromhex("".join(chunks))
            destination.write_bytes(payload)
            return payload
        elif line == "FILE_NOT_FOUND":
            raise FileNotFoundError(remote_name)
        elif collecting:
            chunks.append(line)
    raise TimeoutError(f"Download timed out: {remote_name}")


def collect_status(connection):
    sections = []
    for command in ("STATUS", "BSEC_STATUS", "MODEL_INFO", "CLOCK_INFO"):
        send_line(connection, command)
        deadline = time.monotonic() + 2.0
        lines = []
        while time.monotonic() < deadline:
            raw = connection.readline()
            if raw:
                lines.append(raw.decode("utf-8", errors="replace").rstrip())
        sections.append(f"[{command}]\n" + "\n".join(lines))
    return "\n\n".join(sections) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--output", type=Path, default=Path("old_data"))
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = args.output / f"esp32_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    with serial.Serial(args.port, BAUD, timeout=0.3) as connection:
        time.sleep(2.0)
        connection.reset_input_buffer()
        inventory = list_files(connection)
        print(f"Backing up {len(inventory)} files to {backup_dir}")
        manifest = {
            "created_local": datetime.now().astimezone().isoformat(),
            "port": args.port,
            "files": [],
        }
        for index, (name, expected_size) in enumerate(inventory, 1):
            destination = backup_dir / name
            print(f"[{index}/{len(inventory)}] {name} ({expected_size} bytes)")
            payload = download(connection, name, destination, expected_size)
            actual_size = len(payload)
            verified_remote_size = expected_size
            grew_during_backup = False
            if actual_size > expected_size:
                # LOG/TEST can append to CSV files while a backup is running.
                # Re-list the device and accept the download only when the
                # remote file is now at least as large as the complete payload.
                current_inventory = dict(list_files(connection))
                verified_remote_size = current_inventory.get(name, -1)
                grew_during_backup = verified_remote_size >= actual_size
            if actual_size < expected_size or (
                actual_size > expected_size and not grew_during_backup
            ):
                raise RuntimeError(
                    f"Size mismatch for {name}: listed {expected_size}, "
                    f"downloaded {actual_size}, now {verified_remote_size}"
                )
            manifest["files"].append(
                {
                    "remote": f"/{name}",
                    "expected_size": expected_size,
                    "actual_size": actual_size,
                    "verified_remote_size_after": verified_remote_size,
                    "grew_during_backup": grew_during_backup,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        (backup_dir / "device_status.txt").write_text(
            collect_status(connection), encoding="utf-8"
        )

    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"BACKUP_VERIFIED {backup_dir}")


if __name__ == "__main__":
    main()
