"""The Macros page: slot list, action editor and a keyboard recorder.

Recording captures key events only while MouseMod itself has focus, through a
Qt event filter. It is deliberately not a system-wide keyboard hook.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .keymap import PICKER_GROUPS, usage_for_qt, usage_name
from .macros import (
    REPEAT_COUNT,
    REPEAT_LABELS,
    REPEAT_ONCE,
    REPEAT_UNTIL_ANY_KEY,
    REPEAT_UNTIL_RELEASE,
    Macro,
    MacroAction,
    delay as delay_action,
    key_event,
    mouse_event,
    wheel,
)
from .protocol import MACRO_MAX_ACTIONS, KeyState, MacroKeyType
from .theme import Color
from .widgets import Card, Field, NumberInput, Select, divider_line

REPEAT_ORDER = [REPEAT_ONCE, REPEAT_UNTIL_RELEASE, REPEAT_UNTIL_ANY_KEY, REPEAT_COUNT]

#: Extra actions the picker can insert that are not plain keyboard keys.
EXTRA_ACTIONS = [
    ("Left click", MacroKeyType.MOUSE, 1),
    ("Right click", MacroKeyType.MOUSE, 2),
    ("Middle click", MacroKeyType.MOUSE, 4),
    ("Back", MacroKeyType.MOUSE, 8),
    ("Forward", MacroKeyType.MOUSE, 16),
]


class KeyRecorder(QObject):
    """Captures key presses and releases while active, with real timing."""

    captured = Signal(object)  # MacroAction

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.active = False
        self._last_event: float | None = None

    def start(self) -> None:
        self.active = True
        self._last_event = None
        QApplication.instance().installEventFilter(self)

    def stop(self) -> None:
        self.active = False
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if not self.active:
            return False
        if event.type() not in (QEvent.KeyPress, QEvent.KeyRelease):
            return False
        if event.isAutoRepeat():
            return True

        usage = usage_for_qt(
            event.key(), keypad=bool(event.modifiers() & Qt.KeypadModifier)
        )
        if usage is None:
            return True  # swallow unmapped keys rather than let them act

        now = time.monotonic()
        gap = 1 if self._last_event is None else int((now - self._last_event) * 1000)
        self._last_event = now

        self.captured.emit(
            key_event(usage, down=event.type() == QEvent.KeyPress,
                      delay_ms=max(1, min(65535, gap)))
        )
        return True


class ActionPicker(QDialog):
    """Choose a key or mouse action to insert."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add action")
        self.resize(360, 460)
        self.selected: MacroAction | None = None

        layout = QVBoxLayout(self)

        self.kind = Select()
        self.kind.addItems(["Press and release", "Press only", "Release only"])
        layout.addWidget(QLabel("Behaviour"))
        layout.addWidget(self.kind)

        layout.addWidget(QLabel("Key"))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        for label, usage, kind in self._entries():
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, (usage, kind))
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        layout.addWidget(self.list, 1)

        self.delay = NumberInput()
        self.delay.setRange(1, 65535)
        self.delay.setValue(10)
        self.delay.setSuffix(" ms")
        layout.addWidget(Field("Delay per step", self.delay))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _entries() -> list[tuple[str, int, int]]:
        entries: list[tuple[str, int, int]] = []
        for label, kind, value in EXTRA_ACTIONS:
            entries.append((f"Mouse - {label}", value, int(kind)))
        entries.append(("Wheel - up", 1, int(MacroKeyType.WHEEL)))
        entries.append(("Wheel - down", 255, int(MacroKeyType.WHEEL)))
        for group, usages in PICKER_GROUPS:
            for usage in usages:
                entries.append((f"{group} - {usage_name(usage)}", usage, -1))
        return entries

    def actions(self) -> list[MacroAction]:
        """The actions the dialog would insert, honouring the behaviour choice."""
        item = self.list.currentItem()
        if item is None:
            return []
        usage, kind = item.data(Qt.UserRole)
        step = self.delay.value()
        mode = self.kind.currentIndex()

        if kind == int(MacroKeyType.WHEEL):
            return wheel(up=usage == 1, delay_ms=step)
        if kind == int(MacroKeyType.MOUSE):
            if mode == 1:
                return [mouse_event(usage, True, step)]
            if mode == 2:
                return [mouse_event(usage, False, step)]
            return [mouse_event(usage, True, step), mouse_event(usage, False, step)]

        if mode == 1:
            return [key_event(usage, True, step)]
        if mode == 2:
            return [key_event(usage, False, step)]
        return [key_event(usage, True, step), key_event(usage, False, step)]


class MacroPage(QWidget):
    """Slot list on the left, the selected macro's actions on the right."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self.macros: list[Macro] = []
        self.recorder = KeyRecorder(self)
        self.recorder.captured.connect(self._on_captured)

        columns = QHBoxLayout(self)
        columns.setContentsMargins(0, 0, 8, 0)
        columns.setSpacing(14)
        columns.addWidget(self._build_slots(), 0)
        columns.addWidget(self._build_editor(), 1)

    # -- construction ------------------------------------------------------

    def _build_slots(self) -> QWidget:
        card = Card("Slots")
        card.setFixedWidth(200)
        self.slot_list = QListWidget()
        self.slot_list.setObjectName("ProfileList")
        self.slot_list.currentRowChanged.connect(self._on_slot_selected)
        card.add(self.slot_list)
        return card

    def _build_editor(self) -> QWidget:
        card = Card("Actions")

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Macro name")
        self.name.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self.name, 1)
        card.add_layout(name_row)

        self.action_list = QListWidget()
        self.action_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.action_list.setMinimumHeight(190)
        self.action_list.setStyleSheet(
            f"QListWidget {{ background: {Color.SURFACE_2}; border: 1px solid "
            f"{Color.BORDER}; border-radius: 8px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 5px 8px; border-radius: 5px; }}"
            f"QListWidget::item:selected {{ background: {Color.ACCENT_SOFT}; }}"
        )
        card.add(self.action_list)

        # Two rows: capture on top, list editing below, so nothing gets
        # squeezed to an unreadable width.
        capture_row = QHBoxLayout()
        capture_row.setSpacing(6)

        self.record_button = QPushButton("Record")
        self.record_button.setObjectName("Primary")
        self.record_button.setCheckable(True)
        self.record_button.setMinimumWidth(96)
        self.record_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.record_button.toggled.connect(self._on_record_toggled)
        capture_row.addWidget(self.record_button)

        for label, slot in (
            ("Add action", self._add_action),
            ("Add delay", self._add_delay),
        ):
            button = QPushButton(label)
            button.setObjectName("Ghost")
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.clicked.connect(slot)
            capture_row.addWidget(button)
        capture_row.addStretch()
        card.add_layout(capture_row)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(6)
        for label, slot in (
            ("Move up", lambda: self._move(-1)),
            ("Move down", lambda: self._move(1)),
            ("Remove", self._remove_selected),
            ("Clear all", self._clear),
        ):
            button = QPushButton(label)
            button.setObjectName("Ghost")
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.clicked.connect(slot)
            edit_row.addWidget(button)
        edit_row.addStretch()
        card.add_layout(edit_row)

        self.hint = QLabel(
            "Recording captures keys while this window has focus. "
            "Timing between keystrokes is preserved."
        )
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        card.add(self.hint)

        card.add(divider_line())

        self.repeat = Select()
        self.repeat.addItems([REPEAT_LABELS[mode] for mode in REPEAT_ORDER])
        self.repeat.setFixedWidth(230)
        self.repeat.currentIndexChanged.connect(self._on_repeat_changed)
        card.add(Field("Repeat", self.repeat, "Used when bound to a button"))

        self.repeat_count = NumberInput()
        self.repeat_count.setRange(1, 252)
        self.repeat_count.setFixedWidth(230)
        self.repeat_count.valueChanged.connect(self._on_repeat_changed)
        self.repeat_count_field = Field("Number of repeats", self.repeat_count)
        card.add(self.repeat_count_field)

        return card

    # -- data binding ------------------------------------------------------

    def load(self, macros: list[Macro]) -> None:
        self.macros = macros
        self._loading = True
        try:
            row = max(0, self.slot_list.currentRow())
            self.slot_list.clear()
            for index, macro in enumerate(macros):
                label = macro.name or f"Macro {index + 1}"
                count = len(macro.actions)
                suffix = f"  ({count})" if count else ""
                self.slot_list.addItem(f"{index + 1}. {label}{suffix}")
            self.slot_list.setCurrentRow(min(row, len(macros) - 1) if macros else -1)
        finally:
            self._loading = False
        self._load_current()

    def current_macro(self) -> Macro | None:
        row = self.slot_list.currentRow()
        return self.macros[row] if 0 <= row < len(self.macros) else None

    def _load_current(self) -> None:
        macro = self.current_macro()
        enabled = macro is not None
        for widget in (self.name, self.action_list, self.record_button,
                       self.repeat, self.repeat_count):
            widget.setEnabled(enabled)
        if macro is None:
            return

        self._loading = True
        try:
            self.name.setText(macro.name)
            self._refresh_actions()
            mode = macro.repeat_mode if macro.repeat_mode in REPEAT_ORDER else REPEAT_ONCE
            self.repeat.setCurrentIndex(REPEAT_ORDER.index(mode))
            self.repeat_count.setValue(max(1, macro.repeat_count))
            self.repeat_count_field.setVisible(mode == REPEAT_COUNT)
        finally:
            self._loading = False

    def _refresh_actions(self) -> None:
        macro = self.current_macro()
        self.action_list.clear()
        if macro is None:
            return
        for index, action in enumerate(macro.actions):
            self.action_list.addItem(
                f"{index + 1:>3}.  {action.describe():<22}  +{action.delay_ms} ms"
            )
        total = macro.duration_ms()
        self.hint.setText(
            f"{len(macro.actions)} action(s), {total} ms total. "
            f"Recording captures keys while this window has focus."
            if macro.actions else
            "Press Record and type, or use Add to insert actions by hand."
        )

    def _touch(self) -> None:
        """Refresh the slot label and tell the editor something changed."""
        row = self.slot_list.currentRow()
        macro = self.current_macro()
        if macro is not None and 0 <= row < self.slot_list.count():
            label = macro.name or f"Macro {row + 1}"
            count = len(macro.actions)
            suffix = f"  ({count})" if count else ""
            self.slot_list.item(row).setText(f"{row + 1}. {label}{suffix}")
        self._refresh_actions()
        if not self._loading:
            self.changed.emit()

    # -- slots -------------------------------------------------------------

    def _on_slot_selected(self, _row: int) -> None:
        if self.record_button.isChecked():
            self.record_button.setChecked(False)
        self._load_current()

    def _on_name_changed(self) -> None:
        macro = self.current_macro()
        if macro is None or self._loading:
            return
        macro.name = self.name.text().strip()
        self._touch()

    def _on_repeat_changed(self) -> None:
        macro = self.current_macro()
        if macro is None or self._loading:
            return
        macro.repeat_mode = REPEAT_ORDER[self.repeat.currentIndex()]
        macro.repeat_count = self.repeat_count.value()
        self.repeat_count_field.setVisible(macro.repeat_mode == REPEAT_COUNT)
        self.changed.emit()

    # -- recording ---------------------------------------------------------

    def _on_record_toggled(self, recording: bool) -> None:
        if recording:
            self.record_button.setText("Stop")
            self.hint.setText("Recording. Type now, then click Stop.")
            self.recorder.start()
        else:
            self.recorder.stop()
            self.record_button.setText("Record")
            self._refresh_actions()

    def _on_captured(self, action: MacroAction) -> None:
        macro = self.current_macro()
        if macro is None:
            return
        if len(macro.actions) >= MACRO_MAX_ACTIONS:
            self.record_button.setChecked(False)
            self.hint.setText(
                f"Reached the {MACRO_MAX_ACTIONS}-action limit; recording stopped."
            )
            return
        macro.actions.append(action)
        self._touch()
        self.action_list.scrollToBottom()

    # -- editing -----------------------------------------------------------

    def _insert(self, actions: list[MacroAction]) -> None:
        macro = self.current_macro()
        if macro is None or not actions:
            return
        room = MACRO_MAX_ACTIONS - len(macro.actions)
        if room <= 0:
            self.hint.setText(f"This macro already holds {MACRO_MAX_ACTIONS} actions.")
            return
        row = self.action_list.currentRow()
        at = len(macro.actions) if row < 0 else row + 1
        macro.actions[at:at] = actions[:room]
        self._touch()
        self.action_list.setCurrentRow(min(at + len(actions) - 1,
                                           len(macro.actions) - 1))

    def _add_action(self) -> None:
        if self.current_macro() is None:
            return
        dialog = ActionPicker(self)
        if dialog.exec() == QDialog.Accepted:
            self._insert(dialog.actions())

    def _add_delay(self) -> None:
        self._insert([delay_action(100)])

    def _move(self, step: int) -> None:
        macro = self.current_macro()
        row = self.action_list.currentRow()
        if macro is None or row < 0:
            return
        target = row + step
        if not 0 <= target < len(macro.actions):
            return
        macro.actions[row], macro.actions[target] = (
            macro.actions[target], macro.actions[row]
        )
        self._touch()
        self.action_list.setCurrentRow(target)

    def _remove_selected(self) -> None:
        macro = self.current_macro()
        if macro is None:
            return
        rows = sorted((i.row() for i in self.action_list.selectedIndexes()), reverse=True)
        for row in rows:
            if 0 <= row < len(macro.actions):
                del macro.actions[row]
        self._touch()

    def _clear(self) -> None:
        macro = self.current_macro()
        if macro is None:
            return
        macro.actions.clear()
        self._touch()
