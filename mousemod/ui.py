"""Qt front end: a frameless dark window plus a system-tray presence.

Device calls are short (a few milliseconds per EEPROM transaction) so they run
inline on the UI thread. Events raised from the watcher and hotkey threads are
marshalled back through a queued signal.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .profiles import Profile
from .protocol import (
    MACRO_SLOTS,
    SHORTCUT_MAX_KEYS,
    ButtonClass,
    DpiValue,
    MouseValue,
    WheelValue,
)
from .shortcut_ui import ShortcutCapture
from .service import MouseService
from .settings import ButtonAction
from .theme import STYLESHEET, Color
from .macro_ui import MacroPage
from .macros import encode_repeat
from .widgets import (
    Card,
    Field,
    FramelessWindow,
    NumberInput,
    Pill,
    ProfileRow,
    SegmentedControl,
    Select,
    StatusDot,
    ToggleSwitch,
    app_icon,
    battery_icon,
    divider_line,
)

REPORT_RATES = [125, 250, 500, 1000, 2000, 4000, 8000]

#: Assignable button actions, as (label, class, value1).
ACTIONS: list[tuple[str, int, int]] = [
    ("Left click", ButtonClass.MOUSE, MouseValue.LEFT),
    ("Right click", ButtonClass.MOUSE, MouseValue.RIGHT),
    ("Middle click", ButtonClass.MOUSE, MouseValue.MIDDLE),
    ("Back (side 1)", ButtonClass.MOUSE, MouseValue.SIDE1),
    ("Forward (side 2)", ButtonClass.MOUSE, MouseValue.SIDE2),
    ("DPI cycle", ButtonClass.DPI, DpiValue.CYCLE),
    ("DPI +", ButtonClass.DPI, DpiValue.PLUS),
    ("DPI -", ButtonClass.DPI, DpiValue.MINUS),
    ("Wheel up", ButtonClass.WHEEL, WheelValue.UP),
    ("Wheel down", ButtonClass.WHEEL, WheelValue.DOWN),
    ("Keyboard combination", ButtonClass.SHORTCUT_KEY, 0),
    ("Switch report rate", ButtonClass.REPORT_RATE, 0),
    ("DPI lock", ButtonClass.DPI_LOCK, 0),
    ("Disabled", ButtonClass.CLOSE, 0),
] + [
    # value1 is the zero-based macro slot; value2 (the repeat mode) is filled
    # in from the macro itself when the assignment is collected.
    (f"Macro {slot + 1}", ButtonClass.MACRO, slot)
    for slot in range(MACRO_SLOTS)
]

BUTTON_LABELS = {
    "left": ("Left button", "Primary click"),
    "right": ("Right button", "Secondary click"),
    "middle": ("Wheel click", "Middle mouse button"),
    "side1": ("Side button 1", "Thumb, rear"),
    "side2": ("Side button 2", "Thumb, front"),
    "bottom": ("Bottom button", "Underside of the mouse"),
}

STAGE_COLORS = ["#5B8DEF", "#30A46C", "#F5A524", "#E5484D"]


class EventBridge(QObject):
    """Marshals service events onto the UI thread."""

    event = Signal(str, object)


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


def divider() -> QFrame:
    return divider_line()


def scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return area


class ProfileEditor(QWidget):
    """Editor for one profile's settings. Emits ``changed`` on every edit."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self.profile: Profile | None = None

        self.nav = SegmentedControl(
            ["Sensor", "Buttons", "Macros", "Performance", "Automation"]
        )
        self.pages = QStackedWidget()
        self.nav.changed.connect(self.pages.setCurrentIndex)

        self.macro_page = MacroPage()
        self.macro_page.changed.connect(self._on_macros_changed)

        self.pages.addWidget(scrollable(self._build_sensor_page()))
        self.pages.addWidget(scrollable(self._build_buttons_page()))
        self.pages.addWidget(scrollable(self.macro_page))
        self.pages.addWidget(scrollable(self._build_performance_page()))
        self.pages.addWidget(scrollable(self._build_automation_page()))

        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.addWidget(self.nav)
        nav_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addLayout(nav_row)
        layout.addWidget(self.pages, 1)

    # -- pages -------------------------------------------------------------

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)
        return page, layout

    def _build_sensor_page(self) -> QWidget:
        page, layout = self._page()

        dpi_card = Card("DPI stages")
        self.dpi_spins: list[NumberInput] = []
        for index in range(4):
            spin = NumberInput()
            spin.setRange(50, 42000)
            spin.setSingleStep(50)
            spin.setSuffix(" DPI")
            spin.setFixedWidth(130)
            spin.valueChanged.connect(self._on_edit)
            self.dpi_spins.append(spin)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            swatch = QLabel()
            swatch.setFixedSize(8, 8)
            swatch.setStyleSheet(
                f"background: {STAGE_COLORS[index]}; border-radius: 4px;"
            )
            row_layout.addWidget(swatch)

            name = QLabel(f"Stage {index + 1}")
            name.setObjectName("FieldLabel")
            row_layout.addWidget(name)
            row_layout.addStretch()
            row_layout.addWidget(spin)

            dpi_card.add(row)

        dpi_card.add(divider())
        self.active_stage = Select()
        self.active_stage.addItems([f"Stage {i + 1}" for i in range(4)])
        self.active_stage.setFixedWidth(130)
        self.active_stage.currentIndexChanged.connect(self._on_edit)
        dpi_card.add(
            Field("Active stage", self.active_stage,
                  "The stage the mouse uses when this profile is applied")
        )
        layout.addWidget(dpi_card)

        tracking = Card("Polling and tracking")

        self.report_rate = Select()
        self.report_rate.addItems([f"{hz} Hz" for hz in REPORT_RATES])
        self.report_rate.setFixedWidth(130)
        self.report_rate.currentIndexChanged.connect(self._on_edit)
        tracking.add(
            Field("Report rate", self.report_rate,
                  "8000 Hz over the cable, or with the 8K receiver")
        )

        self.lod = NumberInput()
        self.lod.setRange(0, 10)
        self.lod.setFixedWidth(130)
        self.lod.valueChanged.connect(self._on_edit)
        tracking.add(
            Field("Lift-off distance", self.lod,
                  "How high the mouse can be lifted before tracking stops")
        )

        self.angle = NumberInput()
        self.angle.setRange(-30, 30)
        self.angle.setSuffix(" deg")
        self.angle.setFixedWidth(130)
        self.angle.valueChanged.connect(self._on_edit)
        tracking.add(
            Field("Sensor rotation", self.angle,
                  "Compensates for holding the mouse at an angle")
        )

        layout.addWidget(tracking)
        layout.addStretch()
        return page

    def _build_buttons_page(self) -> QWidget:
        page, layout = self._page()
        card = Card("Button assignments")
        self.button_combos: dict[str, Select] = {}
        self.shortcut_captures: dict[str, ShortcutCapture] = {}
        self.shortcut_fields: dict[str, QWidget] = {}

        for position, (name, (label, hint)) in enumerate(BUTTON_LABELS.items()):
            combo = Select()
            combo.addItems([text for text, _cls, _v1 in ACTIONS])
            combo.setFixedWidth(180)
            combo.currentIndexChanged.connect(self._on_edit)
            self.button_combos[name] = combo
            if position:
                card.add(divider())
            card.add(Field(label, combo, hint))

            # Only meaningful when the button is set to a keyboard combination,
            # so it stays hidden the rest of the time.
            capture = ShortcutCapture()
            capture.changed.connect(self._on_edit)
            self.shortcut_captures[name] = capture
            field = Field("Combination", capture,
                          f"Up to {SHORTCUT_MAX_KEYS} keys, stored on the mouse")
            field.setVisible(False)
            self.shortcut_fields[name] = field
            card.add(field)

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _sync_shortcut_visibility(self) -> None:
        for name, combo in self.button_combos.items():
            _label, cls, _v1 = ACTIONS[combo.currentIndex()]
            self.shortcut_fields[name].setVisible(cls == ButtonClass.SHORTCUT_KEY)

    def _build_performance_page(self) -> QWidget:
        page, layout = self._page()

        sensor = Card("Sensor processing")

        self.motion_sync = ToggleSwitch()
        self.motion_sync.toggled.connect(self._on_edit)
        sensor.add(
            Field("Motion sync", self.motion_sync,
                  "Aligns sensor sampling with the report interval")
        )
        sensor.add(divider())

        self.linear_correction = ToggleSwitch()
        self.linear_correction.toggled.connect(self._on_edit)
        sensor.add(
            Field("Linear correction", self.linear_correction,
                  "Straightens fast swipes; adds a little latency")
        )
        sensor.add(divider())

        self.ripple_control = ToggleSwitch()
        self.ripple_control.toggled.connect(self._on_edit)
        sensor.add(
            Field("Ripple control", self.ripple_control,
                  "Smooths jitter at very high DPI")
        )
        layout.addWidget(sensor)

        behaviour = Card("Behaviour")

        self.debounce = NumberInput()
        self.debounce.setRange(0, 20)
        self.debounce.setSuffix(" ms")
        self.debounce.setFixedWidth(130)
        self.debounce.valueChanged.connect(self._on_edit)
        behaviour.add(
            Field("Click debounce", self.debounce,
                  "Higher values reject double-clicks from worn switches")
        )
        behaviour.add(divider())

        self.sleep = NumberInput()
        self.sleep.setRange(10, 1800)
        self.sleep.setSingleStep(10)
        self.sleep.setSuffix(" s")
        self.sleep.setFixedWidth(130)
        self.sleep.valueChanged.connect(self._on_edit)
        behaviour.add(
            Field("Sleep after", self.sleep, "Idle time before the mouse sleeps")
        )
        layout.addWidget(behaviour)

        layout.addStretch()
        return page

    def _build_automation_page(self) -> QWidget:
        page, layout = self._page()

        apps = Card("Application binding")
        self.applications = QLineEdit()
        self.applications.setPlaceholderText("valorant.exe, cs2.exe")
        self.applications.editingFinished.connect(self._on_edit)
        apps.body().addWidget(
            QLabel("This profile is applied automatically when one of these "
                   "programs takes focus. Separate them with commas.")
        )
        apps.body().itemAt(apps.body().count() - 1).widget().setObjectName("Hint")
        apps.body().itemAt(apps.body().count() - 1).widget().setWordWrap(True)
        apps.add(self.applications)
        layout.addWidget(apps)

        keys = Card("Hotkey")
        self.hotkey = QLineEdit()
        self.hotkey.setPlaceholderText("ctrl+alt+1")
        self.hotkey.setFixedWidth(180)
        self.hotkey.editingFinished.connect(self._on_edit)
        keys.add(
            Field("Apply this profile", self.hotkey,
                  "Modifiers plus one key, for example ctrl+alt+1")
        )
        keys.add(divider())

        globals_label = QLabel(
            "Always available:  Ctrl+Alt+D cycles the DPI stage  ·  "
            "Ctrl+Alt+P cycles profiles"
        )
        globals_label.setObjectName("Hint")
        globals_label.setWordWrap(True)
        keys.add(globals_label)
        layout.addWidget(keys)

        layout.addStretch()
        return page

    # -- data binding ------------------------------------------------------

    def load(self, profile: Profile | None) -> None:
        self.profile = profile
        self.setEnabled(profile is not None)
        if profile is None:
            return

        self._loading = True
        try:
            settings = profile.settings
            stages = list(settings.dpi_stages) + [800] * (4 - len(settings.dpi_stages))
            for spin, value in zip(self.dpi_spins, stages):
                spin.setValue(value)
            self.active_stage.setCurrentIndex(min(settings.active_stage, 3))

            if settings.report_rate_hz in REPORT_RATES:
                self.report_rate.setCurrentIndex(REPORT_RATES.index(settings.report_rate_hz))
            self.lod.setValue(settings.lod)
            angle = settings.sensor_angle
            self.angle.setValue(angle - 256 if angle > 127 else angle)

            for name, combo in self.button_combos.items():
                combo.setCurrentIndex(self._action_index(settings.buttons.get(name)))
                self.shortcut_captures[name].set_steps(settings.shortcuts.get(name, []))
            self._sync_shortcut_visibility()

            self.motion_sync.setChecked(settings.motion_sync)
            self.linear_correction.setChecked(settings.linear_correction)
            self.ripple_control.setChecked(settings.ripple_control)
            self.debounce.setValue(settings.debounce_ms)
            self.sleep.setValue(max(10, settings.sleep_seconds))

            self.applications.setText(", ".join(profile.applications))
            self.hotkey.setText(profile.hotkey or "")
            self.macro_page.load(settings.macros)
        finally:
            self._loading = False

    @staticmethod
    def _action_index(action: ButtonAction | None) -> int:
        if action is None:
            return 0
        for index, (_label, cls, value1) in enumerate(ACTIONS):
            if action.action == int(cls) and action.value1 == int(value1):
                return index
        return len(ACTIONS) - 1

    def collect(self) -> None:
        """Write the widget state back into the bound profile."""
        if self.profile is None or self._loading:
            return

        settings = self.profile.settings
        settings.dpi_stages = [spin.value() for spin in self.dpi_spins]
        settings.active_stage = self.active_stage.currentIndex()
        settings.report_rate_hz = REPORT_RATES[self.report_rate.currentIndex()]
        settings.lod = self.lod.value()
        settings.sensor_angle = self.angle.value() & 0xFF

        for name, combo in self.button_combos.items():
            _label, cls, value1 = ACTIONS[combo.currentIndex()]
            value2 = 0
            if cls == ButtonClass.MACRO and value1 < len(settings.macros):
                macro = settings.macros[value1]
                value2 = encode_repeat(macro.repeat_mode, macro.repeat_count)
            settings.buttons[name] = ButtonAction(int(cls), int(value1), value2)
            settings.shortcuts[name] = list(self.shortcut_captures[name].steps)

        self._sync_shortcut_visibility()

        settings.motion_sync = self.motion_sync.isChecked()
        settings.linear_correction = self.linear_correction.isChecked()
        settings.ripple_control = self.ripple_control.isChecked()
        settings.debounce_ms = self.debounce.value()
        settings.sleep_seconds = self.sleep.value()

        self.profile.applications = [
            part.strip() for part in self.applications.text().split(",") if part.strip()
        ]
        self.profile.hotkey = self.hotkey.text().strip() or None

    def _on_edit(self) -> None:
        if self._loading:
            return
        self.collect()
        self.changed.emit()

    def _on_macros_changed(self) -> None:
        """The macro page edits the profile's macros in place."""
        if self._loading:
            return
        self.collect()  # a macro's repeat mode feeds any button bound to it
        self.changed.emit()


class MainWindow(FramelessWindow):
    def __init__(self, service: MouseService) -> None:
        super().__init__("MouseMod")
        self.service = service
        self.resize(980, 720)
        self.setMinimumSize(860, 600)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)
        columns.addWidget(self._build_sidebar())
        columns.addWidget(self._build_content(), 1)

        self.body.addLayout(columns, 1)
        self.refresh_profiles()

    # -- sidebar -----------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 6, 14, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(section_label("Profiles"))
        header.addStretch()
        add_button = QPushButton("+")
        add_button.setObjectName("Ghost")
        add_button.setFixedWidth(28)
        add_button.setToolTip("New profile")
        add_button.setCursor(QCursor(Qt.PointingHandCursor))
        add_button.clicked.connect(self._add_profile)
        header.addWidget(add_button)
        layout.addLayout(header)

        self.profile_list = QListWidget()
        self.profile_list.setObjectName("ProfileList")
        self.profile_list.currentRowChanged.connect(self._on_profile_selected)
        self.profile_list.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self.profile_list, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        for label, slot, tip in (
            ("Clone", self._clone_profile, "Duplicate the selected profile"),
            ("Rename", self._rename_profile, "Rename the selected profile"),
            ("Delete", self._delete_profile, "Delete the selected profile"),
        ):
            button = QPushButton(label)
            button.setObjectName("Ghost")
            button.setToolTip(tip)
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.clicked.connect(slot)
            actions.addWidget(button)
        layout.addLayout(actions)

        layout.addWidget(divider())

        self.auto_switch = ToggleSwitch(self.service.store.auto_switch)
        self.auto_switch.toggled.connect(self._on_auto_switch)
        layout.addWidget(
            Field("Auto-switch", self.auto_switch,
                  "Apply a profile when its program takes focus")
        )

        return sidebar

    # -- content -----------------------------------------------------------

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("Content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 6, 20, 16)
        layout.setSpacing(16)

        layout.addWidget(self._build_device_header())

        self.editor = ProfileEditor()
        self.editor.changed.connect(self._on_editor_changed)
        layout.addWidget(self.editor, 1)

        layout.addWidget(self._build_footer())
        return content

    def _build_device_header(self) -> QWidget:
        card = Card()
        card.body().setContentsMargins(18, 14, 18, 14)

        row = QHBoxLayout()
        row.setSpacing(12)

        self.status_dot = StatusDot()
        row.addWidget(self.status_dot, 0, Qt.AlignVCenter)

        name_column = QVBoxLayout()
        name_column.setSpacing(1)
        self.device_name = QLabel("Searching for a mouse...")
        self.device_name.setObjectName("DeviceName")
        name_column.addWidget(self.device_name)
        self.device_link = QLabel("")
        self.device_link.setObjectName("Hint")
        name_column.addWidget(self.device_link)
        row.addLayout(name_column)

        row.addStretch()

        self.dpi_pill = Pill("-- DPI", "accent")
        row.addWidget(self.dpi_pill)
        self.rate_pill = Pill("-- Hz", "neutral")
        row.addWidget(self.rate_pill)
        self.battery_pill = Pill("--%", "neutral")
        row.addWidget(self.battery_pill)

        card.add_layout(row)
        return card

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.reset_button = QPushButton("Factory reset")
        self.reset_button.setObjectName("Danger")
        self.reset_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.reset_button.clicked.connect(self._factory_reset)
        layout.addWidget(self.reset_button)

        self.status = QLabel("Connecting...")
        self.status.setObjectName("StatusText")
        self.status.setMinimumWidth(120)
        self.status.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.status, 1)

        self.read_button = QPushButton("Read from mouse")
        self.read_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.read_button.clicked.connect(self._read_from_mouse)
        layout.addWidget(self.read_button)

        self.apply_button = QPushButton("Apply to mouse")
        self.apply_button.setObjectName("Primary")
        self.apply_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.apply_button.clicked.connect(self._apply_current)
        layout.addWidget(self.apply_button)

        return footer

    # -- device state ------------------------------------------------------

    def update_device_header(self, battery: dict | None) -> None:
        connected = self.service.connected
        self.status_dot.set_tone("success" if connected else "danger")

        if connected and self.service.mouse is not None:
            endpoint = self.service.mouse.endpoint
            self.device_name.setText(endpoint.product)
            self.device_link.setText(
                "Connected over the 8K receiver" if endpoint.is_dongle
                else "Connected over USB"
            )
        else:
            self.device_name.setText("No mouse connected")
            self.device_link.setText("Plug in the mouse or its receiver")

        settings = self.service.current
        if settings and settings.dpi_stages:
            stage = min(settings.active_stage, len(settings.dpi_stages) - 1)
            self.dpi_pill.setText(f"{settings.dpi_stages[stage]} DPI")
            self.rate_pill.setText(f"{settings.report_rate_hz} Hz")
        else:
            self.dpi_pill.setText("-- DPI")
            self.rate_pill.setText("-- Hz")

        if battery and battery.get("percent") is not None:
            percent = battery["percent"]
            tone = "danger" if percent <= 15 else "warning" if percent <= 35 else "success"
            suffix = " charging" if battery.get("charging") else ""
            self.battery_pill.setText(f"{percent}%{suffix}")
            self.battery_pill.set_tone(tone)
        else:
            self.battery_pill.setText("--%")
            self.battery_pill.set_tone("neutral")

    # -- profile list ------------------------------------------------------

    def refresh_profiles(self, select: str | None = None) -> None:
        target = select
        if target is None:
            current = self.current_profile()
            target = current.name if current else None

        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for profile in self.service.store.profiles:
            item = QListWidgetItem()
            row = ProfileRow(
                profile.name,
                ", ".join(profile.applications) or "No application bound",
                profile is self.service.active_profile,
            )
            item.setSizeHint(row.sizeHint())
            self.profile_list.addItem(item)
            self.profile_list.setItemWidget(item, row)
        self.profile_list.blockSignals(False)

        row_index = 0
        if target:
            for index, profile in enumerate(self.service.store.profiles):
                if profile.name == target:
                    row_index = index
                    break
        if self.service.store.profiles:
            self.profile_list.setCurrentRow(row_index)
            self.editor.load(self.current_profile())
        else:
            self.editor.load(None)

    def current_profile(self) -> Profile | None:
        row = self.profile_list.currentRow()
        profiles = self.service.store.profiles
        return profiles[row] if 0 <= row < len(profiles) else None

    def _on_profile_selected(self, _row: int) -> None:
        self.editor.load(self.current_profile())

    def _add_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "New profile", "Profile name")
        if not ok or not name.strip():
            return
        profile = Profile(name=name.strip())
        if self.service.current is not None:
            profile.settings = self.service.current.copy()
        self.service.store.add(profile)
        self.service.store.save()
        self.refresh_profiles(select=profile.name)

    def _clone_profile(self) -> None:
        source = self.current_profile()
        if source is None:
            return
        name, ok = QInputDialog.getText(
            self, "Clone profile", "Profile name", text=f"{source.name} copy"
        )
        if not ok or not name.strip():
            return
        clone = Profile(
            name=name.strip(),
            settings=source.settings.copy(),
            applications=list(source.applications),
        )
        self.service.store.add(clone)
        self.service.store.save()
        self.refresh_profiles(select=clone.name)

    def _rename_profile(self) -> None:
        profile = self.current_profile()
        if profile is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename profile", "Profile name", text=profile.name
        )
        if not ok or not name.strip():
            return
        self.service.store.rename(profile.name, name.strip())
        self.service.store.save()
        self.service.reload_hotkeys()
        self.refresh_profiles(select=name.strip())

    def _delete_profile(self) -> None:
        profile = self.current_profile()
        if profile is None:
            return
        confirm = QMessageBox.question(
            self, "Delete profile", f"Delete the profile '{profile.name}'?"
        )
        if confirm != QMessageBox.Yes:
            return
        self.service.store.remove(profile.name)
        self.service.store.save()
        self.service.reload_hotkeys()
        self.refresh_profiles()

    # -- actions -----------------------------------------------------------

    def _on_editor_changed(self) -> None:
        self.service.store.save()

    def _on_auto_switch(self, enabled: bool) -> None:
        self.service.set_auto_switch(enabled)
        self.set_status(
            "Automatic profile switching is on." if enabled
            else "Automatic profile switching is off."
        )

    def _apply_current(self) -> None:
        profile = self.current_profile()
        if profile is None:
            return
        self.editor.collect()
        self.service.store.save()
        self.service.reload_hotkeys()
        if self.service.apply_profile(profile, force=True):
            self.set_status(f"Applied '{profile.name}' to the mouse.")
            self.refresh_profiles(select=profile.name)
        else:
            self.set_status("Could not apply the profile. Is the mouse connected?")

    def _read_from_mouse(self) -> None:
        profile = self.current_profile()
        settings = self.service.refresh()
        if settings is None:
            self.set_status("Could not read the mouse.")
            return
        if profile is not None:
            profile.settings = settings.copy()
            self.service.store.save()
            self.editor.load(profile)
        self.set_status("Loaded the live configuration from the mouse.")

    def _factory_reset(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Factory reset",
            "Reset the mouse itself to its factory defaults?\n\n"
            "This clears the on-device configuration and macros. Your saved "
            "profiles on this PC are kept and can be re-applied afterwards.",
        )
        if confirm != QMessageBox.Yes:
            return
        if not self.service.factory_reset():
            self.set_status("Factory reset failed. Is the mouse connected?")
            return
        self.set_status("The mouse was reset to its factory defaults.")
        profile = self.current_profile()
        if profile is not None and self.service.current is not None:
            self.editor.load(profile)

    def set_status(self, message: str) -> None:
        """Keep the footer one line tall; the full text lives in the tooltip."""
        metrics = self.status.fontMetrics()
        available = max(120, self.status.width())
        self.status.setText(metrics.elidedText(message, Qt.ElideRight, available))
        self.status.setToolTip(message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Closing hides to tray; quitting happens from the tray menu."""
        event.ignore()
        self.hide()


class TrayApp:
    """Wires the service, the window and the tray icon together."""

    def __init__(self) -> None:
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("MouseMod")
        self.app.setApplicationDisplayName("MouseMod")
        self.app.setWindowIcon(app_icon())
        self.app.setStyleSheet(STYLESHEET)
        self.app.setQuitOnLastWindowClosed(False)

        self.service = MouseService()
        self.bridge = EventBridge()
        self.bridge.event.connect(self._on_event)
        self.service.subscribe(
            lambda name, payload: self.bridge.event.emit(name, payload)
        )

        self.window = MainWindow(self.service)
        self.battery_percent: int | None = None
        self.battery_info: dict | None = None

        self.tray = QSystemTrayIcon(battery_icon(None, False))
        self.tray.setToolTip("MouseMod")
        self.tray.activated.connect(self._on_tray_activated)
        self.menu = QMenu()
        self.menu.setStyleSheet(STYLESHEET)
        self.tray.setContextMenu(self.menu)
        self.tray.show()

        self.service.connect()
        self.service.start_automation()
        self._rebuild_menu()
        self._poll_battery()

        self.battery_timer = QTimer()
        self.battery_timer.timeout.connect(self._poll_battery)
        self.battery_timer.start(60_000)

    # -- tray --------------------------------------------------------------

    def _rebuild_menu(self) -> None:
        self.menu.clear()

        header = self.menu.addAction(self._status_text())
        header.setEnabled(False)
        self.menu.addSeparator()

        for profile in self.service.store.profiles:
            action = QAction(profile.name, self.menu)
            action.setCheckable(True)
            action.setChecked(profile is self.service.active_profile)
            action.triggered.connect(
                lambda _checked=False, name=profile.name: self._apply_named(name)
            )
            self.menu.addAction(action)

        self.menu.addSeparator()
        cycle = self.menu.addAction("Next DPI stage")
        cycle.triggered.connect(lambda: self.service.cycle_dpi(1))

        show = self.menu.addAction("Open MouseMod")
        show.triggered.connect(self._show_window)

        self.menu.addSeparator()
        quit_action = self.menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

    def _status_text(self) -> str:
        if not self.service.connected:
            return "Mouse not connected"
        parts = [self.service.mouse.endpoint.product if self.service.mouse else "Mouse"]
        if self.battery_percent is not None:
            parts.append(f"{self.battery_percent}%")
        settings = self.service.current
        if settings and settings.dpi_stages:
            stage = min(settings.active_stage, len(settings.dpi_stages) - 1)
            parts.append(f"{settings.dpi_stages[stage]} DPI")
        return "   ".join(parts)

    def _refresh_tray(self) -> None:
        self.tray.setIcon(battery_icon(self.battery_percent, self.service.connected))
        self.tray.setToolTip(f"MouseMod - {self._status_text()}")
        self._rebuild_menu()
        self.window.update_device_header(self.battery_info)

    def _poll_battery(self) -> None:
        self.battery_info = self.service.battery()
        self.battery_percent = (
            self.battery_info["percent"] if self.battery_info else None
        )
        self._refresh_tray()

    def _apply_named(self, name: str) -> None:
        if self.service.apply_profile_named(name):
            self.window.set_status(f"Applied '{name}'.")
            self.window.refresh_profiles(select=name)
        self._refresh_tray()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _quit(self) -> None:
        self.service.shutdown()
        self.app.quit()

    # -- service events ----------------------------------------------------

    def _on_event(self, name: str, payload: object) -> None:
        if name == "connected":
            self.window.set_status(f"Connected to {payload.label}.")
            self.window.refresh_profiles()
        elif name == "disconnected":
            self.window.set_status(f"Mouse not reachable: {payload}")
        elif name == "profile":
            self.window.set_status(f"Active profile: {payload.name}")
        elif name == "error":
            self.window.set_status(str(payload))
        self._refresh_tray()

    def run(self, show_window: bool = True) -> int:
        if show_window:
            self._show_window()
        return self.app.exec()


def main(show_window: bool = True) -> int:
    return TrayApp().run(show_window=show_window)


if __name__ == "__main__":
    sys.exit(main())
