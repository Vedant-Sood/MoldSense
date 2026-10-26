"""Small COM-port probe for the one-shot BME688 firmware."""

import argparse
import time

import serial


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--include-boot", action="store_true")
    parser.add_argument("commands", nargs="*", default=["STATUS"])
    args = parser.parse_args()

    with serial.Serial(args.port, 115200, timeout=0.2) as connection:
        time.sleep(2.0)
        received = bytearray()
        if args.include_boot:
            received.extend(connection.read(connection.in_waiting or 1))
        else:
            connection.reset_input_buffer()
        for command in args.commands:
            connection.write((command + "\n").encode("ascii"))
            connection.flush()
            time.sleep(0.4)

        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            received.extend(connection.read(connection.in_waiting or 1))

    print(received.decode("utf-8", errors="replace"), end="")


if __name__ == "__main__":
    main()
