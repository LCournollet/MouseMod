"""Combination keys: a chord of up to three keys bound to a mouse button.

Each physical button has its own record at ``256 + 32 * button_index``:

    page 0 (offset 0)   byte 0 = entry count, bytes 1..9 = payload[0:9]
    page 1 (offset 10)  bytes 0..9          = payload[9:19]

The payload is the entries, 3 bytes each, followed by one check byte:

    crc = (85 - sum(count byte + entry bytes)) & 0xFF

An entry has the same byte-0 layout as a macro action (bit 7 down, bit 6 up,
bits 0..2 key type) but carries no delay, so it is 3 bytes rather than 5.

The firmware stores two entries per key - every key pressed, then every key
released - which is why six entries means three keys.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .device import Mouse
from .protocol import (
    MODIFIER_USAGES,
    SHORTCUT_ADDRESSES,
    SHORTCUT_ENTRY_SIZE,
    SHORTCUT_FIRST_PAGE_PAYLOAD,
    SHORTCUT_MAX_ENTRIES,
    SHORTCUT_MAX_KEYS,
    SHORTCUT_PAGE_SIZE,
    KeyState,
    MacroKeyType,
    crc,
    pack_state_type,
    unpack_state_type,
)

BUTTON_ORDER = ("left", "right", "middle", "side1", "side2", "bottom")

#: Reverse lookup: modifier bitmask -> HID usage.
MASK_TO_USAGE = {mask: usage for usage, mask in MODIFIER_USAGES.items()}


@dataclass
class ShortcutStep:
    """One stored entry: a key going down or coming back up."""

    key_type: int = int(MacroKeyType.KEY)
    state: int = int(KeyState.DOWN)
    value1: int = 0
    value2: int = 0

    def to_bytes(self) -> bytes:
        return bytes(
            [
                pack_state_type(self.state, self.key_type),
                self.value1 & 0xFF,
                self.value2 & 0xFF,
            ]
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "ShortcutStep":
        state, key_type = unpack_state_type(data[0])
        return cls(key_type=key_type, state=state, value1=data[1], value2=data[2])

    @property
    def usage(self) -> int:
        """The HID usage this entry refers to, whatever type it is stored as."""
        if self.key_type == MacroKeyType.MODIFIER:
            return MASK_TO_USAGE.get(self.value1, 0)
        return self.value1


def _step_for(usage: int, down: bool) -> ShortcutStep:
    is_modifier = usage in MODIFIER_USAGES
    return ShortcutStep(
        key_type=int(MacroKeyType.MODIFIER if is_modifier else MacroKeyType.KEY),
        state=int(KeyState.DOWN if down else KeyState.UP),
        value1=MODIFIER_USAGES.get(usage, usage),
    )


def build(usages: list[int]) -> list[ShortcutStep]:
    """Turn a chord into stored entries: all keys down, then up in reverse.

    Releasing in reverse order is what a keyboard does when you let a chord go,
    so a modifier never outlives the key it was modifying.
    """
    keys = [u for u in usages if u][:SHORTCUT_MAX_KEYS]
    if not keys:
        return []
    downs = [_step_for(usage, True) for usage in keys]
    ups = [_step_for(usage, False) for usage in reversed(keys)]
    return downs + ups


def to_usages(steps: list[ShortcutStep]) -> list[int]:
    """Recover the chord from stored entries: the leading run of key downs."""
    return [
        step.usage for step in steps if step.state == KeyState.DOWN and step.usage
    ]


def describe(steps: list[ShortcutStep]) -> str:
    from .keymap import usage_name

    usages = to_usages(steps)
    return " + ".join(usage_name(u) for u in usages) if usages else "Not set"


# --- device access ------------------------------------------------------------


def _address(button: str | int) -> int:
    index = BUTTON_ORDER.index(button) if isinstance(button, str) else button
    if not 0 <= index < len(SHORTCUT_ADDRESSES):
        raise IndexError(f"no shortcut record for button {button!r}")
    return SHORTCUT_ADDRESSES[index]


def read_shortcut(mouse: Mouse, button: str | int) -> list[ShortcutStep]:
    base = _address(button)

    page0 = mouse.read_eeprom(base, SHORTCUT_PAGE_SIZE)
    count = page0[0]
    if count == 0 or count > SHORTCUT_MAX_ENTRIES:
        return []

    payload = bytearray(page0[1 : 1 + SHORTCUT_FIRST_PAGE_PAYLOAD])
    if count * SHORTCUT_ENTRY_SIZE > SHORTCUT_FIRST_PAGE_PAYLOAD:
        payload += mouse.read_eeprom(base + SHORTCUT_PAGE_SIZE, SHORTCUT_PAGE_SIZE)

    return [
        ShortcutStep.from_bytes(
            bytes(payload[i * SHORTCUT_ENTRY_SIZE : (i + 1) * SHORTCUT_ENTRY_SIZE])
        )
        for i in range(count)
    ]


def write_shortcut(mouse: Mouse, button: str | int, steps: list[ShortcutStep]) -> None:
    base = _address(button)
    steps = steps[:SHORTCUT_MAX_ENTRIES]

    entries = bytearray()
    for step in steps:
        entries += step.to_bytes()

    payload = bytes(entries) + bytes([crc(len(steps), *entries)])

    first = bytes([len(steps)]) + payload[:SHORTCUT_FIRST_PAGE_PAYLOAD]
    mouse.write_eeprom(base, first.ljust(SHORTCUT_PAGE_SIZE, b"\x00"))

    if len(payload) > SHORTCUT_FIRST_PAGE_PAYLOAD:
        second = payload[SHORTCUT_FIRST_PAGE_PAYLOAD:]
        mouse.write_eeprom(
            base + SHORTCUT_PAGE_SIZE, second.ljust(SHORTCUT_PAGE_SIZE, b"\x00")
        )


def read_all(mouse: Mouse) -> dict[str, list[ShortcutStep]]:
    return {name: read_shortcut(mouse, name) for name in BUTTON_ORDER}


def write_all(
    mouse: Mouse,
    shortcuts: dict[str, list[ShortcutStep]],
    current: dict[str, list[ShortcutStep]] | None = None,
) -> None:
    for name, steps in shortcuts.items():
        if name not in BUTTON_ORDER:
            continue
        if current is not None and _serialise(current.get(name, [])) == _serialise(steps):
            continue
        write_shortcut(mouse, name, steps)


def _serialise(steps: list[ShortcutStep]) -> list[dict]:
    return [asdict(step) for step in steps]


def default_shortcuts() -> dict[str, list[ShortcutStep]]:
    return {name: [] for name in BUTTON_ORDER}
