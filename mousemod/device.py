"""HID discovery and transport for ATK mice.

Two endpoints can carry the config protocol: the mouse itself when it is
plugged in over USB, and the 8K dongle when the mouse is live on RF. Both
expose the same vendor collection, so the transport is identical; only
discovery differs.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import hid

from .protocol import REPORT_ID, Command, Response, build, build_read

ATK_VIDS = (0x373B, 0x3554)
CONFIG_USAGE_PAGE = 0xFF02
CONFIG_USAGE = 0x02

#: Product ids that are receivers rather than mice.
DONGLE_PIDS = {0x1145, 0x1159, 0x1160, 0x1167, 0x1168, 0x1189, 0x11A7, 0x11A8, 0x11B6}

KNOWN_MICE = {
    0x1045: "ATK F1 EXTREME",
    0x104C: "ATK F1 Ultra",
    0x104D: "ATK X1 Ultimate",
    0x103C: "ATK F1 Ultimate",
}


class DeviceError(RuntimeError):
    pass


class NotConnected(DeviceError):
    pass


@dataclass(frozen=True)
class Endpoint:
    path: bytes
    vendor_id: int
    product_id: int
    product: str
    is_dongle: bool

    @property
    def label(self) -> str:
        kind = "dongle" if self.is_dongle else "wired"
        return f"{self.product} ({kind})"


def discover() -> list[Endpoint]:
    """All ATK vendor config endpoints currently attached, mice first."""
    found = []
    for info in hid.enumerate():
        if info["vendor_id"] not in ATK_VIDS:
            continue
        if info["usage_page"] != CONFIG_USAGE_PAGE or info["usage"] != CONFIG_USAGE:
            continue
        pid = info["product_id"]
        product = info.get("product_string") or KNOWN_MICE.get(pid) or f"ATK {pid:04X}"
        is_dongle = pid in DONGLE_PIDS or "dongle" in product.lower()
        found.append(
            Endpoint(
                path=info["path"],
                vendor_id=info["vendor_id"],
                product_id=pid,
                product=product,
                is_dongle=is_dongle,
            )
        )
    found.sort(key=lambda e: e.is_dongle)
    return found


class Mouse:
    """Synchronous request/response channel to one endpoint.

    The device answers on the same collection it is written to. Replies are
    matched on the echoed command id, and unrelated reports (the mouse pushes
    status notifications of its own) are skipped.
    """

    def __init__(self, endpoint: Endpoint, timeout_ms: int = 600, retries: int = 2):
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self.retries = retries
        self._dev: hid.device | None = None
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> "Mouse":
        with self._lock:
            if self._dev is None:
                dev = hid.device()
                try:
                    dev.open_path(self.endpoint.path)
                except OSError as exc:
                    raise NotConnected(f"cannot open {self.endpoint.label}: {exc}") from exc
                self._dev = dev
        return self

    def close(self) -> None:
        with self._lock:
            if self._dev is not None:
                try:
                    self._dev.close()
                finally:
                    self._dev = None

    def __enter__(self) -> "Mouse":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # -- transport ---------------------------------------------------------

    def transfer(self, frame: bytes) -> Response:
        """Send a frame and wait for the matching reply."""
        with self._lock:
            if self._dev is None:
                self.open()
            assert self._dev is not None
            last_error: Exception | None = None
            for _ in range(self.retries + 1):
                try:
                    written = self._dev.write(bytes([REPORT_ID]) + frame)
                    if written <= 0:
                        raise DeviceError("HID write rejected")
                    reply = self._await_reply(frame[0])
                    if reply is not None:
                        return reply
                    last_error = DeviceError(f"no reply to command {frame[0]}")
                except OSError as exc:
                    last_error = exc
                    self.close()
                    self.open()
            raise DeviceError(
                f"{self.endpoint.label}: {last_error or 'transfer failed'}"
            )

    def _await_reply(self, command_id: int) -> Response | None:
        assert self._dev is not None
        deadline = time.monotonic() + self.timeout_ms / 1000
        while time.monotonic() < deadline:
            data = self._dev.read(64, 100)
            if not data or len(data) < 16:
                continue
            if data[1] == command_id:
                return Response(bytes(data))
        return None

    # -- primitives --------------------------------------------------------

    def command(self, cmd: Command, address: int = 0, data: bytes = b"") -> Response:
        return self.transfer(build(cmd, address, data))

    def read_eeprom(self, address: int, length: int = 10) -> bytes:
        reply = self.transfer(build_read(address, length))
        if not reply.ok:
            raise DeviceError(
                f"read at {address} rejected (status {reply.status}); "
                "the mouse may be asleep or offline"
            )
        return reply.data[:length]

    def write_eeprom(self, address: int, data: bytes) -> None:
        reply = self.command(Command.SET_EEPROM, address, data)
        if not reply.ok:
            raise DeviceError(f"write at {address} rejected (status {reply.status})")

    # -- identity ----------------------------------------------------------

    def is_alive(self) -> bool:
        """True when this endpoint can actually reach the mouse right now."""
        try:
            self.read_eeprom(0, 2)
            return True
        except (DeviceError, OSError):
            return False

    def cid_mid(self) -> tuple[int, int]:
        data = self.command(Command.GET_MOUSE_CID_MID).data
        return data[0], data[1]

    def firmware_version(self) -> str:
        data = self.command(Command.GET_MOUSE_VERSION).data
        return f"{data[0]}.{data[1]}"

    def dongle_version(self) -> str | None:
        reply = self.command(Command.GET_DONGLE_VERSION)
        return str(reply.data[0]) if reply.ok else None

    def battery(self) -> dict:
        """Battery level in percent plus the charging flag."""
        data = self.command(Command.GET_BATTERY_LEVEL).data
        return {"percent": data[0], "charging": bool(data[1])}

    def wireless_status(self) -> dict:
        data = self.command(Command.GET_WIRELESS_MOUSE_ONLINE).data
        return {
            "online": data[0] == 1,
            "rf_id": f"{data[1]:02x}-{data[2]:02x}-{data[3]:02x}",
        }

    def restore_factory(self) -> None:
        self.command(Command.RESTORE_FACTORY)


def connect(prefer_wired: bool = True) -> Mouse:
    """Open the best endpoint that can actually talk to the mouse.

    A dongle enumerates whether or not the mouse is awake on RF, and the wired
    interface enumerates whether or not the cable is the active link, so both
    are probed rather than trusted.
    """
    endpoints = discover()
    if not endpoints:
        raise NotConnected("no ATK mouse or dongle found")
    if not prefer_wired:
        endpoints = sorted(endpoints, key=lambda e: not e.is_dongle)

    errors = []
    for endpoint in endpoints:
        mouse = Mouse(endpoint)
        try:
            mouse.open()
            if mouse.is_alive():
                return mouse
            errors.append(f"{endpoint.label}: no response")
        except DeviceError as exc:
            errors.append(str(exc))
        mouse.close()

    raise NotConnected(
        "found ATK hardware but no live mouse: " + "; ".join(errors)
    )
