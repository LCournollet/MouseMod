"""Build the whole UI offscreen and exercise it without a display.

Run: python -m tests.test_ui_smoke
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtCore import QTimer  # noqa: E402

from mousemod.hotkeys import HotkeyError, parse  # noqa: E402
from mousemod.profiles import Profile, ProfileStore  # noqa: E402
from mousemod.settings import Settings  # noqa: E402
from mousemod.watcher import foreground_executable  # noqa: E402


def test_hotkey_parsing():
    print("== hotkeys ==")
    assert parse("ctrl+alt+d") == (0x0002 | 0x0001, ord("D"))
    assert parse("shift+f5") == (0x0004, 0x74)
    assert parse("win+numpad3") == (0x0008, 0x63)
    for bad in ("", "ctrl+", "ctrl+a+b", "ctrl+nope"):
        try:
            parse(bad)
        except HotkeyError:
            continue
        raise AssertionError(f"{bad!r} should have been rejected")
    print("  parsing and rejection ok")


def test_profile_roundtrip(tmp_path="h:/MouseMod/tests/_tmp_profiles.json"):
    print("\n== profiles ==")
    from pathlib import Path

    path = Path(tmp_path)
    store = ProfileStore()
    store.add(Profile(name="FPS", settings=Settings(dpi_stages=[800, 1600]),
                      applications=["valorant.exe"], hotkey="ctrl+alt+1"))
    store.add(Profile(name="FPS"))  # duplicate name must be disambiguated
    store.save(path)

    loaded = ProfileStore.load(path)
    assert [p.name for p in loaded.profiles] == ["FPS", "FPS (2)"], [p.name for p in loaded.profiles]
    assert loaded.for_application("VALORANT.EXE").name == "FPS"
    assert loaded.for_application("notepad.exe") is None
    assert loaded.resolve("notepad.exe").name == "FPS"  # falls back to default
    assert loaded.profiles[0].settings.dpi_stages == [800, 1600]
    print(f"  saved, reloaded, matched: {[p.name for p in loaded.profiles]}")

    path.write_text("{ this is not json", encoding="utf-8")
    recovered = ProfileStore.load(path)
    assert recovered.profiles == []
    print("  corrupt file recovered without crashing")

    path.unlink(missing_ok=True)
    Path(str(path).replace(".json", ".corrupt")).unlink(missing_ok=True)


def test_watcher():
    print("\n== watcher ==")
    print(f"  foreground executable: {foreground_executable()}")


def test_ui_builds():
    print("\n== ui ==")
    from mousemod.ui import TrayApp

    app = TrayApp()
    window = app.window

    print(f"  connected      : {app.service.connected}")
    print(f"  profiles       : {[p.name for p in app.service.store.profiles]}")
    print(f"  tray status    : {app._status_text()}")
    print(f"  editor enabled : {window.editor.isEnabled()}")

    profile = window.current_profile()
    assert profile is not None, "expected a seeded profile"
    window.editor.load(profile)
    before = profile.settings.dpi_stages[0]
    window.editor.dpi_spins[0].setValue(1234)
    window.editor.collect()
    after = profile.settings.dpi_stages[0]
    assert after == 1234, f"editor did not write back: {after}"
    window.editor.dpi_spins[0].setValue(before)
    window.editor.collect()
    print(f"  editor writes back to the profile ({before} -> 1234 -> {profile.settings.dpi_stages[0]})")

    test_macro_page(app)

    QTimer.singleShot(200, app._quit)
    code = app.run()
    print(f"  event loop exited cleanly with {code}")
    return code


def test_macro_page(app):
    """The macro editor must write straight into the bound profile."""
    from mousemod.macros import REPEAT_UNTIL_RELEASE, encode_repeat, key_press
    from mousemod.protocol import MACRO_SLOTS, ButtonClass

    print("\n== macro page ==")
    editor = app.window.editor
    page = editor.macro_page
    profile = app.window.current_profile()

    assert len(profile.settings.macros) == MACRO_SLOTS, len(profile.settings.macros)
    print(f"  {MACRO_SLOTS} slots bound to the profile")

    page.slot_list.setCurrentRow(0)
    macro = page.current_macro()
    assert macro is profile.settings.macros[0], "editor is not editing the profile"

    before = len(macro.actions)
    page._insert(key_press(0x04, 25))  # A down/up
    assert len(macro.actions) == before + 2, len(macro.actions)
    assert page.action_list.count() == len(macro.actions)
    print(f"  inserted 2 actions -> {[a.describe() for a in macro.actions]}")

    macro.name = "Test macro"
    macro.repeat_mode = REPEAT_UNTIL_RELEASE
    page.load(profile.settings.macros)
    assert page.slot_list.item(0).text().startswith("1. Test macro"), \
        page.slot_list.item(0).text()
    print(f"  slot label follows the name: {page.slot_list.item(0).text()!r}")

    # Binding a button to the macro must pick up that repeat mode.
    combo = editor.button_combos["side1"]
    macro_index = next(
        i for i, (label, cls, v1) in enumerate(
            __import__("mousemod.ui", fromlist=["ACTIONS"]).ACTIONS
        ) if cls == ButtonClass.MACRO and v1 == 0
    )
    combo.setCurrentIndex(macro_index)
    editor.collect()
    action = profile.settings.buttons["side1"]
    expected = encode_repeat(REPEAT_UNTIL_RELEASE, 1)
    assert action.action == int(ButtonClass.MACRO), action
    assert action.value1 == 0, action
    assert action.value2 == expected, f"{action.value2} != {expected}"
    print(f"  side1 -> {action.describe()}  (value2={action.value2})")

    # Put it back so the smoke test leaves no residue.
    macro.actions = macro.actions[:before]
    macro.name = ""
    combo.setCurrentIndex(3)
    editor.collect()
    print("  reverted")


if __name__ == "__main__":
    test_hotkey_parsing()
    test_profile_roundtrip()
    test_watcher()
    sys.exit(test_ui_builds())
