"""Mapping between Qt keys and HID keyboard usage codes.

Macros store HID usages (USB HID Usage Table, page 0x07), which is what the
firmware replays. Recording from Qt therefore needs a translation both ways.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

#: HID usage -> display name.
USAGE_NAMES: dict[int, str] = {}

#: Qt.Key -> HID usage.
QT_TO_USAGE: dict[int, int] = {}


def _register(usage: int, name: str, qt_key: int | None = None) -> None:
    USAGE_NAMES[usage] = name
    if qt_key is not None:
        QT_TO_USAGE[int(qt_key)] = usage


# Letters: HID 0x04..0x1D are A..Z
for _offset in range(26):
    _register(0x04 + _offset, chr(ord("A") + _offset), Qt.Key_A + _offset)

# Digits: HID 0x1E..0x26 are 1..9, 0x27 is 0
for _offset in range(9):
    _register(0x1E + _offset, str(_offset + 1), Qt.Key_1 + _offset)
_register(0x27, "0", Qt.Key_0)

# Function keys: HID 0x3A..0x45 are F1..F12
for _offset in range(12):
    _register(0x3A + _offset, f"F{_offset + 1}", Qt.Key_F1 + _offset)

_CONTROLS = [
    (0x28, "Enter", Qt.Key_Return),
    (0x29, "Esc", Qt.Key_Escape),
    (0x2A, "Backspace", Qt.Key_Backspace),
    (0x2B, "Tab", Qt.Key_Tab),
    (0x2C, "Space", Qt.Key_Space),
    (0x2D, "-", Qt.Key_Minus),
    (0x2E, "=", Qt.Key_Equal),
    (0x2F, "[", Qt.Key_BracketLeft),
    (0x30, "]", Qt.Key_BracketRight),
    (0x31, "\\", Qt.Key_Backslash),
    (0x33, ";", Qt.Key_Semicolon),
    (0x34, "'", Qt.Key_Apostrophe),
    (0x35, "`", Qt.Key_QuoteLeft),
    (0x36, ",", Qt.Key_Comma),
    (0x37, ".", Qt.Key_Period),
    (0x38, "/", Qt.Key_Slash),
    (0x39, "Caps Lock", Qt.Key_CapsLock),
    (0x46, "Print Screen", Qt.Key_Print),
    (0x47, "Scroll Lock", Qt.Key_ScrollLock),
    (0x48, "Pause", Qt.Key_Pause),
    (0x49, "Insert", Qt.Key_Insert),
    (0x4A, "Home", Qt.Key_Home),
    (0x4B, "Page Up", Qt.Key_PageUp),
    (0x4C, "Delete", Qt.Key_Delete),
    (0x4D, "End", Qt.Key_End),
    (0x4E, "Page Down", Qt.Key_PageDown),
    (0x4F, "Right", Qt.Key_Right),
    (0x50, "Left", Qt.Key_Left),
    (0x51, "Down", Qt.Key_Down),
    (0x52, "Up", Qt.Key_Up),
    (0x53, "Num Lock", Qt.Key_NumLock),
    (0x65, "Menu", Qt.Key_Menu),
]
for _usage, _name, _key in _CONTROLS:
    _register(_usage, _name, _key)

# Keypad. Qt does not distinguish these without the KeypadModifier, so they are
# named but not bound to a plain Qt key.
_KEYPAD = [
    (0x54, "Num /"), (0x55, "Num *"), (0x56, "Num -"), (0x57, "Num +"),
    (0x58, "Num Enter"), (0x59, "Num 1"), (0x5A, "Num 2"), (0x5B, "Num 3"),
    (0x5C, "Num 4"), (0x5D, "Num 5"), (0x5E, "Num 6"), (0x5F, "Num 7"),
    (0x60, "Num 8"), (0x61, "Num 9"), (0x62, "Num 0"), (0x63, "Num ."),
]
for _usage, _name in _KEYPAD:
    _register(_usage, _name)

#: HID usages for the keypad, indexed the way Qt reports them.
KEYPAD_USAGES = {
    int(Qt.Key_Slash): 0x54,
    int(Qt.Key_Asterisk): 0x55,
    int(Qt.Key_Minus): 0x56,
    int(Qt.Key_Plus): 0x57,
    int(Qt.Key_Enter): 0x58,
    int(Qt.Key_1): 0x59, int(Qt.Key_2): 0x5A, int(Qt.Key_3): 0x5B,
    int(Qt.Key_4): 0x5C, int(Qt.Key_5): 0x5D, int(Qt.Key_6): 0x5E,
    int(Qt.Key_7): 0x5F, int(Qt.Key_8): 0x60, int(Qt.Key_9): 0x61,
    int(Qt.Key_0): 0x62, int(Qt.Key_Period): 0x63,
}

# Modifiers. Qt reports one key for each side only via the native scan code, so
# the left-hand variants are used when recording.
_MODIFIERS = [
    (0xE0, "Left Ctrl", Qt.Key_Control),
    (0xE1, "Left Shift", Qt.Key_Shift),
    (0xE2, "Left Alt", Qt.Key_Alt),
    (0xE3, "Left Win", Qt.Key_Meta),
    (0xE4, "Right Ctrl", None),
    (0xE5, "Right Shift", None),
    (0xE6, "Right Alt", Qt.Key_AltGr),
    (0xE7, "Right Win", None),
]
for _usage, _name, _key in _MODIFIERS:
    _register(_usage, _name, _key)

_register(0x00, "None")

#: Keys worth offering in a picker, grouped for the UI.
PICKER_GROUPS: list[tuple[str, list[int]]] = [
    ("Letters", list(range(0x04, 0x1E))),
    ("Digits", list(range(0x1E, 0x28))),
    ("Function", list(range(0x3A, 0x46))),
    ("Modifiers", [0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7]),
    ("Navigation", [0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52]),
    ("Editing", [0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x39, 0x65]),
    ("Punctuation", [0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38]),
    ("Keypad", [u for u, _ in _KEYPAD]),
]


def usage_name(usage: int) -> str:
    return USAGE_NAMES.get(usage, f"Key {usage:#04x}")


def usage_for_qt(key: int, keypad: bool = False) -> int | None:
    """Translate a Qt key code into a HID usage, or None if unmapped."""
    if keypad and int(key) in KEYPAD_USAGES:
        return KEYPAD_USAGES[int(key)]
    return QT_TO_USAGE.get(int(key))
