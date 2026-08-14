"""Combination-key codec plus a live write/read round-trip on the side1 button.

The button's previous shortcut record is restored before exit.

Run: python -m tests.test_shortcuts
"""

import sys

sys.path.insert(0, ".")

from mousemod import connect  # noqa: E402
from mousemod.protocol import (  # noqa: E402
    SHORTCUT_MAX_ENTRIES,
    SHORTCUT_MAX_KEYS,
    KeyState,
    MacroKeyType,
)
from mousemod.shortcuts import (  # noqa: E402
    ShortcutStep,
    build,
    describe,
    read_shortcut,
    to_usages,
    write_shortcut,
)

TARGET = "side1"

CTRL, SHIFT, ALT = 0xE0, 0xE1, 0xE2
KEY_A, KEY_C, KEY_S = 0x04, 0x06, 0x16


def test_entry_codec():
    print("== entry codec ==")
    step = ShortcutStep(int(MacroKeyType.KEY), int(KeyState.DOWN), KEY_A)
    raw = step.to_bytes()
    assert len(raw) == 3, len(raw)
    assert raw[0] == 0x81, hex(raw[0])
    assert ShortcutStep.from_bytes(raw) == step
    print(f"  A down  -> {raw.hex(' ')}  ok")

    up = ShortcutStep(int(MacroKeyType.KEY), int(KeyState.UP), KEY_A).to_bytes()
    assert up[0] == 0x41, hex(up[0])
    print(f"  A up    -> {up.hex(' ')}  ok")

    mod = ShortcutStep(int(MacroKeyType.MODIFIER), int(KeyState.DOWN), 0x01).to_bytes()
    assert mod[0] == 0x80, hex(mod[0])
    print(f"  Ctrl dn -> {mod.hex(' ')}  ok  (type 0, mask 0x01)")


def test_build():
    print("\n== chord building ==")
    steps = build([CTRL, SHIFT, KEY_A])
    assert len(steps) == 6, len(steps)
    assert to_usages(steps) == [CTRL, SHIFT, KEY_A], to_usages(steps)
    order = [(s.state, s.usage) for s in steps]
    print(f"  Ctrl+Shift+A -> {len(steps)} entries")
    for step in steps:
        word = "down" if step.state == KeyState.DOWN else "up"
        print(f"    {step.to_bytes().hex(' ')}  {word:<4} usage={step.usage:#04x}")
    # Down in order, then up in reverse: a modifier never releases before its key.
    assert order == [
        (KeyState.DOWN, CTRL), (KeyState.DOWN, SHIFT), (KeyState.DOWN, KEY_A),
        (KeyState.UP, KEY_A), (KeyState.UP, SHIFT), (KeyState.UP, CTRL),
    ], order
    print(f"  describe(): {describe(steps)}")

    # Over the limit must clamp rather than corrupt the record.
    clamped = build([CTRL, SHIFT, ALT, KEY_A, KEY_C])
    assert len(clamped) == SHORTCUT_MAX_ENTRIES, len(clamped)
    assert len(to_usages(clamped)) == SHORTCUT_MAX_KEYS
    print(f"  5 keys clamped to {SHORTCUT_MAX_KEYS}: {describe(clamped)}")

    assert build([]) == []
    print("  empty chord -> no entries  ok")


def test_live_roundtrip():
    print("\n== live round-trip ==")
    mouse = connect()
    with mouse:
        original = read_shortcut(mouse, TARGET)
        print(f"  {TARGET} originally: {describe(original)} "
              f"({len(original)} entries)")

        failures = []

        def check(label, usages):
            steps = build(usages)
            write_shortcut(mouse, TARGET, steps)
            back = read_shortcut(mouse, TARGET)
            ok = back == steps
            print(f"  {label:<20} wrote {len(steps)} entries, read {len(back)}"
                  f"  -> {describe(back)}  {'ok' if ok else 'MISMATCH'}")
            if not ok:
                failures.append(label)
                for want, got in zip(steps, back):
                    if want != got:
                        print(f"      want {want.to_bytes().hex(' ')} "
                              f"got {got.to_bytes().hex(' ')}")

        try:
            check("Ctrl+C", [CTRL, KEY_C])           # 4 entries, one page
            check("Ctrl+Shift+S", [CTRL, SHIFT, KEY_S])  # 6 entries, two pages
            check("single key A", [KEY_A])           # 2 entries

            write_shortcut(mouse, TARGET, [])
            cleared = read_shortcut(mouse, TARGET)
            print(f"  {'cleared':<20} -> {len(cleared)} entries  "
                  f"{'ok' if not cleared else 'FAILED'}")
            if cleared:
                failures.append("clear")
        finally:
            print("\n  restoring")
            write_shortcut(mouse, TARGET, original)
            restored = read_shortcut(mouse, TARGET)
            same = restored == original
            print(f"  restored: {'ok' if same else 'FAILED'}")
            if not same:
                failures.append("restore")

        print("\n" + ("ALL SHORTCUT CHECKS PASSED" if not failures
                      else f"FAILED: {', '.join(failures)}"))
        return 1 if failures else 0


if __name__ == "__main__":
    test_entry_codec()
    test_build()
    sys.exit(test_live_roundtrip())
