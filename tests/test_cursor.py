"""The frameless window must not leave a resize cursor stuck over its content.

Regression test: moving from a window edge onto a child widget used to keep the
horizontal-resize cursor, which every child without its own cursor inherited.

Run: python -m tests.test_cursor
"""

import sys

sys.path.insert(0, ".")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mousemod.theme import SHADOW_MARGIN  # noqa: E402
from mousemod.widgets import FramelessWindow  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = FramelessWindow("Cursor test")
    window.resize(600, 400)
    window.setAttribute(Qt.WA_ShowWithoutActivating, True)
    window.move(-4000, -4000)
    window.show()

    failures = []

    def check(label, point, expected_edge):
        edge = window._edge_at(point)
        ok = edge == expected_edge
        print(f"  {label:<28} {str(point.x()) + ',' + str(point.y()):<10} "
              f"-> {str(edge):<12} {'ok' if ok else f'expected {expected_edge}'}")
        if not ok:
            failures.append(label)

    width, height = window.width(), window.height()
    print("== edge detection ==")
    check("left edge", QPoint(1, height // 2), "left")
    check("right edge", QPoint(width - 1, height // 2), "right")
    check("top edge", QPoint(width // 2, 1), "top")
    check("bottom edge", QPoint(width // 2, height - 1), "bottom")
    check("top-left corner", QPoint(1, 1), "topleft")
    check("bottom-right corner", QPoint(width - 1, height - 1), "bottomright")

    # The band must stay inside the transparent shadow margin: anything beyond
    # it belongs to the content, where children eat the mouse events.
    check("just inside the content", QPoint(SHADOW_MARGIN + 4, height // 2), None)
    check("middle of the window", QPoint(width // 2, height // 2), None)
    check("over the title bar", QPoint(width // 2, SHADOW_MARGIN + 20), None)

    print("\n== cursor lifecycle ==")
    window._update_cursor_from(window.mapToGlobal(QPoint(1, height // 2)))
    at_edge = window.cursor().shape()
    print(f"  on the left edge      -> {at_edge}")
    if at_edge != Qt.SizeHorCursor:
        failures.append("edge cursor")

    window._update_cursor_from(window.mapToGlobal(QPoint(width // 2, height // 2)))
    inland = window.cursor().shape()
    print(f"  moved into the content-> {inland}")
    if inland == Qt.SizeHorCursor:
        failures.append("cursor stuck after moving inland")

    window._update_cursor_from(window.mapToGlobal(QPoint(-50, -50)))
    outside = window.cursor().shape()
    print(f"  pointer outside       -> {outside}")
    if outside == Qt.SizeHorCursor:
        failures.append("cursor stuck when outside")

    print("\n== child widgets keep their own cursor ==")
    from mousemod.widgets import WindowButton

    buttons = window.title_bar.findChildren(WindowButton)
    print(f"  window buttons found: {len(buttons)}")
    window._update_cursor_from(window.mapToGlobal(QPoint(1, height // 2)))
    for button in buttons:
        if button.cursor().shape() != Qt.PointingHandCursor:
            failures.append("window button lost its pointing-hand cursor")
            break
    else:
        print("  they still show the pointing hand while an edge is hovered  ok")

    window.hide()
    print("\n" + ("CURSOR BEHAVIOUR OK" if not failures
                  else "FAILED: " + ", ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
