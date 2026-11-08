"""One serial owner; committed data is independent of plot refresh/pause."""

from collections import deque
import json, queue, threading, time, zlib, hashlib
from .database import utc
from .protocol import Parser, SequenceTracker, compatible


def serial_open(port):
    import serial

    link = serial.Serial()
    link.port = port
    link.baudrate = 115200
    link.timeout = 0.1
    link.write_timeout = 1
    link.dtr = False
    link.rts = False
    link.open()
    return link


def candidates():
    from serial.tools import list_ports

    return [
        p.device
        for p in list_ports.comports()
        if p.vid is not None
        or any(
            t in p.description.lower()
            for t in ("cp210", "ch340", "usb serial", "esp32")
        )
    ]


def identify(port, expected=None, opener=serial_open):
    link = opener(port)
    parser = Parser()
    deadline = time.monotonic() + 4
    info = None
    try:
        link.write(b"@1 PING\n")
        while time.monotonic() < deadline:
            for frame in parser.feed(link.read(4096)):
                if frame.message and compatible(frame.message):
                    info = frame.message
                    if expected and info["device_id"] != expected:
                        raise ValueError("Different device; reconnect refused")
                    return link, info
        raise TimeoutError("No compatible MoldSense protocol-v1 device")
    except Exception:
        link.close()
        raise


class LogTransferError(ValueError):
    """A device-log transfer failed; acquisition itself remains healthy."""


def sample_interval_s(packet):
    value = packet.get("sample_interval_ms")
    if type(value) not in (int, float) or not 1 <= value <= 3_600_000:
        return 1.0
    return value / 1000


class Acquisition:
    def __init__(self, db):
        self.db = db
        self.events = queue.Queue(maxsize=1024)
        self.commands = queue.Queue(maxsize=64)
        self.stop_event = threading.Event()
        self.reconnect_event = threading.Event()
        self.record_started = None
        self.record_elapsed = 0
        self.lock = threading.RLock()
        self.thread = None
        self.session = None
        self.recording = False
        self.info = None
        self.port = None
        self.expected_device = None
        self.latest = {}
        self.health = {}
        self.baseline = {}
        self.model = {}
        self.tracker = SequenceTracker()
        self.request = 1
        self.rolling = {}
        self.wall_windows = {
            k: deque(maxlen=30)
            for k in ("wall_cap_raw", "wall_cap_filtered", "wall_moisture_index")
        }
        self.last_gas = {}
        self.last_baseline = None
        self.connected = False
        self.last_packet = 0
        self.ui_dropped = 0
        self.stored_count = 0
        self.log_handle = None
        self.log_bytes = 0
        self.log_path = None

    def notify(self, kind, payload):
        try:
            self.events.put_nowait((kind, payload))
        except queue.Full:
            self.ui_dropped += 1  # Measurements have already been committed to SQLite.

    def start(self, port=None, device=None):
        if self.thread and self.thread.is_alive():
            return
        self.port = port
        self.expected_device = device
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="MoldSense acquisition"
        )
        self.thread.start()

    def select_device(self, port, device):
        self.port = port
        self.expected_device = device
        self.reconnect_event.set()

    def send(self, command):
        if "\n" in command or "\r" in command:
            raise ValueError("one command per request")
        with self.lock:
            self.request += 1
            request = self.request
        self.commands.put_nowait((request, command))
        return request

    def attach_session(self, session, recording=True):
        with self.lock:
            self.session = session
            self.recording = recording
            self.record_started = time.monotonic() if recording else None
            self.record_elapsed = 0
            self.stored_count = self.db.count(session) if session else 0
            self.rolling.clear()
            self.last_gas.clear()
            [q.clear() for q in self.wall_windows.values()]

    def set_recording(self, active):
        with self.lock:
            if not active and self.recording and self.record_started is not None:
                self.record_elapsed = max(0, time.monotonic() - self.record_started)
            self.recording = active

    def process(self, frame, epoch=None):
        epoch = time.time() if epoch is None else epoch
        received = utc()
        packet = frame.message
        error = frame.error
        with self.lock:
            session = self.session
            recording = self.recording

            def log_error(reason):
                self.db.ingest_batch(
                    session, [(frame.raw, packet, reason, received, epoch)], False
                )
                # Stop appending; the .partial file is kept and never certified.
                if self.log_handle:
                    self.log_handle.close()
                    self.log_handle = None
                raise LogTransferError(reason)

            if packet:
                marker, gap = self.tracker.observe(packet)
                error = None if marker == "OK" else marker
                if gap:
                    self.db.event(
                        session,
                        "SEQUENCE_GAP",
                        {
                            "missing": gap,
                            "boot_id": packet["boot_id"],
                            "sequence": packet["sequence"],
                        },
                    )
                if packet["type"] == "reading":
                    self.latest = dict(packet)
                    self.last_packet = time.monotonic()
                    # Only fresh gas observations enter the desktop rolling mean.
                    key = (
                        packet["boot_id"],
                        packet.get("gas_observation_id"),
                        packet.get("gas_heater_index"),
                    )
                    gas = packet.get("gas_resistance_ohms")
                    heater = packet.get("gas_heater_index", 0)
                    window = self.rolling.setdefault(heater, deque(maxlen=30))
                    if gap or gas is None:
                        window.clear()
                    if (
                        gas is not None
                        and key != self.last_gas.get(heater)
                        and error != "DUPLICATE_OR_OUT_OF_ORDER"
                    ):
                        window.append(gas)
                        self.last_gas[heater] = key
                    packet = dict(packet)
                    packet["gas_rolling_mean"] = (
                        sum(window) / len(window) if window else None
                    )
                    if gap or packet.get("baseline_id") != self.last_baseline:
                        for q in self.wall_windows.values():
                            q.clear()
                    self.last_baseline = packet.get("baseline_id")
                    for field, derived in (
                        ("wall_cap_raw", "wall_raw_rolling_mean"),
                        ("wall_cap_filtered", "wall_rolling_mean"),
                        ("wall_moisture_index", "wall_index_rolling_mean"),
                    ):
                        q = self.wall_windows[field]
                        value = packet.get(field)
                        if value is None:
                            q.clear()
                        elif error != "DUPLICATE_OR_OUT_OF_ORDER":
                            q.append(value)
                        packet[derived] = sum(q) / len(q) if q else None
                    packet["gas_deviation"] = (
                        gas - packet["gas_rolling_mean"]
                        if gas is not None and packet["gas_rolling_mean"] is not None
                        else None
                    )
                elif packet["type"] == "status":
                    self.health = packet
                elif packet["type"] == "device_info":
                    self.info = packet
                    self.db.device(packet)
                elif packet["type"] in ("baseline_info", "calibration_complete"):
                    self.baseline = packet
                elif packet["type"] == "model_info":
                    self.model = packet
                elif packet["type"] == "log_chunk":
                    data = bytes.fromhex(packet.get("hex", ""))
                    if zlib.crc32(data) != packet.get("crc32"):
                        log_error("Log chunk checksum mismatch")
                    if packet.get("offset") == 0:
                        if self.log_handle:
                            self.log_handle.close()
                        directory = self.db.root / "device_logs"
                        directory.mkdir(exist_ok=True)
                        self.log_path = directory / (
                            str(time.time_ns()) + ".csv.partial"
                        )
                        self.log_handle = self.log_path.open("wb")
                        self.log_bytes = 0
                    if not self.log_handle or packet.get("offset") != self.log_bytes:
                        log_error(
                            "Missing/out-of-order log chunk; partial download retained"
                        )
                    self.log_handle.write(data)
                    self.log_bytes += len(data)
                elif packet["type"] == "log_complete":
                    if (
                        packet.get("bytes") == 0
                        and packet.get("expected_bytes") == 0
                        and not self.log_handle
                    ):
                        directory = self.db.root / "device_logs"
                        directory.mkdir(exist_ok=True)
                        self.log_path = directory / (
                            str(time.time_ns()) + ".csv.partial"
                        )
                        self.log_handle = self.log_path.open("wb")
                        self.log_bytes = 0
                    if (
                        not self.log_handle
                        or packet.get("bytes") != self.log_bytes
                        or packet.get("expected_bytes") != self.log_bytes
                    ):
                        log_error("Incomplete log download")
                    self.log_handle.flush()
                    self.log_handle.close()
                    self.log_handle = None
                    final = self.log_path.with_suffix("")
                    self.log_path.replace(final)
                    packet = {
                        **packet,
                        "desktop_file": str(final),
                        "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
                    }
                    final.with_suffix(".csv.metadata.json").write_text(
                        json.dumps(packet, indent=2), encoding="utf-8"
                    )
            # Each receive batch transaction is durable before UI events are emitted.
            inserted = self.db.ingest_batch(
                session, [(frame.raw, packet, error, received, epoch)], recording
            )
            self.stored_count += len(inserted)
        if packet:
            self.notify(packet["type"], packet)
        elif error:
            self.notify("protocol_error", {"reason": error, "raw": frame.raw[:200]})

    def _run(self):
        link = None
        pending = {}
        retry = 0
        while not self.stop_event.is_set():
            try:
                if self.reconnect_event.is_set():
                    self.reconnect_event.clear()
                    if link:
                        link.close()
                        link = None
                        self.db.event(
                            self.session,
                            "DISCONNECTED",
                            {"reason": "Operator selected another port"},
                        )
                    self.connected = False
                    pending.clear()
                    while not self.commands.empty():
                        try:
                            request, command = self.commands.get_nowait()
                        except queue.Empty:
                            break
                        self.notify(
                            "command_timeout",
                            {
                                "request_id": request,
                                "command": command,
                                "reason": "Port selection cancelled pending request",
                            },
                        )
                    retry = 0
                if link is None:
                    if time.monotonic() < retry:
                        self.stop_event.wait(0.2)
                        continue
                    found = []
                    ports = [self.port] if self.port else candidates()
                    for port in ports:
                        if self.stop_event.is_set():
                            break
                        try:
                            candidate, info = identify(port, self.expected_device)
                            found.append((port, info))
                            candidate.close()
                        except Exception:
                            continue
                    if len(found) > 1 and not self.expected_device:
                        self.notify("devices", [{"port": p, **i} for p, i in found])
                        retry = time.monotonic() + 5
                        continue
                    if not found:
                        # Selected port can change after reconnect. Search USB ports for SAME ID.
                        if self.expected_device:
                            self.port = None
                        retry = time.monotonic() + 3
                        continue
                    if self.stop_event.is_set():
                        break
                    self.port, info = found[0]
                    link, info = identify(self.port, self.expected_device)
                    if self.stop_event.is_set():
                        link.close()
                        link = None
                        break
                    self.expected_device = info["device_id"]
                    self.info = info
                    self.latest = {}
                    self.health = {}
                    self.baseline = {}
                    self.model = {}
                    self.db.device(info)
                    self.connected = True
                    self.tracker.observe(info)
                    parser = Parser()
                    self.last_packet = time.monotonic()
                    pending.clear()
                    self.db.event(
                        self.session, "CONNECTED", {"port": self.port, "device": info}
                    )
                    self.notify("connected", {"port": self.port, **info})
                    for cmd in ("GET_BASELINE", "MODEL_INFO", "STATUS"):
                        self.send(cmd)
                while not self.commands.empty():
                    request, command = self.commands.get_nowait()
                    link.write(f"@{request} {command}\n".encode("ascii"))
                    pending[request] = (command, time.monotonic() + 5)
                for frame in parser.feed(link.read(4096)):
                    if frame.message:
                        self.last_packet = time.monotonic()
                        if frame.message["device_id"] != self.expected_device:
                            raise ValueError("Device identity changed")
                        if frame.message["type"] == "command_ack":
                            request = frame.message.get("request_id")
                            entry = pending.pop(request, None)
                            if not entry:
                                self.db.event(
                                    self.session, "UNMATCHED_ACK", frame.message
                                )
                    try:
                        self.process(frame)
                    except LogTransferError as error:
                        # Only the download failed; keep the link and live readings.
                        self.notify("protocol_error", {"reason": str(error)})
                for request, (command, deadline) in list(pending.items()):
                    if time.monotonic() > deadline:
                        del pending[request]
                        self.notify(
                            "command_timeout",
                            {"request_id": request, "command": command},
                        )
                        self.db.event(
                            self.session,
                            "COMMAND_TIMEOUT",
                            {"request_id": request, "command": command},
                        )
                interval = sample_interval_s(self.latest)
                if time.monotonic() - self.last_packet > max(15, interval * 3):
                    raise TimeoutError("No packets received")
            except Exception as error:
                if link:
                    try:
                        link.close()
                    except Exception:
                        pass
                link = None
                self.connected = False
                for request, (command, _) in pending.items():
                    self.notify(
                        "command_timeout",
                        {
                            "request_id": request,
                            "command": command,
                            "reason": "Disconnected; outcome unknown",
                        },
                    )
                pending.clear()
                while not self.commands.empty():
                    try:
                        request, command = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    self.notify(
                        "command_timeout",
                        {
                            "request_id": request,
                            "command": command,
                            "reason": "Cancelled on disconnect",
                        },
                    )
                self.rolling.clear()
                self.last_gas.clear()
                [q.clear() for q in self.wall_windows.values()]
                try:
                    self.db.event(self.session, "DISCONNECTED", {"reason": str(error)})
                except Exception:
                    pass
                self.notify("disconnected", str(error))
                retry = time.monotonic() + 3
        if link:
            link.close()
        self.connected = False
        if self.log_handle:
            self.log_handle.close()
            self.log_handle = None

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)
        if self.log_handle and (not self.thread or not self.thread.is_alive()):
            self.log_handle.close()
            self.log_handle = None
