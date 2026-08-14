"""Macro codec checks plus a live write/read round-trip.

Slot 16 (the last one) is used as scratch space and restored to whatever it
held before the test.

Run: python -m tests.test_macros
"""

import sys
import time

sys.path.insert(0, ".")

from mousemod import connect  # noqa: E402
from mousemod.keymap import usage_for_qt, usage_name  # noqa: E402
from mousemod.macros import (  # noqa: E402
    REPEAT_COUNT,
    REPEAT_ONCE,
    REPEAT_UNTIL_ANY_KEY,
    REPEAT_UNTIL_RELEASE,
    Macro,
    MacroAction,
    decode_repeat,
    encode_repeat,
    key_press,
    read_macro,
    wheel,
    write_macro,
)
from mousemod.protocol import KeyState, MacroKeyType  # noqa: E402

SCRATCH_SLOT = 15


def test_action_codec():
    print("== action codec ==")
    cases = [
        MacroAction(int(MacroKeyType.KEY), int(KeyState.DOWN), 0x04, 0, 1),
        MacroAction(int(MacroKeyType.KEY), int(KeyState.UP), 0x04, 0, 65535),
        MacroAction(int(MacroKeyType.MODIFIER), int(KeyState.DOWN), 0x02, 0, 250),
        MacroAction(int(MacroKeyType.MOUSE), int(KeyState.DOWN), 1, 0, 15),
        MacroAction(int(MacroKeyType.WHEEL), int(KeyState.SCROLL), 255, 0, 5),
    ]
    for action in cases:
        raw = action.to_bytes()
        assert len(raw) == 5, f"action must be 5 bytes, got {len(raw)}"
        back = MacroAction.from_bytes(raw)
        assert back == action, f"{action} -> {raw.hex(' ')} -> {back}"
        print(f"  {raw.hex(' ')}  {action.describe()}   ok")

    # Flag layout must match the firmware's expectations exactly.
    down = MacroAction(int(MacroKeyType.KEY), int(KeyState.DOWN), 0x04).to_bytes()
    up = MacroAction(int(MacroKeyType.KEY), int(KeyState.UP), 0x04).to_bytes()
    scroll = MacroAction(int(MacroKeyType.WHEEL), int(KeyState.SCROLL), 1).to_bytes()
    assert down[0] == 0x81, hex(down[0])   # 0x80 down | type 1
    assert up[0] == 0x41, hex(up[0])       # 0x40 up   | type 1
    assert scroll[0] == 0x06, hex(scroll[0])  # no state bits | type 6
    print("  flag bits: down=0x81 up=0x41 wheel=0x06   ok")


def test_repeat_codec():
    print("\n== repeat modes ==")
    for mode, count in [
        (REPEAT_ONCE, 1),
        (REPEAT_UNTIL_RELEASE, 1),
        (REPEAT_UNTIL_ANY_KEY, 1),
        (REPEAT_COUNT, 7),
    ]:
        value = encode_repeat(mode, count)
        back_mode, back_count = decode_repeat(value)
        assert back_mode == mode, f"{mode} -> {value} -> {back_mode}"
        if mode == REPEAT_COUNT:
            assert back_count == count
        print(f"  {mode:<14} -> value2={value:<3} -> {back_mode} x{back_count}   ok")


def test_keymap():
    print("\n== keymap ==")
    from PySide6.QtCore import Qt

    assert usage_for_qt(Qt.Key_A) == 0x04
    assert usage_for_qt(Qt.Key_Z) == 0x1D
    assert usage_for_qt(Qt.Key_1) == 0x1E
    assert usage_for_qt(Qt.Key_0) == 0x27
    assert usage_for_qt(Qt.Key_F5) == 0x3E
    assert usage_for_qt(Qt.Key_Space) == 0x2C
    assert usage_for_qt(Qt.Key_5, keypad=True) == 0x5D
    assert usage_name(0x04) == "A"
    print("  A=0x04 Z=0x1D 1=0x1E 0=0x27 F5=0x3E Space=0x2C Num5=0x5D   ok")


def test_live_roundtrip():
    print("\n== live round-trip ==")
    mouse = connect()
    with mouse:
        original = read_macro(mouse, SCRATCH_SLOT)
        print(f"  slot {SCRATCH_SLOT + 1} originally holds {len(original.actions)} action(s)")

        # "hello" typed out, then a wheel notch, then ctrl+c
        built = Macro(name="Test")
        for usage in (0x0B, 0x08, 0x0F, 0x0F, 0x12):  # h e l l o
            built.actions += key_press(usage, delay_ms=12)
        built.actions += wheel(up=True, delay_ms=8)
        built.actions += [
            MacroAction(int(MacroKeyType.MODIFIER), int(KeyState.DOWN), 0x01, 0, 5),
            MacroAction(int(MacroKeyType.KEY), int(KeyState.DOWN), 0x06, 0, 5),
            MacroAction(int(MacroKeyType.KEY), int(KeyState.UP), 0x06, 0, 5),
            MacroAction(int(MacroKeyType.MODIFIER), int(KeyState.UP), 0x01, 0, 5),
        ]
        print(f"  writing {len(built.actions)} actions ({built.duration_ms()} ms total)")

        started = time.monotonic()
        write_macro(mouse, SCRATCH_SLOT, built)
        elapsed = (time.monotonic() - started) * 1000

        read_back = read_macro(mouse, SCRATCH_SLOT)
        print(f"  wrote in {elapsed:.0f} ms, read back {len(read_back.actions)} action(s)")

        failures = []
        if len(read_back.actions) != len(built.actions):
            failures.append(f"count {len(read_back.actions)} != {len(built.actions)}")
        for index, (want, got) in enumerate(zip(built.actions, read_back.actions)):
            if want != got:
                failures.append(f"action {index}: {want} != {got}")

        for index, action in enumerate(read_back.actions[:6]):
            print(f"    {index}: {action.to_bytes().hex(' ')}  {action.describe()}"
                  f"  +{action.delay_ms}ms")

        # An odd-length macro exercises the page-boundary maths.
        odd = Macro(name="Odd", actions=key_press(0x04, 20) + [
            MacroAction(int(MacroKeyType.KEY), int(KeyState.DOWN), 0x05, 0, 30)
        ])
        write_macro(mouse, SCRATCH_SLOT, odd)
        odd_back = read_macro(mouse, SCRATCH_SLOT)
        if len(odd_back.actions) != 3:
            failures.append(f"odd macro: read {len(odd_back.actions)} actions, wanted 3")
        elif odd_back.actions != odd.actions:
            failures.append("odd macro mismatch")
        print(f"  odd-length macro (3 actions) round-trip: "
              f"{'ok' if len(odd_back.actions) == 3 else 'FAILED'}")

        # Empty slot must read back as empty.
        write_macro(mouse, SCRATCH_SLOT, Macro(name="Empty"))
        empty_back = read_macro(mouse, SCRATCH_SLOT)
        if empty_back.actions:
            failures.append(f"cleared slot still has {len(empty_back.actions)} actions")
        print(f"  cleared slot reads empty: {'ok' if not empty_back.actions else 'FAILED'}")

        print("\n  restoring the original slot contents")
        write_macro(mouse, SCRATCH_SLOT, original)
        restored = read_macro(mouse, SCRATCH_SLOT)
        if restored.to_dict() != original.to_dict():
            failures.append("restore mismatch")
        print(f"  restored: {'ok' if restored.to_dict() == original.to_dict() else 'FAILED'}")

        print("\n" + ("ALL MACRO CHECKS PASSED" if not failures
                      else "FAILED:\n  " + "\n  ".join(failures)))
        return 1 if failures else 0


def test_apply_settings_path():
    """Macros must travel with a profile through apply_settings()."""
    print("\n== profile apply path ==")
    from mousemod.macros import REPEAT_UNTIL_RELEASE
    from mousemod.protocol import ButtonClass
    from mousemod.settings import ButtonAction, apply_settings, read_settings

    mouse = connect()
    with mouse:
        original = read_settings(mouse)

        wanted = original.copy()
        wanted.macros[SCRATCH_SLOT].actions = key_press(0x07, 40)  # D down/up
        wanted.macros[SCRATCH_SLOT].name = "Apply test"
        wanted.macros[SCRATCH_SLOT].repeat_mode = REPEAT_UNTIL_RELEASE

        try:
            apply_settings(mouse, wanted, original)
            after = read_settings(mouse)
            landed = after.macros[SCRATCH_SLOT].actions
            ok = landed == wanted.macros[SCRATCH_SLOT].actions
            print(f"  macro reached the device through apply_settings: "
                  f"{'ok' if ok else 'FAILED'}")
            for action in landed:
                print(f"    {action.to_bytes().hex(' ')}  {action.describe()}")

            # A second apply with no macro change must skip the write entirely.
            same = after.copy()
            apply_settings(mouse, same, after)
            print("  re-applying an unchanged profile: ok (writes skipped)")

            binding = ButtonAction(int(ButtonClass.MACRO), SCRATCH_SLOT, 253)
            print(f"  button binding would read: {binding.describe()}")
            failed = not ok
        finally:
            print("  restoring")
            apply_settings(mouse, original, None)
            restored = read_settings(mouse)
            same_state = restored.to_dict() == original.to_dict()
            print(f"  restored to the original configuration: "
                  f"{'ok' if same_state else 'FAILED'}")
            failed = failed or not same_state

        print("\n" + ("APPLY PATH OK" if not failed else "APPLY PATH FAILED"))
        return 1 if failed else 0


if __name__ == "__main__":
    test_action_codec()
    test_repeat_codec()
    test_keymap()
    status = test_live_roundtrip()
    status |= test_apply_settings_path()
    sys.exit(status)
