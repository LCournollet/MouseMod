"""On-device macros: 16 slots, read and written through plain EEPROM pages.

Slot layout, derived from the ATK HUB bundle and verified on the device:

    offset  0..30   fixed header, always [8] + [2]*8 + [255]*22
    offset  31      number of actions
    offset  32..    actions, 5 bytes each
    last            checksum = (85 - sum(count byte + action bytes)) & 0xFF

An action is:

    byte 0   bit 7 set = key down, bit 6 set = key up, neither = wheel;
             bits 0..2 hold the key type
    byte 1   value1 (HID usage, modifier bitmask, or wheel direction)
    byte 2   value2
    byte 3-4 delay in milliseconds, big endian
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .device import Mouse
from .protocol import (
    KEY_TYPE_MASK,
    MACRO_ACTION_SIZE,
    MACRO_ADDRESSES,
    MACRO_COUNT_OFFSET,
    MACRO_DATA_OFFSET,
    MACRO_HEADER,
    MACRO_MAX_ACTIONS,
    MACRO_MAX_LOOPS,
    MACRO_PAGE_SIZE,
    MACRO_REPEAT_UNTIL_ANY_KEY,
    MACRO_REPEAT_UNTIL_KEY_RELEASE,
    MACRO_SLOTS,
    MACRO_STOP_IMMEDIATELY,
    MODIFIER_USAGES,
    STATE_DOWN_BIT,
    STATE_UP_BIT,
    KeyState,
    MacroKeyType,
    crc,
)

#: Repeat behaviour, as stored in value2 of the button assignment.
REPEAT_ONCE = "once"
REPEAT_UNTIL_RELEASE = "until_release"
REPEAT_UNTIL_ANY_KEY = "until_any_key"
REPEAT_COUNT = "count"

REPEAT_LABELS = {
    REPEAT_ONCE: "Play once",
    REPEAT_UNTIL_RELEASE: "Repeat while held",
    REPEAT_UNTIL_ANY_KEY: "Repeat until any key",
    REPEAT_COUNT: "Repeat a set number of times",
}


@dataclass
class MacroAction:
    """One step of a macro."""

    key_type: int = int(MacroKeyType.KEY)
    state: int = int(KeyState.DOWN)
    value1: int = 0
    value2: int = 0
    delay_ms: int = 1

    # -- wire format -------------------------------------------------------

    def to_bytes(self) -> bytes:
        flags = self.key_type & KEY_TYPE_MASK
        if self.state == KeyState.DOWN:
            flags |= STATE_DOWN_BIT
        elif self.state == KeyState.UP:
            flags |= STATE_UP_BIT
        delay = max(0, min(0xFFFF, int(self.delay_ms)))
        return bytes(
            [flags, self.value1 & 0xFF, self.value2 & 0xFF, delay >> 8, delay & 0xFF]
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "MacroAction":
        flags = data[0]
        if flags & STATE_UP_BIT:
            state = int(KeyState.UP)
        elif flags & STATE_DOWN_BIT:
            state = int(KeyState.DOWN)
        else:
            state = int(KeyState.SCROLL)
        return cls(
            key_type=flags & KEY_TYPE_MASK,
            state=state,
            value1=data[1],
            value2=data[2],
            delay_ms=(data[3] << 8) | data[4],
        )

    # -- presentation ------------------------------------------------------

    def describe(self, key_name=None) -> str:
        from .keymap import usage_name

        namer = key_name or usage_name
        if self.key_type == MacroKeyType.WHEEL:
            if self.value1 == 0:
                return "Wheel release"
            return "Wheel down" if self.value1 > 127 else "Wheel up"
        if self.key_type == MacroKeyType.MODIFIER:
            return f"{modifier_name(self.value1)} {self._state_word()}"
        if self.key_type == MacroKeyType.MOUSE:
            return f"{mouse_button_name(self.value1)} {self._state_word()}"
        return f"{namer(self.value1)} {self._state_word()}"

    def _state_word(self) -> str:
        return {int(KeyState.DOWN): "down", int(KeyState.UP): "up"}.get(
            self.state, "scroll"
        )


def modifier_name(mask: int) -> str:
    names = {
        0x01: "Left Ctrl", 0x02: "Left Shift", 0x04: "Left Alt", 0x08: "Left Win",
        0x10: "Right Ctrl", 0x20: "Right Shift", 0x40: "Right Alt", 0x80: "Right Win",
    }
    return names.get(mask, f"Modifier {mask:#04x}")


def mouse_button_name(mask: int) -> str:
    names = {1: "Left click", 2: "Right click", 4: "Middle click",
             8: "Back", 16: "Forward"}
    return names.get(mask, f"Mouse {mask}")


@dataclass
class Macro:
    """One macro slot.

    The repeat mode lives here rather than on the button, so that assigning a
    slot to a button carries the behaviour the macro was designed for.
    """

    name: str = ""
    actions: list[MacroAction] = field(default_factory=list)
    repeat_mode: str = REPEAT_ONCE
    repeat_count: int = 1

    @property
    def is_empty(self) -> bool:
        return not self.actions

    def duration_ms(self) -> int:
        return sum(action.delay_ms for action in self.actions)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "repeat_mode": self.repeat_mode,
            "repeat_count": self.repeat_count,
            "actions": [asdict(a) for a in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Macro":
        return cls(
            name=data.get("name", ""),
            repeat_mode=data.get("repeat_mode", REPEAT_ONCE),
            repeat_count=int(data.get("repeat_count", 1)),
            actions=[MacroAction(**a) for a in data.get("actions", [])],
        )

    def copy(self) -> "Macro":
        return Macro(
            name=self.name,
            actions=[MacroAction(**asdict(a)) for a in self.actions],
            repeat_mode=self.repeat_mode,
            repeat_count=self.repeat_count,
        )

    def wire_equals(self, other: "Macro") -> bool:
        """Compare only what is stored on the device (name and repeat are ours)."""
        return [asdict(a) for a in self.actions] == [asdict(a) for a in other.actions]


# --- builders -----------------------------------------------------------------


def key_press(usage: int, delay_ms: int = 1) -> list[MacroAction]:
    """A full press and release of one key."""
    kind = MacroKeyType.MODIFIER if usage in MODIFIER_USAGES else MacroKeyType.KEY
    value = MODIFIER_USAGES.get(usage, usage)
    return [
        MacroAction(int(kind), int(KeyState.DOWN), value, 0, delay_ms),
        MacroAction(int(kind), int(KeyState.UP), value, 0, delay_ms),
    ]


def key_event(usage: int, down: bool, delay_ms: int = 1) -> MacroAction:
    kind = MacroKeyType.MODIFIER if usage in MODIFIER_USAGES else MacroKeyType.KEY
    value = MODIFIER_USAGES.get(usage, usage)
    state = KeyState.DOWN if down else KeyState.UP
    return MacroAction(int(kind), int(state), value, 0, delay_ms)


def mouse_event(button_mask: int, down: bool, delay_ms: int = 1) -> MacroAction:
    state = KeyState.DOWN if down else KeyState.UP
    return MacroAction(int(MacroKeyType.MOUSE), int(state), button_mask, 0, delay_ms)


def wheel(up: bool, delay_ms: int = 1) -> list[MacroAction]:
    """A wheel notch: one direction sample followed by a release sample."""
    direction = 1 if up else 255
    return [
        MacroAction(int(MacroKeyType.WHEEL), int(KeyState.SCROLL), direction, 0, delay_ms),
        MacroAction(int(MacroKeyType.WHEEL), int(KeyState.SCROLL), 0, 0, delay_ms),
    ]


def delay(milliseconds: int) -> MacroAction:
    """A pure pause, encoded as a no-op key with only a delay."""
    return MacroAction(int(MacroKeyType.KEY), int(KeyState.UP), 0, 0, milliseconds)


# --- repeat mode --------------------------------------------------------------


def encode_repeat(mode: str, count: int = 1) -> int:
    """Repeat mode -> the value2 byte of a macro button assignment."""
    if mode == REPEAT_UNTIL_RELEASE:
        return MACRO_REPEAT_UNTIL_KEY_RELEASE
    if mode == REPEAT_UNTIL_ANY_KEY:
        return MACRO_REPEAT_UNTIL_ANY_KEY
    if mode == REPEAT_COUNT:
        return max(1, min(MACRO_MAX_LOOPS, count))
    return MACRO_STOP_IMMEDIATELY


def decode_repeat(value2: int) -> tuple[str, int]:
    if value2 == MACRO_REPEAT_UNTIL_KEY_RELEASE:
        return REPEAT_UNTIL_RELEASE, 1
    if value2 == MACRO_REPEAT_UNTIL_ANY_KEY:
        return REPEAT_UNTIL_ANY_KEY, 1
    if value2 == MACRO_STOP_IMMEDIATELY:
        return REPEAT_ONCE, 1
    return REPEAT_COUNT, max(1, value2)


# --- device access ------------------------------------------------------------


def _slot_address(index: int) -> int:
    if not 0 <= index < MACRO_SLOTS:
        raise IndexError(f"macro slot must be 0..{MACRO_SLOTS - 1}, got {index}")
    return MACRO_ADDRESSES[index]


def read_macro(mouse: Mouse, index: int) -> Macro:
    """Read one slot. An empty or corrupt slot comes back as an empty macro."""
    base = _slot_address(index)
    name = f"Macro {index + 1}"

    count = mouse.read_eeprom(base + MACRO_COUNT_OFFSET, 1)[0]
    if count == 0 or count > MACRO_MAX_ACTIONS:
        return Macro(name=name)

    needed = count * MACRO_ACTION_SIZE
    pages = math.ceil(needed / MACRO_PAGE_SIZE)
    payload = bytearray()
    for page in range(pages):
        payload += mouse.read_eeprom(
            base + MACRO_DATA_OFFSET + page * MACRO_PAGE_SIZE, MACRO_PAGE_SIZE
        )

    actions = [
        MacroAction.from_bytes(bytes(payload[i * MACRO_ACTION_SIZE :
                                             (i + 1) * MACRO_ACTION_SIZE]))
        for i in range(count)
    ]
    return Macro(name=name, actions=actions)


def write_macro(mouse: Mouse, index: int, macro: Macro) -> None:
    """Write one slot, header and checksum included."""
    base = _slot_address(index)
    actions = macro.actions[:MACRO_MAX_ACTIONS]

    body = bytearray([len(actions)])
    for action in actions:
        body += action.to_bytes()
    body.append(crc(*body))

    record = bytes(MACRO_HEADER) + bytes(body)
    pages = math.ceil(len(record) / MACRO_PAGE_SIZE)
    for page in range(pages):
        chunk = record[page * MACRO_PAGE_SIZE : (page + 1) * MACRO_PAGE_SIZE]
        chunk = chunk.ljust(MACRO_PAGE_SIZE, b"\x00")
        mouse.write_eeprom(base + page * MACRO_PAGE_SIZE, chunk)


def clear_macro(mouse: Mouse, index: int) -> None:
    write_macro(mouse, index, Macro(name=f"Macro {index + 1}"))


def read_all(mouse: Mouse, count: int = MACRO_SLOTS) -> list[Macro]:
    return [read_macro(mouse, index) for index in range(count)]


def write_all(
    mouse: Mouse, macros: list[Macro], current: list[Macro] | None = None
) -> None:
    """Write every slot that differs from ``current``."""
    for index, macro in enumerate(macros[:MACRO_SLOTS]):
        if current is not None and index < len(current):
            if current[index].wire_equals(macro):
                continue
        write_macro(mouse, index, macro)


def default_macros() -> list[Macro]:
    return [Macro(name=f"Macro {i + 1}") for i in range(MACRO_SLOTS)]
