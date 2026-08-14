"""A control that captures a keyboard chord for a mouse button.

Like the macro recorder, this only listens while MouseMod has focus - it grabs
the keyboard for the duration of the capture rather than installing a hook.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QPushButton

from .keymap import usage_for_qt
from .protocol import SHORTCUT_MAX_KEYS
from .shortcuts import ShortcutStep, build, describe, to_usages
from .theme import Color

#: Qt modifier -> HID usage, in the order a chord reads naturally.
MODIFIER_ORDER = [
    (Qt.ControlModifier, 0xE0),
    (Qt.ShiftModifier, 0xE1),
    (Qt.AltModifier, 0xE2),
    (Qt.MetaModifier, 0xE3),
]

#: Keys that only ever act as modifiers, ignored as the "main" key.
MODIFIER_KEYS = {
    int(Qt.Key_Control), int(Qt.Key_Shift), int(Qt.Key_Alt),
    int(Qt.Key_Meta), int(Qt.Key_AltGr),
}


class ShortcutCapture(QPushButton):
    """Click, then press a key combination. Escape cancels, Delete clears."""

    changed = Signal(list)  # list[ShortcutStep]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: list[ShortcutStep] = []
        self._capturing = False
        self._truncated = False
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(180)
        self.clicked.connect(self._begin)
        self._refresh()

    # -- state -------------------------------------------------------------

    def set_steps(self, steps: list[ShortcutStep]) -> None:
        self.steps = list(steps)
        self._truncated = False
        self._refresh()

    def _refresh(self) -> None:
        if self._capturing:
            self.setText("Press a combination...")
            border, colour = Color.ACCENT, Color.ACCENT
        elif self.steps:
            self.setText(describe(self.steps))
            border, colour = Color.BORDER, Color.TEXT
        else:
            self.setText("Click to set")
            border, colour = Color.BORDER, Color.TEXT_MUTE

        self.setStyleSheet(
            f"QPushButton {{ background: {Color.SURFACE_2}; border: 1px solid "
            f"{border}; border-radius: 8px; padding: 7px 12px; color: {colour}; "
            f"text-align: left; }}"
            f"QPushButton:hover {{ border-color: {Color.BORDER_STRONG}; }}"
        )
        if self._truncated:
            self.setToolTip(
                f"The mouse stores at most {SHORTCUT_MAX_KEYS} keys, so the "
                "combination was shortened."
            )
        else:
            self.setToolTip(
                "Click, then press the combination. Escape cancels, Delete clears."
            )

    # -- capture -----------------------------------------------------------

    def _begin(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._truncated = False
        self.grabKeyboard()
        self._refresh()

    def _end(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self.releaseKeyboard()
        self._refresh()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._end()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key = int(event.key())
        if key == int(Qt.Key_Escape):
            self._end()
            event.accept()
            return
        if key in (int(Qt.Key_Delete), int(Qt.Key_Backspace)):
            self.steps = []
            self._end()
            self.changed.emit(self.steps)
            event.accept()
            return
        if key in MODIFIER_KEYS:
            event.accept()  # wait for the key the modifiers apply to
            return

        usage = usage_for_qt(key, keypad=bool(event.modifiers() & Qt.KeypadModifier))
        if usage is None:
            event.accept()
            return

        usages = [
            hid for modifier, hid in MODIFIER_ORDER if event.modifiers() & modifier
        ]
        usages.append(usage)

        self._truncated = len(usages) > SHORTCUT_MAX_KEYS
        self.steps = build(usages)
        self._end()
        self.changed.emit(self.steps)
        event.accept()

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if self._capturing:
            event.accept()
            return
        super().keyReleaseEvent(event)

    def usages(self) -> list[int]:
        return to_usages(self.steps)
