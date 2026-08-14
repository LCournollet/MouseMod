# MouseMod

Native configuration for the **ATK Blazing Sky F1 Extreme 8K** (and other
ATK/VXE mice on the same COMPX protocol), so the browser-based ATK HUB is no
longer needed.

MouseMod talks the vendor HID protocol directly. No vendor driver, no browser,
no account, no network access. The protocol was reverse-engineered from the
ATK HUB web bundle and verified against the device; see [PROTOCOL.md](PROTOCOL.md).

## What it does

Everything the web driver does:

- DPI stages (up to 4 exposed, 8 supported by the hardware) with per-stage values
- Report rate, 125 Hz to 8000 Hz
- Lift-off distance, sensor angle
- Motion sync, linear correction, ripple control
- Click debounce, sleep timer
- Button remapping for all six buttons
- **Macros** — 16 on-device slots, up to 70 actions each
- **Keyboard combinations** — bind a chord like `Ctrl+Shift+S` to a button
- Battery level, firmware version, factory reset

Plus what it does not:

- **Unlimited PC-side profiles**, not just the mouse's onboard slots
- **Automatic profile switching per application** — bind `valorant.exe` to an
  FPS profile and it applies the moment the game takes focus
- **Global hotkeys** — `Ctrl+Alt+D` cycles DPI, `Ctrl+Alt+P` cycles profiles,
  and any profile can have its own
- **Battery in the system tray**, colour-coded, always visible

## Running it

Double-click **`dist\MouseMod.exe`**. It is a single self-contained
executable — no Python installation, no dependencies, nothing to install. Copy
it anywhere you like.

Closing the window hides it to the tray; quit from the tray menu.

For development, run from source instead:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m mousemod gui          # window + tray
.venv\Scripts\python.exe -m mousemod gui --tray   # start minimised
```

### Building the executable

```powershell
.venv\Scripts\python.exe tools\make_icon.py                    # regenerate the icon
.venv\Scripts\pyinstaller.exe --noconfirm --clean MouseMod.spec
```

The result is `dist\MouseMod.exe` (~44 MB; Qt is bundled). The build entry
point is `main.py` rather than `mousemod/__main__.py`, because PyInstaller runs
its entry script as a top-level module where relative imports do not resolve.

### Command line

```powershell
python -m mousemod devices          # list attached ATK endpoints
python -m mousemod status           # dump the live configuration
python -m mousemod dpi 1600         # set the active DPI stage
python -m mousemod dpi 3200 --stage 4
python -m mousemod rate 4000        # set the report rate
python -m mousemod profile          # list profiles
python -m mousemod profile Valorant # apply one
python -m mousemod save "My setup"  # snapshot the mouse into a new profile
```

## Keyboard combinations

Set a button to **Keyboard combination** in the Buttons tab, then click the
field and press the chord you want — `Ctrl+Shift+S`, `Alt+F4`, or a single key.
Escape cancels, Delete clears it.

The mouse stores **three keys at most** per button (six entries, two per key),
so `Ctrl+Shift+S` fits but `Ctrl+Alt+Shift+S` is shortened. The field says so
when that happens.

For anything longer, use a macro instead.

## Macros

The mouse holds **16 macro slots**, up to **70 actions** each. An action is a
key or mouse-button press or release, a wheel notch, or a pause, each with its
own delay in milliseconds.

In the **Macros** tab you can:

- **Record** — press Record and type. Key presses, releases and the real timing
  between them are captured. Recording only listens while MouseMod has focus;
  it is not a system-wide keyboard hook.
- **Add actions by hand** — any key, modifier, mouse button or wheel notch,
  inserted as press-and-release, press-only or release-only.
- **Add delays**, reorder, remove, or clear.
- Choose how the macro **repeats** when bound to a button: once, while the
  button is held, until any key is pressed, or a set number of times.

Bind a macro to a button in the **Buttons** tab (`Macro 1` … `Macro 16`); the
repeat mode set on the macro travels with it.

Macros are stored in the profile, so switching profiles rewrites only the slots
that actually differ.

## Wired and wireless

Both links work. MouseMod probes every ATK endpoint it finds and uses the one
that actually answers, preferring the cable when both are live:

- **Wired** — the mouse itself enumerates as `373B:1045`
- **8K dongle** — enumerates as `373B:1159` and relays to the mouse over RF

If the mouse is asleep the dongle rejects reads; MouseMod reports that rather
than silently doing nothing. Move the mouse and retry.

## Profiles

Profiles live in `%APPDATA%\MouseMod\profiles.json` — plain JSON, easy to back
up or edit by hand. Each profile holds a full settings snapshot plus the
executables and hotkey that select it.

Profile switching only writes the fields that actually differ from what is on
the mouse, which keeps focus-triggered switches fast.

## Safety

MouseMod only reads and writes configuration EEPROM. It never touches the
firmware flash, so it cannot brick the device. "Factory reset" in the window
issues the vendor's own reset command; your PC-side profiles survive it and can
be re-applied.

## Interface

A frameless dark window with its own chrome: rounded corners, drop shadow,
drag-to-move title bar and edge resizing. Steppers, chevrons, toggles and the
tray icon are painted at runtime rather than loaded from image assets or icon
fonts, so nothing depends on a font being installed.

The design tokens live in `theme.py`; changing the palette there restyles the
whole application.

## Layout

```
main.py         frozen-build entry point
mousemod/
  protocol.py   wire format, command ids, EEPROM map, DPI codec
  device.py     HID discovery and transport (mouse + dongle)
  settings.py   typed read/write of every setting
  profiles.py   PC-side profile store
  macros.py     macro slots: encode, decode, read, write
  shortcuts.py  per-button keyboard combinations
  keymap.py     Qt key <-> HID usage translation
  watcher.py    foreground-application detection
  hotkeys.py    system-wide hotkeys
  service.py    orchestration, no UI dependency
  theme.py      design tokens and the stylesheet
  widgets.py    frameless window, toggles, cards, painted controls
  ui.py         the window and the tray
  macro_ui.py   the macro editor and keyboard recorder
  shortcut_ui.py the chord capture control
  cli.py        command line
tools/          icon generation
recon/          the reverse-engineering scripts, kept for reference
tests/          codec, profile, write round-trip, UI smoke and render tests
```

## Tests

```powershell
python -m tests.test_read       # codec checks + live read-only dump
python -m tests.test_write      # live write round-trip, restores the original state
python -m tests.test_macros     # macro codec + live round-trip, restores the slot
python -m tests.test_shortcuts  # combination codec + live round-trip on side1
python -m tests.test_ui_smoke   # profiles, hotkeys, macro editor, headless UI build
python -m tests.test_wireless   # dongle path; unplug the cable first
python -m tests.render_ui       # render each page to tests/_render for review
```

`render_ui` shows the window off-screen without activating it, so it never
steals focus from a game or another foreground application.
