"""NDJSON framing and sequence validation, independent of transport and UI."""

from dataclasses import dataclass
import json
import math

PROTOCOL_VERSION = 1
MAX_LINE = 16384
MESSAGE_TYPES = {
    "reading",
    "status",
    "device_info",
    "baseline_info",
    "calibration_progress",
    "calibration_complete",
    "model_info",
    "warning",
    "error",
    "command_ack",
    "log_chunk",
    "log_complete",
}
NUMERIC_FIELDS = {
    "temperature_c",
    "raw_temperature_c",
    "humidity_percent",
    "raw_humidity_percent",
    "pressure_pa",
    "gas_resistance_ohms",
    "wall_cap_raw",
    "wall_cap_filtered",
    "wall_moisture_index",
    "wall_baseline",
    "wall_deviation",
    "iaq",
    "static_iaq",
    "iaq_accuracy",
    "stabilization_status",
    "run_in_status",
    "dew_point_c",
    "mold_probability",
    "confidence",
    "gas_observation_id",
    "gas_heater_index",
    "air_sample_uptime_ms",
    "wall_sample_uptime_ms",
    "baseline_id",
    "environment_risk",
    "condensation_risk",
    "voc_mold_probability",
    "environment_contribution",
    "wall_contribution",
    "condensation_contribution",
    "voc_contribution",
    "sample_interval_ms",
}


@dataclass
class Frame:
    raw: str
    message: dict | None
    error: str | None = None


class Parser:
    def __init__(self):
        self.buffer = bytearray()
        self.discarding = False

    def feed(self, data):
        frames = []
        for byte in data:
            if byte == 10:
                if self.discarding:
                    frames.append(
                        Frame(
                            self.buffer.decode("utf-8", errors="replace"),
                            None,
                            "OVERSIZE_FRAME_TRUNCATED",
                        )
                    )
                elif self.buffer:
                    frames.append(
                        parse_line(
                            self.buffer.rstrip(b"\r").decode("utf-8", errors="replace")
                        )
                    )
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                if len(self.buffer) >= MAX_LINE:
                    self.discarding = True
                else:
                    self.buffer.append(byte)
        return frames


def parse_line(raw):
    try:
        message = json.loads(
            raw,
            parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError("nonfinite JSON literal")
            ),
        )
        if not isinstance(message, dict):
            raise ValueError("object required")
        if type(message.get("protocol_version")) is not int or message["protocol_version"] != PROTOCOL_VERSION:
            raise ValueError("PROTOCOL_MISMATCH")
        if message.get("type") not in MESSAGE_TYPES:
            raise ValueError("unknown message type")
        for key in ("device_id", "firmware_version", "boot_id"):
            if (
                not isinstance(message.get(key), str)
                or not 1 <= len(message[key]) <= 128
            ):
                raise ValueError("missing/invalid " + key)
        for key in ("sequence", "uptime_ms"):
            if type(message.get(key)) is not int or not 0 <= message[key] <= 2**63 - 1:
                raise ValueError("missing/invalid " + key)
        if message["type"] == "reading":
            for key in NUMERIC_FIELDS:
                value = message.get(key)
                if value is not None and (
                    type(value) not in (int, float) or not math.isfinite(value)
                ):
                    raise ValueError("invalid numeric " + key)
        if message["type"] == "log_chunk":
            for key in ("offset", "crc32"):
                if (
                    type(message.get(key)) is not int
                    or not 0 <= message[key] <= 2**32 - 1
                ):
                    raise ValueError("invalid log " + key)
            data = message.get("hex")
            if not isinstance(data, str) or len(data) > 128 or len(data) % 2:
                raise ValueError("invalid log hex")
            bytes.fromhex(data)
        if message["type"] == "log_complete":
            for key in ("bytes", "expected_bytes"):
                if (
                    type(message.get(key)) is not int
                    or not 0 <= message[key] <= 2**32 - 1
                ):
                    raise ValueError("invalid log length")
        return Frame(raw, message)
    except (ValueError, TypeError, RecursionError, OverflowError) as error:
        return Frame(raw, None, str(error))


def compatible(info):
    return (
        info.get("type") == "device_info"
        and info.get("product") == "MoldSense"
        and info.get("protocol_version") == 1
        and str(info.get("firmware_version", "")).split(".")[0] == "1"
    )


class SequenceTracker:
    def __init__(self):
        self.last = {}
        self.lost = 0
        self.duplicates = 0

    def observe(self, packet):
        key = (packet["device_id"], packet["boot_id"])
        seq = packet["sequence"]
        prev = self.last.get(key)
        if prev is not None and seq <= prev:
            self.duplicates += 1
            return "DUPLICATE_OR_OUT_OF_ORDER", 0
        gap = max(0, seq - prev - 1) if prev is not None else 0
        self.last[key] = seq
        self.lost += gap
        return ("SEQUENCE_GAP" if gap else "OK"), gap
