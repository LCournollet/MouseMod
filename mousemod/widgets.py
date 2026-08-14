"""Custom widgets that Qt does not ship: frameless chrome, toggles, cards.

Everything here is painted from the palette in `theme`, so restyling the app
means editing tokens rather than chasing colours through the UI code.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .theme import Color, Radius


class Card(QFrame):
    """A titled surface panel."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(14)

        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            self._layout.addWidget(label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


def divider_line() -> QFrame:
    """A one-pixel horizontal rule."""
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.HLine)
    return line


class Field(QWidget):
    """A labelled row: description on the left, control on the right."""

    def __init__(self, label: str, control: QWidget, hint: str | None = None):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)

        title = QLabel(label)
        title.setObjectName("FieldLabel")
        text_column.addWidget(title)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("Hint")
            hint_label.setWordWrap(True)
            text_column.addWidget(hint_label)

        row.addLayout(text_column, 1)
        control.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        row.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)


class ToggleSwitch(QWidget):
    """An animated on/off switch, API-compatible enough with QCheckBox."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._checked = checked
        self._offset = 1.0 if checked else 0.0
        self.setFixedSize(44, 24)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    # -- state -------------------------------------------------------------

    def isChecked(self) -> bool:  # noqa: N802 - mirrors QCheckBox
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()
        self.toggled.emit(checked)

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, get_offset, set_offset)

    # -- interaction -------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.setChecked(not self._checked)
        event.accept()

    # -- painting ----------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        enabled = self.isEnabled()
        off = QColor(Color.SURFACE_3)
        on = QColor(Color.ACCENT)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * self._offset),
            int(off.green() + (on.green() - off.green()) * self._offset),
            int(off.blue() + (on.blue() - off.blue()) * self._offset),
        )
        if not enabled:
            track.setAlpha(90)

        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), 12, 12)

        if self._offset < 0.99:
            painter.setPen(QPen(QColor(Color.BORDER_STRONG), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)

        knob = QColor("#FFFFFF" if enabled else "#9AA1AE")
        painter.setPen(Qt.NoPen)
        painter.setBrush(knob)
        travel = self.width() - 20 - 4
        x = 3 + travel * self._offset
        painter.drawEllipse(QRect(int(x), 3, 18, 18))


class NumberInput(QSpinBox):
    """A spin box with painted chevrons instead of Qt's native arrows.

    The stylesheet triangle trick renders inconsistently at small sizes, so the
    native buttons are dropped and the stepper is drawn and hit-tested here.
    """

    ARROW_WIDTH = 22

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._hover: str | None = None
        self.setMouseTracking(True)

    def _zone(self, position) -> str | None:
        if position.x() < self.width() - self.ARROW_WIDTH:
            return None
        return "up" if position.y() < self.height() / 2 else "down"

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        zone = self._zone(event.position())
        if zone != self._hover:
            self._hover = zone
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        zone = self._zone(event.position())
        if zone == "up":
            self.stepUp()
            event.accept()
            return
        if zone == "down":
            self.stepDown()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        x = self.width() - self.ARROW_WIDTH / 2 - 4
        half = self.height() / 2
        # direction +1 draws a chevron pointing up, -1 pointing down.
        for zone, centre_y, direction in (
            ("up", half * 0.62, 1),
            ("down", half * 1.38, -1),
        ):
            active = self._hover == zone
            painter.setPen(
                QPen(QColor(Color.TEXT if active else Color.TEXT_MUTE), 1.4)
            )
            span, height = 3.5, 2.2
            painter.drawLine(
                int(x - span), int(centre_y + direction * height / 2),
                int(x), int(centre_y - direction * height / 2),
            )
            painter.drawLine(
                int(x), int(centre_y - direction * height / 2),
                int(x + span), int(centre_y + direction * height / 2),
            )


class Select(QComboBox):
    """A combo box with a painted chevron, matching NumberInput."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        view = self.view()
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(Color.TEXT_MUTE), 1.4))

        x = self.width() - 15
        y = self.height() / 2
        span = 4
        painter.drawLine(int(x - span), int(y - 1.5), int(x), int(y + 2.0))
        painter.drawLine(int(x), int(y + 2.0), int(x + span), int(y - 1.5))


class Pill(QLabel):
    """A small rounded status chip."""

    def __init__(self, text: str = "", tone: str = "neutral"):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        palette = {
            "neutral": (Color.SURFACE_3, Color.TEXT_DIM),
            "accent": (Color.ACCENT_SOFT, Color.ACCENT),
            "success": ("#12281E", Color.SUCCESS),
            "warning": ("#33270A", Color.WARNING),
            "danger": (Color.DANGER_SOFT, Color.DANGER),
        }
        background, foreground = palette.get(tone, palette["neutral"])
        self.setStyleSheet(
            f"background: {background}; color: {foreground};"
            f"border-radius: 10px; padding: 3px 10px;"
            f"font-size: 12px; font-weight: 600;"
        )


class StatusDot(QWidget):
    """A coloured connection indicator."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._color = QColor(Color.TEXT_MUTE)

    def set_tone(self, tone: str) -> None:
        self._color = QColor(
            {"success": Color.SUCCESS, "danger": Color.DANGER,
             "warning": Color.WARNING}.get(tone, Color.TEXT_MUTE)
        )
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect())


class SegmentedControl(QWidget):
    """A pill-shaped tab strip; emits the index of the selected segment."""

    changed = Signal(int)

    def __init__(self, labels: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._current = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.clicked.connect(lambda _c=False, i=index: self.set_current(i))
            self._buttons.append(button)
            layout.addWidget(button)

        self.setStyleSheet(
            f"""
            SegmentedControl {{
                background: {Color.SURFACE};
                border: 1px solid {Color.BORDER};
                border-radius: {Radius.INPUT + 2}px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {Radius.INPUT}px;
                padding: 7px 18px;
                color: {Color.TEXT_DIM};
                font-weight: 500;
            }}
            QPushButton:hover {{ color: {Color.TEXT}; }}
            QPushButton:checked {{
                background: {Color.SURFACE_3};
                color: {Color.TEXT};
                font-weight: 600;
            }}
            """
        )
        self.set_current(0)

    def set_current(self, index: int) -> None:
        self._current = index
        for position, button in enumerate(self._buttons):
            button.setChecked(position == index)
        self.changed.emit(index)

    def current(self) -> int:
        return self._current


class ProfileRow(QWidget):
    """The contents of one row in the profile list."""

    def __init__(self, name: str, subtitle: str, active: bool):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        marker = QWidget()
        marker.setFixedWidth(3)
        marker.setMinimumHeight(28)
        marker.setStyleSheet(
            f"background: {Color.ACCENT if active else 'transparent'};"
            f"border-radius: 2px;"
        )
        layout.addWidget(marker)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)

        title = QLabel(name)
        title.setStyleSheet(
            f"font-weight: {'600' if active else '500'}; font-size: 13px;"
            f"color: {Color.TEXT if active else Color.TEXT_DIM};"
        )
        text_column.addWidget(title)

        if subtitle:
            caption = QLabel(subtitle)
            caption.setStyleSheet(f"color: {Color.TEXT_MUTE}; font-size: 11px;")
            text_column.addWidget(caption)

        layout.addLayout(text_column, 1)

        if active:
            dot = StatusDot()
            dot.set_tone("success")
            layout.addWidget(dot, 0, Qt.AlignVCenter)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 52)


class WindowButton(QPushButton):
    """Minimise/close button whose glyph is painted, not typed.

    Drawing the glyph avoids depending on the Segoe MDL2 Assets font being
    present and correctly hinted.
    """

    def __init__(self, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(34, 28)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._hovered = False
        self.setStyleSheet("background: transparent; border: none;")

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(
                QColor(Color.DANGER) if self.kind == "close" else QColor(Color.SURFACE_3)
            )
            painter.drawRoundedRect(self.rect(), 6, 6)

        colour = QColor("#FFFFFF") if (self._hovered and self.kind == "close") \
            else QColor(Color.TEXT if self._hovered else Color.TEXT_DIM)
        painter.setPen(QPen(colour, 1.3))

        centre = self.rect().center()
        span = 5
        if self.kind == "close":
            painter.drawLine(centre.x() - span, centre.y() - span,
                             centre.x() + span, centre.y() + span)
            painter.drawLine(centre.x() + span, centre.y() - span,
                             centre.x() - span, centre.y() + span)
        else:
            painter.drawLine(centre.x() - span, centre.y() + 1,
                             centre.x() + span, centre.y() + 1)


class TitleBar(QWidget):
    """Custom window chrome: title, subtitle and the window buttons."""

    minimise_requested = Signal()
    close_requested = Signal()

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(46)
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 10, 0)
        layout.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(app_mark(20))
        layout.addWidget(mark)

        name = QLabel(title)
        name.setObjectName("AppTitle")
        layout.addWidget(name)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("AppSubtitle")
        layout.addWidget(self.subtitle)

        layout.addStretch()

        minimise = WindowButton("minimise")
        minimise.setToolTip("Minimise")
        minimise.clicked.connect(self.minimise_requested.emit)
        layout.addWidget(minimise)

        close = WindowButton("close")
        close.setToolTip("Close to tray")
        close.clicked.connect(self.close_requested.emit)
        layout.addWidget(close)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(f"  {text}" if text else "")

    # Dragging the bar moves the frameless window.
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            window = self.window()
            self._drag_offset = event.globalPosition().toPoint() - window.pos()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        event.accept()


class FramelessWindow(QWidget):
    """Rounded, shadowed, borderless window with edge resizing.

    Qt cannot round a native frame, so the frame is dropped and redrawn: a
    translucent top-level hosts a rounded `#Root` child, and hit-testing on the
    outer margin restores resize handles.
    """

    RESIZE_MARGIN = 6

    def __init__(self, title: str = "MouseMod"):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        # Still needed even without native chrome: the taskbar and Alt+Tab
        # read the window title.
        self.setWindowTitle(title)

        from .theme import SHADOW_MARGIN

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )

        self.root = QWidget()
        self.root.setObjectName("Root")
        self.root.setMouseTracking(True)
        outer.addWidget(self.root)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 190))
        self.root.setGraphicsEffect(shadow)

        self.body = QVBoxLayout(self.root)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)

        self.title_bar = TitleBar(title)
        self.title_bar.minimise_requested.connect(self.showMinimized)
        self.title_bar.close_requested.connect(self.close)
        self.body.addWidget(self.title_bar)

        self._resize_edge: str | None = None
        self._resize_origin: QPoint | None = None
        self._resize_geometry: QRect | None = None
        self._cursor_edge: str | None = None

        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

    # -- resizing ----------------------------------------------------------

    def _edge_at(self, position: QPoint) -> str | None:
        """Which resize edge a point falls on, if any.

        The band is kept inside the transparent shadow margin, which the window
        owns outright. Reaching further in would put the band under child
        widgets, which swallow the mouse events the resize needs.
        """
        from .theme import SHADOW_MARGIN

        margin = min(SHADOW_MARGIN, self.RESIZE_MARGIN + 2)
        x, y, width, height = position.x(), position.y(), self.width(), self.height()

        left = x <= margin
        right = x >= width - margin
        top = y <= margin
        bottom = y >= height - margin

        if top and left:
            return "topleft"
        if top and right:
            return "topright"
        if bottom and left:
            return "bottomleft"
        if bottom and right:
            return "bottomright"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    @staticmethod
    def _cursor_for(edge: str | None):
        return {
            "left": Qt.SizeHorCursor,
            "right": Qt.SizeHorCursor,
            "top": Qt.SizeVerCursor,
            "bottom": Qt.SizeVerCursor,
            "topleft": Qt.SizeFDiagCursor,
            "bottomright": Qt.SizeFDiagCursor,
            "topright": Qt.SizeBDiagCursor,
            "bottomleft": Qt.SizeBDiagCursor,
        }.get(edge, Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_geometry = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._resize_edge and self._resize_origin and self._resize_geometry:
            delta = event.globalPosition().toPoint() - self._resize_origin
            rect = QRect(self._resize_geometry)
            minimum = self.minimumSize()

            if "left" in self._resize_edge:
                rect.setLeft(min(rect.left() + delta.x(), rect.right() - minimum.width()))
            if "right" in self._resize_edge:
                rect.setRight(max(rect.right() + delta.x(), rect.left() + minimum.width()))
            if "top" in self._resize_edge:
                rect.setTop(min(rect.top() + delta.y(), rect.bottom() - minimum.height()))
            if "bottom" in self._resize_edge:
                rect.setBottom(max(rect.bottom() + delta.y(), rect.top() + minimum.height()))

            self.setGeometry(rect)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._resize_edge = None
        self._resize_origin = None
        self._resize_geometry = None
        self._apply_cursor(None)
        super().mouseReleaseEvent(event)

    # -- cursor ------------------------------------------------------------

    def _apply_cursor(self, edge: str | None) -> None:
        """Set the resize cursor, or give it back to whatever is underneath.

        unsetCursor() rather than an explicit arrow: children with a cursor of
        their own (buttons, text fields) must keep it.
        """
        if edge == self._cursor_edge:
            return
        self._cursor_edge = edge
        if edge is None:
            self.unsetCursor()
        else:
            self.setCursor(self._cursor_for(edge))

    def _update_cursor_from(self, global_position: QPoint) -> None:
        if self._resize_edge:
            return
        local = self.mapFromGlobal(global_position)
        edge = self._edge_at(local) if self.rect().contains(local) else None
        self._apply_cursor(edge)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """Track the pointer across the whole window.

        Child widgets consume their own mouse moves, so without an
        application-level filter the resize cursor set at an edge would never
        be cleared once the pointer moved inland - and every child without its
        own cursor would inherit it.
        """
        if event.type() == QEvent.MouseMove and self.isVisible():
            try:
                self._update_cursor_from(event.globalPosition().toPoint())
            except (AttributeError, RuntimeError):
                pass
        return False

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self._resize_edge:
            self._apply_cursor(None)
        super().leaveEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._apply_cursor(None)
        super().closeEvent(event)


# --- iconography --------------------------------------------------------------


def _draw_mouse_glyph(painter: QPainter, size: int, body: QColor, accent: QColor) -> None:
    """A mouse silhouette with a lit scroll wheel."""
    unit = size / 32
    painter.setPen(Qt.NoPen)
    painter.setBrush(body)

    path = QPainterPath()
    path.addRoundedRect(9 * unit, 4 * unit, 14 * unit, 24 * unit, 7 * unit, 8 * unit)
    painter.drawPath(path)

    painter.setBrush(accent)
    painter.drawRoundedRect(
        QRect(int(15 * unit), int(9 * unit), int(2.4 * unit), int(6 * unit)),
        int(1.2 * unit),
        int(1.2 * unit),
    )


def app_mark(size: int = 32) -> QPixmap:
    """The MouseMod glyph, drawn at runtime."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    _draw_mouse_glyph(painter, size, QColor(Color.TEXT), QColor(Color.ACCENT))
    painter.end()
    return pixmap


def app_icon(size: int = 256) -> QIcon:
    """Square app icon: rounded accent tile with the glyph knocked out."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#161A21"))
    painter.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)

    painter.setPen(QPen(QColor(Color.BORDER_STRONG), max(1, size // 96)))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(
        0, 0, size - 1, size - 1, size * 0.22, size * 0.22
    )

    _draw_mouse_glyph(painter, size, QColor("#E8EAED"), QColor(Color.ACCENT))
    painter.end()
    return QIcon(pixmap)


def battery_icon(percent: int | None, connected: bool) -> QIcon:
    """Tray icon: a rounded tile carrying the battery figure."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    if not connected:
        tone, text = QColor("#4B5563"), "--"
    elif percent is None:
        tone, text = QColor(Color.ACCENT), "?"
    elif percent <= 15:
        tone, text = QColor(Color.DANGER), str(percent)
    elif percent <= 35:
        tone, text = QColor(Color.WARNING), str(percent)
    else:
        tone, text = QColor(Color.SUCCESS), str(percent)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#161A21"))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 15, 15)

    painter.setPen(QPen(tone, 3))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(2, 2, size - 5, size - 5, 14, 14)

    painter.setPen(QColor(Color.TEXT))
    font = QFont("Segoe UI")
    font.setPixelSize(30 if len(text) > 2 else 34)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
    painter.end()

    return QIcon(pixmap)
