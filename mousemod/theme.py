"""Design tokens and the application stylesheet.

One dark theme, defined once here so every widget pulls from the same palette
instead of hard-coding colours at the call site.
"""

from __future__ import annotations


class Color:
    # Surfaces, darkest to lightest
    BG = "#0E1013"
    SURFACE = "#15181D"
    SURFACE_2 = "#1B1F26"
    SURFACE_3 = "#222731"

    # Lines
    BORDER = "#252A33"
    BORDER_STRONG = "#323945"

    # Type
    TEXT = "#E8EAED"
    TEXT_DIM = "#9AA1AE"
    TEXT_MUTE = "#666E7C"

    # Meaning
    ACCENT = "#5B8DEF"
    ACCENT_HOVER = "#7BA4F5"
    ACCENT_PRESSED = "#4577DB"
    ACCENT_SOFT = "#1E2A44"
    DANGER = "#E5484D"
    DANGER_SOFT = "#3B1E22"
    SUCCESS = "#30A46C"
    WARNING = "#F5A524"


class Radius:
    WINDOW = 14
    CARD = 10
    INPUT = 8
    PILL = 999


#: Margin reserved around the window for the drop shadow.
SHADOW_MARGIN = 14

FONT_FAMILY = '"Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif'


STYLESHEET = f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: {Color.TEXT};
}}

QWidget#Root {{
    background: {Color.BG};
    border: 1px solid {Color.BORDER};
    border-radius: {Radius.WINDOW}px;
}}

/* ---- title bar ---- */

QWidget#TitleBar {{
    background: transparent;
}}
QLabel#AppTitle {{
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
QLabel#AppSubtitle {{
    color: {Color.TEXT_MUTE};
    font-size: 12px;
}}

QPushButton#WinButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {Color.TEXT_DIM};
    font-size: 15px;
    font-family: "Segoe MDL2 Assets";
    min-width: 34px;
    max-width: 34px;
    min-height: 28px;
    max-height: 28px;
}}
QPushButton#WinButton:hover {{
    background: {Color.SURFACE_3};
    color: {Color.TEXT};
}}
QPushButton#WinButtonClose:hover {{
    background: {Color.DANGER};
    color: #ffffff;
}}

/* ---- structure ---- */

QWidget#Sidebar {{
    background: {Color.SURFACE};
    border: none;
    border-right: 1px solid {Color.BORDER};
}}
QWidget#Content {{
    background: transparent;
}}
QFrame#Card {{
    background: {Color.SURFACE};
    border: 1px solid {Color.BORDER};
    border-radius: {Radius.CARD}px;
}}
QFrame#Divider {{
    background: {Color.BORDER};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

QLabel#SectionTitle {{
    font-size: 11px;
    font-weight: 700;
    color: {Color.TEXT_MUTE};
    letter-spacing: 1.1px;
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 600;
}}
QLabel#FieldLabel {{
    color: {Color.TEXT_DIM};
}}
QLabel#Hint {{
    color: {Color.TEXT_MUTE};
    font-size: 12px;
}}
QLabel#StatusText {{
    color: {Color.TEXT_DIM};
    font-size: 12px;
}}
QLabel#DeviceName {{
    font-size: 15px;
    font-weight: 600;
}}

/* ---- inputs ---- */

QSpinBox, QLineEdit, QComboBox {{
    background: {Color.SURFACE_2};
    border: 1px solid {Color.BORDER};
    border-radius: {Radius.INPUT}px;
    padding: 6px 10px;
    min-height: 20px;
    selection-background-color: {Color.ACCENT};
}}
QSpinBox:hover, QLineEdit:hover, QComboBox:hover {{
    border-color: {Color.BORDER_STRONG};
}}
QSpinBox:focus, QLineEdit:focus, QComboBox:focus {{
    border-color: {Color.ACCENT};
}}
QSpinBox:disabled, QLineEdit:disabled, QComboBox:disabled {{
    color: {Color.TEXT_MUTE};
    background: {Color.SURFACE};
}}

/* Steppers and chevrons are painted by NumberInput / Select, not by Qt. */
QSpinBox {{
    padding-right: 26px;
}}
QComboBox {{
    padding-right: 26px;
}}
QComboBox::drop-down {{
    border: none;
    width: 0px;
}}
QComboBox QAbstractItemView {{
    background: {Color.SURFACE_2};
    border: 1px solid {Color.BORDER_STRONG};
    border-radius: {Radius.INPUT}px;
    padding: 4px;
    outline: none;
    selection-background-color: {Color.ACCENT_SOFT};
    selection-color: {Color.TEXT};
}}

/* ---- buttons ---- */

QPushButton {{
    background: {Color.SURFACE_2};
    border: 1px solid {Color.BORDER};
    border-radius: {Radius.INPUT}px;
    padding: 8px 16px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {Color.SURFACE_3};
    border-color: {Color.BORDER_STRONG};
}}
QPushButton:pressed {{
    background: {Color.SURFACE};
}}
QPushButton:disabled {{
    color: {Color.TEXT_MUTE};
    background: {Color.SURFACE};
}}

QPushButton#Primary {{
    background: {Color.ACCENT};
    border: 1px solid {Color.ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {Color.ACCENT_HOVER};
    border-color: {Color.ACCENT_HOVER};
}}
QPushButton#Primary:pressed {{
    background: {Color.ACCENT_PRESSED};
}}
QPushButton#Primary:disabled {{
    background: {Color.SURFACE_2};
    border-color: {Color.BORDER};
    color: {Color.TEXT_MUTE};
}}

QPushButton#Danger {{
    background: transparent;
    border: 1px solid {Color.BORDER};
    color: {Color.TEXT_DIM};
}}
QPushButton#Danger:hover {{
    background: {Color.DANGER_SOFT};
    border-color: {Color.DANGER};
    color: {Color.DANGER};
}}

QPushButton#Ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {Color.TEXT_DIM};
    padding: 6px 10px;
}}
QPushButton#Ghost:hover {{
    background: {Color.SURFACE_2};
    color: {Color.TEXT};
}}

/* ---- profile list ---- */

QListWidget#ProfileList {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget#ProfileList::item {{
    border-radius: {Radius.INPUT}px;
    margin: 2px 0px;
    padding: 0px;
}}
QListWidget#ProfileList::item:selected {{
    background: transparent;
}}

/* ---- scrollbars ---- */

QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {Color.BORDER_STRONG};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {Color.TEXT_MUTE};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
    background: transparent;
}}
QScrollBar:horizontal {{ height: 0px; }}

/* ---- menus, dialogs, tooltips ---- */

QMenu {{
    background: {Color.SURFACE_2};
    border: 1px solid {Color.BORDER_STRONG};
    border-radius: {Radius.CARD}px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 26px 7px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {Color.ACCENT_SOFT};
}}
QMenu::item:disabled {{
    color: {Color.TEXT_MUTE};
}}
QMenu::separator {{
    height: 1px;
    background: {Color.BORDER};
    margin: 5px 8px;
}}
QMenu::indicator {{
    width: 14px;
    margin-left: 8px;
}}

QToolTip {{
    background: {Color.SURFACE_3};
    border: 1px solid {Color.BORDER_STRONG};
    border-radius: 6px;
    padding: 5px 8px;
    color: {Color.TEXT};
}}

QDialog, QMessageBox, QInputDialog {{
    background: {Color.SURFACE};
}}
QMessageBox QLabel, QInputDialog QLabel {{
    color: {Color.TEXT};
}}
"""
