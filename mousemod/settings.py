"""High-level read/write of every mouse setting MouseMod manages.

Each field is written with the smallest possible EEPROM transaction so that
touching one setting never rewrites its neighbours.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from .device import Mouse
from .macros import Macro, default_macros
from .macros import read_all as read_macros
from .macros import write_all as write_macros
from .shortcuts import ShortcutStep, default_shortcuts
from .shortcuts import read_all as read_shortcuts
from .shortcuts import write_all as write_shortcuts
from .protocol import (
    BUTTON_ADDR,
    BUTTON_DEFAULTS,
    BUTTONS,
    Addr,
    ButtonClass,
    Command,
    ReportRate,
    crc,
    decode_dpi,
    encode_dpi,
    quantize_dpi,
)

#: DPI stages live two per EEPROM record.
DPI_RECORDS = (Addr.DPI1, Addr.DPI3, Addr.DPI5, Addr.DPI7)
MAX_DPI_STAGES = 8


@dataclass
class ButtonAction:
    """What a physical button does: an action class plus up to two operands."""

    action: int = int(ButtonClass.MOUSE)
    value1: int = 0
    value2: int = 0

    def to_bytes(self) -> bytes:
        return bytes(
            [self.action, self.value1, self.value2, crc(self.action, self.value1, self.value2)]
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "ButtonAction":
        return cls(action=data[0], value1=data[1], value2=data[2])

    def describe(self) -> str:
        return describe_action(self)


@dataclass
class Settings:
    """The full managed state of the mouse."""

    report_rate_hz: int = 1000
    dpi_stages: list[int] = field(default_factory=lambda: [400, 800, 1600, 3200])
    active_stage: int = 0
    lod: int = 1
    motion_sync: bool = True
    linear_correction: bool = False
    ripple_control: bool = False
    debounce_ms: int = 0
    sleep_seconds: int = 60
    sensor_angle: int = 0
    buttons: dict[str, ButtonAction] = field(default_factory=dict)
    macros: list[Macro] = field(default_factory=default_macros)
    shortcuts: dict[str, list[ShortcutStep]] = field(default_factory=default_shortcuts)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["buttons"] = {k: asdict(v) for k, v in self.buttons.items()}
        data["macros"] = [m.to_dict() for m in self.macros]
        data["shortcuts"] = {
            k: [asdict(s) for s in v] for k, v in self.shortcuts.items()
        }
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        data = dict(data)
        buttons = data.pop("buttons", {}) or {}
        macros = data.pop("macros", None)
        shortcuts = data.pop("shortcuts", None)
        skip = ("buttons", "macros", "shortcuts")
        known = {f for f in cls.__dataclass_fields__ if f not in skip}
        clean = {k: v for k, v in data.items() if k in known}
        result = cls(**clean)
        result.buttons = {k: ButtonAction(**v) for k, v in buttons.items()}
        if macros is not None:
            result.macros = [Macro.from_dict(m) for m in macros]
        if shortcuts is not None:
            result.shortcuts = {
                k: [ShortcutStep(**s) for s in v] for k, v in shortcuts.items()
            }
        return result

    def copy(self) -> "Settings":
        return replace(
            self,
            dpi_stages=list(self.dpi_stages),
            buttons=dict(self.buttons),
            macros=[m.copy() for m in self.macros],
            shortcuts={k: list(v) for k, v in self.shortcuts.items()},
        )


# --- reading ------------------------------------------------------------------


def _scalar(mouse: Mouse, address: int) -> int:
    return mouse.read_eeprom(address, 2)[0]


def read_dpi_stages(mouse: Mouse, count: int) -> list[int]:
    stages: list[int] = []
    for record in DPI_RECORDS:
        if len(stages) >= count:
            break
        data = mouse.read_eeprom(int(record), 8)
        for slot in range(2):
            chunk = data[slot * 4 : slot * 4 + 4]
            stages.append(decode_dpi(chunk[0], chunk[1], chunk[2])[0])
    return stages[:count]


def read_buttons(mouse: Mouse) -> dict[str, ButtonAction]:
    actions = {}
    for name in BUTTONS:
        data = mouse.read_eeprom(int(BUTTON_ADDR[name]), 4)
        actions[name] = ButtonAction.from_bytes(data)
    return actions


def read_settings(mouse: Mouse, include_macros: bool = True) -> Settings:
    """Read the complete live configuration off the device.

    Macros cost roughly one transaction per slot, so callers that only need the
    fast-changing settings can skip them.
    """
    header = mouse.read_eeprom(int(Addr.REPORT_RATE), 6)
    rate_raw, stage_count, active = header[0], header[2], header[4]

    try:
        rate_hz = ReportRate(rate_raw).hz
    except ValueError:
        rate_hz = 1000

    stage_count = max(1, min(MAX_DPI_STAGES, stage_count))
    func = mouse.read_eeprom(int(Addr.STABILIZATION_TIME), 10)

    return Settings(
        report_rate_hz=rate_hz,
        dpi_stages=read_dpi_stages(mouse, stage_count),
        active_stage=min(active, stage_count - 1),
        lod=_scalar(mouse, int(Addr.SILENT_HEIGHT)),
        debounce_ms=func[0],
        motion_sync=bool(func[2]),
        sleep_seconds=func[4] * 10,
        linear_correction=bool(func[6]),
        ripple_control=bool(func[8]),
        sensor_angle=_scalar(mouse, int(Addr.ANGLE)),
        buttons=read_buttons(mouse),
        macros=read_macros(mouse) if include_macros else default_macros(),
        shortcuts=read_shortcuts(mouse),
    )


# --- writing ------------------------------------------------------------------


def _write_scalar(mouse: Mouse, address: int, value: int) -> None:
    value &= 0xFF
    mouse.write_eeprom(address, bytes([value, crc(value)]))


def set_report_rate(mouse: Mouse, hz: int) -> None:
    _write_scalar(mouse, int(Addr.REPORT_RATE), int(ReportRate.from_hz(hz)))


def set_stage_count(mouse: Mouse, count: int) -> None:
    _write_scalar(mouse, int(Addr.MAX_DPI), max(1, min(MAX_DPI_STAGES, count)))


def set_active_stage(mouse: Mouse, index: int) -> None:
    _write_scalar(mouse, int(Addr.CURRENT_DPI), max(0, index))


def set_dpi_stages(mouse: Mouse, stages: list[int]) -> list[int]:
    """Write DPI stages, two per record. Returns the values actually stored."""
    stages = [quantize_dpi(int(v)) for v in stages][:MAX_DPI_STAGES]
    padded = stages + [stages[-1] if stages else 800] * (MAX_DPI_STAGES - len(stages))
    for index, record in enumerate(DPI_RECORDS):
        pair = padded[index * 2 : index * 2 + 2]
        payload = bytearray()
        for value in pair:
            x, y, ex = encode_dpi(value, value)
            payload += bytes([x, y, ex, crc(x, y, ex)])
        mouse.write_eeprom(int(record), bytes(payload))
    set_stage_count(mouse, len(stages))
    return stages


def set_lod(mouse: Mouse, value: int) -> None:
    _write_scalar(mouse, int(Addr.SILENT_HEIGHT), value)


def set_motion_sync(mouse: Mouse, enabled: bool) -> None:
    _write_scalar(mouse, int(Addr.MOTION_SYNC), int(bool(enabled)))


def set_linear_correction(mouse: Mouse, enabled: bool) -> None:
    _write_scalar(mouse, int(Addr.LINEAR_CORRECTION), int(bool(enabled)))


def set_ripple_control(mouse: Mouse, enabled: bool) -> None:
    _write_scalar(mouse, int(Addr.RIPPLE_CONTROL), int(bool(enabled)))


def set_debounce(mouse: Mouse, milliseconds: int) -> None:
    _write_scalar(mouse, int(Addr.STABILIZATION_TIME), max(0, min(255, milliseconds)))


def set_sleep_seconds(mouse: Mouse, seconds: int) -> None:
    _write_scalar(mouse, int(Addr.CLOSE_LED_TIME), max(0, min(255, seconds // 10)))


def set_sensor_angle(mouse: Mouse, angle: int) -> None:
    _write_scalar(mouse, int(Addr.ANGLE), angle & 0xFF)


def set_button(mouse: Mouse, name: str, action: ButtonAction) -> None:
    if name not in BUTTON_ADDR:
        raise KeyError(f"unknown button: {name}")
    mouse.write_eeprom(int(BUTTON_ADDR[name]), action.to_bytes())


def apply_settings(mouse: Mouse, settings: Settings, current: Settings | None = None) -> Settings:
    """Push a configuration to the device.

    When ``current`` is supplied only the differing fields are written, which
    keeps profile switching fast enough to run on window focus changes.
    """
    stored = settings.copy()

    if current is None or settings.dpi_stages != current.dpi_stages:
        stored.dpi_stages = set_dpi_stages(mouse, settings.dpi_stages)
    if current is None or settings.report_rate_hz != current.report_rate_hz:
        set_report_rate(mouse, settings.report_rate_hz)
    if current is None or settings.active_stage != current.active_stage:
        set_active_stage(mouse, settings.active_stage)
    if current is None or settings.lod != current.lod:
        set_lod(mouse, settings.lod)
    if current is None or settings.motion_sync != current.motion_sync:
        set_motion_sync(mouse, settings.motion_sync)
    if current is None or settings.linear_correction != current.linear_correction:
        set_linear_correction(mouse, settings.linear_correction)
    if current is None or settings.ripple_control != current.ripple_control:
        set_ripple_control(mouse, settings.ripple_control)
    if current is None or settings.debounce_ms != current.debounce_ms:
        set_debounce(mouse, settings.debounce_ms)
    if current is None or settings.sleep_seconds != current.sleep_seconds:
        set_sleep_seconds(mouse, settings.sleep_seconds)
    if current is None or settings.sensor_angle != current.sensor_angle:
        set_sensor_angle(mouse, settings.sensor_angle)

    # Macros first: a button pointing at a slot should never run the old
    # contents, however briefly.
    write_macros(mouse, settings.macros, None if current is None else current.macros)
    write_shortcuts(
        mouse, settings.shortcuts, None if current is None else current.shortcuts
    )

    for name, action in settings.buttons.items():
        if current is None or current.buttons.get(name) != action:
            set_button(mouse, name, action)

    return stored


def switch_onboard_profile(mouse: Mouse, index: int) -> None:
    """Select one of the mouse's own onboard configs."""
    mouse.command(Command.SET_CURRENT_CONFIG, 0, bytes([index & 0xFF]))


def onboard_profile(mouse: Mouse) -> int:
    return mouse.command(Command.GET_CURRENT_CONFIG).data[0]


# --- presentation -------------------------------------------------------------

_MOUSE_NAMES = {0: "Disabled", 1: "Left click", 2: "Right click", 4: "Middle click",
                8: "Back (side 1)", 16: "Forward (side 2)"}
_DPI_NAMES = {1: "DPI cycle", 2: "DPI +", 3: "DPI -"}
_WHEEL_NAMES = {1: "Wheel up", 2: "Wheel down"}
_ROLL_NAMES = {1: "Tilt left", 2: "Tilt right"}


def describe_action(action: ButtonAction) -> str:
    """Human-readable label for a button assignment."""
    kind = action.action
    if kind == ButtonClass.CLOSE:
        return "Disabled"
    if kind == ButtonClass.MOUSE:
        return _MOUSE_NAMES.get(action.value1, f"Mouse {action.value1}")
    if kind == ButtonClass.DPI:
        return _DPI_NAMES.get(action.value1, f"DPI {action.value1}")
    if kind == ButtonClass.ROLL_SIDE_TO_SIDE:
        return _ROLL_NAMES.get(action.value1, f"Tilt {action.value1}")
    if kind == ButtonClass.FIREPOWER_KEY:
        return f"Rapid fire ({action.value1})"
    if kind == ButtonClass.SHORTCUT_KEY:
        return "Keyboard combination"
    if kind == ButtonClass.MACRO:
        from .macros import REPEAT_LABELS, decode_repeat

        mode, count = decode_repeat(action.value2)
        suffix = f" x{count}" if mode == "count" else ""
        return f"Macro {action.value1 + 1} ({REPEAT_LABELS[mode].lower()}{suffix})"
    if kind == ButtonClass.REPORT_RATE:
        return "Switch report rate"
    if kind == ButtonClass.CONFIG_FILE:
        return f"Onboard profile {action.value1}"
    if kind == ButtonClass.DPI_LOCK:
        return "DPI lock"
    if kind == ButtonClass.WHEEL:
        return _WHEEL_NAMES.get(action.value1, f"Wheel {action.value1}")
    return f"Class {kind} ({action.value1}, {action.value2})"


def default_buttons() -> dict[str, ButtonAction]:
    return {
        name: ButtonAction(int(cls), int(v1), int(v2))
        for name, (cls, v1, v2) in BUTTON_DEFAULTS.items()
    }
