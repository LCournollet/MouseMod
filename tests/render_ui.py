"""Render each page of the window to PNG so the design can be reviewed.

Uses the native platform so real fonts are applied, but positions the window
off-screen and shows it without activating, so nothing steals focus from
whatever is in the foreground.

Run: python -m tests.render_ui
"""

import sys

sys.path.insert(0, ".")

from pathlib import Path  # noqa: E402

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402

OUT = Path("h:/MouseMod/tests/_render")
PAGES = ["sensor", "buttons", "macros", "performance", "automation"]


def settle(times: int = 8) -> None:
    for _ in range(times):
        QCoreApplication.processEvents()


def main() -> int:
    from mousemod.ui import TrayApp

    OUT.mkdir(parents=True, exist_ok=True)
    app = TrayApp()
    window = app.window
    window.setAttribute(Qt.WA_ShowWithoutActivating, True)
    window.resize(980, 720)
    window.move(-4000, -4000)
    window.show()
    settle(12)

    for index, name in enumerate(PAGES):
        window.editor.nav.set_current(index)
        settle(8)
        path = OUT / f"{index + 1}-{name}.png"
        window.grab().save(str(path))
        print(f"  wrote {path}")

    window.hide()
    app.service.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
