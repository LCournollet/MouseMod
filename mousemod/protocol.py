"""Wire format for the ATK/COMPX mouse configuration protocol.

Frames are 16 bytes, sent as output report id 8 on the vendor collection
(usage page 0xFF02, usage 2). See PROTOCOL.md for the derivation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

REPORT_ID = 0x08
FRAME_SIZE = 16
DATA_OFFSET = 5  # payload offset inside a request frame
CRC_BASE = 85


class Command(enum.IntEnum):
    DOWNLOAD_DATA = 1
    DOWNLOAD_DRIVER_STATUS = 2
    GET_WIRELESS_MOUSE_ONLINE = 3
    GET_BATTERY_LEVEL = 4
    SET_WIRELESS_DONGLE_PAIR = 5
    GET_WIRELESS_DONGLE_PAIR_RESULT = 6
    SET_EEPROM = 7
    GET_EEPROM = 8
    RESTORE_FACTORY = 9
    REPORT_MOUSE_STATUS = 10
    ENTER_USB_UPGRADE_MODE = 13
    GET_CURRENT_CONFIG = 14
    SET_CURRENT_CONFIG = 15
    GET_MOUSE_CID_MID = 16
    GET_MOUSE_VERSION = 18
    DONGLE_EXIT_PAIR = 19
    SET_4K_RGB_MODE = 20
    GET_4K_RGB_MODE = 21
    SET_FAR_DISTANCE_MODE = 22
    GET_FAR_DISTANCE_MODE = 23
    SET_DONGLE_LIGHT_MODE = 24
    GET_DONGLE_LIGHT_MODE = 25
    GET_DONGLE_VERSION = 29


class Addr(enum.IntEnum):
    """EEPROM addresses. Scalars are stored as value followed by a check byte."""

    REPORT_RATE = 0
    MAX_DPI = 2
    CURRENT_DPI = 4
    SILENT_HEIGHT = 10  # lift-off distance
    DPI1 = 12
    DPI3 = 20
    DPI5 = 28
    DPI7 = 36
    DPI1_COLOR = 44
    DPI3_COLOR = 52
    DPI5_COLOR = 60
    DPI7_COLOR = 68
    DPI_RGB_EFFECTS = 76
    DPI_RGB_BRIGHTNESS = 78
    DPI_RGB_SPEED = 80
    DPI_RGB_ENABLE = 82
    KEY0 = 96
    KEY1 = 100
    KEY2 = 104
    KEY3 = 108
    KEY4 = 112
    KEY5 = 116
    DECORATION_LIGHT = 160
    STABILIZATION_TIME = 169  # debounce
    MOTION_SYNC = 171
    CLOSE_LED_TIME = 173  # sleep timer, stored in units of 10 s
    LINEAR_CORRECTION = 175
    RIPPLE_CONTROL = 177
    MOVE_CLOSE_LIGHTS = 179
    SENSOR_ENABLE = 181
    SENSOR_TIME = 183
    SENSOR_MODE = 185
    RF_TX_TIME = 187
    ANGLE = 189
    ROLLING_DELAY = 227


# --- keyboard shortcuts -------------------------------------------------------

#: Per-button combination-key storage, one 32-byte record per physical button.
SHORTCUT_BASE = 256
SHORTCUT_STRIDE = 32
SHORTCUT_ADDRESSES = [SHORTCUT_BASE + SHORTCUT_STRIDE * i for i in range(6)]

#: Six 3-byte entries at most, i.e. three keys held then released.
SHORTCUT_ENTRY_SIZE = 3
SHORTCUT_MAX_ENTRIES = 6
SHORTCUT_MAX_KEYS = SHORTCUT_MAX_ENTRIES // 2
SHORTCUT_PAGE_SIZE = 10
#: Page 0 holds the count in byte 0, so only 9 payload bytes fit there.
SHORTCUT_FIRST_PAGE_PAYLOAD = 9


# --- macros -------------------------------------------------------------------

#: The 16 on-device macro slots, 384 bytes apart.
MACRO_BASE = 768
MACRO_STRIDE = 384
MACRO_SLOTS = 16
MACRO_ADDRESSES = [MACRO_BASE + MACRO_STRIDE * i for i in range(MACRO_SLOTS)]

#: Fixed 31-byte preamble each slot starts with, then the action count.
MACRO_HEADER = bytes([8] + [2] * 8 + [255] * 22)
MACRO_COUNT_OFFSET = len(MACRO_HEADER)
MACRO_DATA_OFFSET = MACRO_COUNT_OFFSET + 1
MACRO_ACTION_SIZE = 5
MACRO_PAGE_SIZE = 10
MACRO_MAX_ACTIONS = 70


class MacroKeyType(enum.IntEnum):
    MODIFIER = 0
    KEY = 1
    MEDIA = 2
    POWER = 3
    MOUSE = 4
    MOVE_XY = 5
    WHEEL = 6


class KeyState(enum.IntEnum):
    DOWN = 0
    UP = 1
    SCROLL = 2


#: Flag bits in byte 0 of a macro action.
STATE_DOWN_BIT = 0x80
STATE_UP_BIT = 0x40
KEY_TYPE_MASK = 0x07

#: value2 of a macro button assignment selects how the macro repeats.
MACRO_REPEAT_UNTIL_KEY_RELEASE = 253
MACRO_STOP_IMMEDIATELY = 254
MACRO_REPEAT_UNTIL_ANY_KEY = 255
#: Anything below that is a literal loop count.
MACRO_MAX_LOOPS = 252

def pack_state_type(state: int, key_type: int) -> int:
    """Byte 0 of a macro action or shortcut entry: state flags plus key type."""
    flags = key_type & KEY_TYPE_MASK
    if state == KeyState.DOWN:
        flags |= STATE_DOWN_BIT
    elif state == KeyState.UP:
        flags |= STATE_UP_BIT
    return flags


def unpack_state_type(flags: int) -> tuple[int, int]:
    """Inverse of :func:`pack_state_type`, returning (state, key_type)."""
    if flags & STATE_UP_BIT:
        state = int(KeyState.UP)
    elif flags & STATE_DOWN_BIT:
        state = int(KeyState.DOWN)
    else:
        state = int(KeyState.SCROLL)
    return state, flags & KEY_TYPE_MASK


#: HID modifier usages, in the bit order the firmware expects.
MODIFIER_USAGES = {
    0xE0: 0x01,  # left ctrl
    0xE1: 0x02,  # left shift
    0xE2: 0x04,  # left alt
    0xE3: 0x08,  # left gui
    0xE4: 0x10,  # right ctrl
    0xE5: 0x20,  # right shift
    0xE6: 0x40,  # right alt
    0xE7: 0x80,  # right gui
}


class ReportRate(enum.IntEnum):
    HZ_1000 = 1
    HZ_500 = 2
    HZ_250 = 4
    HZ_125 = 8
    HZ_2000 = 16
    HZ_4000 = 32
    HZ_8000 = 64

    @property
    def hz(self) -> int:
        return _RATE_HZ[self]

    @classmethod
    def from_hz(cls, hz: int) -> "ReportRate":
        for rate, value in _RATE_HZ.items():
            if value == hz:
                return rate
        raise ValueError(f"unsupported report rate: {hz} Hz")


_RATE_HZ = {
    ReportRate.HZ_125: 125,
    ReportRate.HZ_250: 250,
    ReportRate.HZ_500: 500,
    ReportRate.HZ_1000: 1000,
    ReportRate.HZ_2000: 2000,
    ReportRate.HZ_4000: 4000,
    ReportRate.HZ_8000: 8000,
}


class ButtonClass(enum.IntEnum):
    CLOSE = 0
    MOUSE = 1
    DPI = 2
    ROLL_SIDE_TO_SIDE = 3
    FIREPOWER_KEY = 4
    SHORTCUT_KEY = 5
    MACRO = 6
    REPORT_RATE = 7
    CHANDELIERS = 8
    CONFIG_FILE = 9
    DPI_LOCK = 10
    WHEEL = 11


class MouseValue(enum.IntEnum):
    DISABLE = 0
    LEFT = 1
    RIGHT = 2
    MIDDLE = 4
    SIDE1 = 8
    SIDE2 = 16


class DpiValue(enum.IntEnum):
    CYCLE = 1
    PLUS = 2
    MINUS = 3


class WheelValue(enum.IntEnum):
    UP = 1
    DOWN = 2


class RollValue(enum.IntEnum):
    LEFT = 1
    RIGHT = 2


#: Physical buttons in EEPROM order, with their factory assignment.
BUTTONS = ("left", "right", "middle", "side1", "side2", "bottom")

BUTTON_ADDR = {
    "left": Addr.KEY0,
    "right": Addr.KEY1,
    "middle": Addr.KEY2,
    "side1": Addr.KEY3,
    "side2": Addr.KEY4,
    "bottom": Addr.KEY5,
}

BUTTON_DEFAULTS = {
    "left": (ButtonClass.MOUSE, MouseValue.LEFT, 0),
    "right": (ButtonClass.MOUSE, MouseValue.RIGHT, 0),
    "middle": (ButtonClass.MOUSE, MouseValue.MIDDLE, 0),
    "side1": (ButtonClass.MOUSE, MouseValue.SIDE1, 0),
    "side2": (ButtonClass.MOUSE, MouseValue.SIDE2, 0),
    "bottom": (ButtonClass.DPI, DpiValue.CYCLE, 0),
}


def crc(*values: int) -> int:
    """Check byte used for every stored field: 85 minus the sum, mod 256."""
    return (CRC_BASE - sum(values)) & 0xFF


def build(command: Command, address: int = 0, data: bytes = b"") -> bytes:
    """Build a request frame. ``data`` length becomes dataValidLen."""
    if len(data) > FRAME_SIZE - DATA_OFFSET - 1:
        raise ValueError(f"payload too large: {len(data)} bytes")
    frame = bytearray(FRAME_SIZE)
    frame[0] = int(command)
    frame[1] = 0
    frame[2] = (address >> 8) & 0xFF
    frame[3] = address & 0xFF
    frame[4] = len(data)
    frame[DATA_OFFSET : DATA_OFFSET + len(data)] = data
    frame[15] = (CRC_BASE - (sum([REPORT_ID]) + sum(frame[:15])) & 0xFF) & 0xFF
    return bytes(frame)


def build_read(address: int, length: int = 10) -> bytes:
    """A GetEEPROM request: dataValidLen states how many bytes to read back."""
    frame = bytearray(FRAME_SIZE)
    frame[0] = int(Command.GET_EEPROM)
    frame[2] = (address >> 8) & 0xFF
    frame[3] = address & 0xFF
    frame[4] = length
    frame[15] = (CRC_BASE - (sum([REPORT_ID]) + sum(frame[:15])) & 0xFF) & 0xFF
    return bytes(frame)


@dataclass(frozen=True)
class Response:
    """A reply frame. hidapi prepends the report id, so fields shift by one."""

    raw: bytes

    @property
    def command(self) -> int:
        return self.raw[1]

    @property
    def status(self) -> int:
        return self.raw[2]

    @property
    def address(self) -> int:
        return (self.raw[3] << 8) | self.raw[4]

    @property
    def length(self) -> int:
        return self.raw[5]

    @property
    def data(self) -> bytes:
        return self.raw[6:16]

    @property
    def ok(self) -> bool:
        return self.status == 0


# --- DPI codec (PAW3950Ultra) -------------------------------------------------

DPI_LOW_MAX = 10_000
DPI_HIGH_MAX = 30_000
DPI_HIGH_BASE = 10_050
DPI_STEP_LOW = 10
DPI_STEP_HIGH = 50
DPI_MAX = 60_000


def _encode_axis(dpi: int) -> tuple[int, int]:
    """Return (raw10bit, flag_bits) where flags are (high_range, doubled)."""
    high = dpi > DPI_LOW_MAX
    if not high:
        raw = dpi // DPI_STEP_LOW - 1
        return raw, 0
    doubled = dpi > DPI_HIGH_MAX
    base = dpi // 2 if doubled else dpi
    raw = (base - DPI_HIGH_BASE) // DPI_STEP_HIGH
    return raw, (0b11 if doubled else 0b10)


def encode_dpi(x_dpi: int, y_dpi: int) -> tuple[int, int, int]:
    """Logical DPI pair -> (xDpi, yDpi, dpiEx) as stored in EEPROM."""
    x_raw, x_flags = _encode_axis(x_dpi)
    y_raw, y_flags = _encode_axis(y_dpi)
    dpi_ex = ((y_raw >> 8) & 0b11) << 6 | ((x_raw >> 8) & 0b11) << 2
    dpi_ex |= x_flags | (y_flags << 4)
    return x_raw & 0xFF, y_raw & 0xFF, dpi_ex & 0xFF


def decode_dpi(x_raw: int, y_raw: int, dpi_ex: int) -> tuple[int, int]:
    """(xDpi, yDpi, dpiEx) -> logical DPI pair."""
    x = x_raw | ((dpi_ex & 0b1100) >> 2) << 8
    y = y_raw | ((dpi_ex & 0b11000000) >> 6) << 8
    x_dpi = DPI_STEP_HIGH * x + DPI_HIGH_BASE if dpi_ex & 0b10 else DPI_STEP_LOW * (x + 1)
    y_dpi = DPI_STEP_HIGH * y + DPI_HIGH_BASE if dpi_ex & 0b100000 else DPI_STEP_LOW * (y + 1)
    if dpi_ex & 0b1:
        x_dpi *= 2
    if dpi_ex & 0b10000:
        y_dpi *= 2
    return x_dpi, y_dpi


def quantize_dpi(dpi: int) -> int:
    """Snap a requested DPI to the nearest value the sensor can actually store."""
    dpi = max(DPI_STEP_LOW, min(DPI_MAX, dpi))
    return decode_dpi(*encode_dpi(dpi, dpi))[0]
