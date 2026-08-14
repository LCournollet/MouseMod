"""System-wide hotkeys via RegisterHotKey.

Hotkeys are owned by a dedicated thread running its own message loop, because
RegisterHotKey delivers WM_HOTKEY to the registering thread's queue.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MODIFIERS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}

#: Virtual-key codes for the names we accept beyond plain letters and digits.
NAMED_KEYS = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "enter": 0x0D,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69,
}


class HotkeyError(ValueError):
    pass


def parse(spec: str) -> tuple[int, int]:
    """'ctrl+shift+f1' -> (modifier mask, virtual key code)."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise HotkeyError(f"empty hotkey: {spec!r}")

    modifiers = 0
    key = None
    for part in parts:
        if part in MODIFIERS:
            modifiers |= MODIFIERS[part]
        elif key is None:
            key = part
        else:
            raise HotkeyError(f"more than one non-modifier key in {spec!r}")

    if key is None:
        raise HotkeyError(f"no key in {spec!r}")
    if key in NAMED_KEYS:
        return modifiers, NAMED_KEYS[key]
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        return modifiers, ord(key.upper())
    raise HotkeyError(f"unknown key {key!r} in {spec!r}")


class HotkeyManager:
    """Registers hotkeys and dispatches their callbacks.

    Callbacks run on the hotkey thread, so anything touching the UI must
    marshal back to the UI thread itself.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, Callable[[], None]] = {}
        self._pending: dict[str, Callable[[], None]] = {}
        self._ids: dict[int, str] = {}
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._failed: dict[str, str] = {}

    @property
    def failed(self) -> dict[str, str]:
        """Hotkeys that could not be registered, mapped to the reason."""
        with self._lock:
            return dict(self._failed)

    def bind(self, spec: str, callback: Callable[[], None]) -> None:
        with self._lock:
            self._pending[spec] = callback

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()
        self.stop()

    def start(self) -> None:
        """(Re)start the hotkey thread with the currently bound hotkeys."""
        self.stop()
        with self._lock:
            self._bindings = dict(self._pending)
            self._failed.clear()
        if not self._bindings:
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3)

    def stop(self) -> None:
        if self._thread and self._thread.is_alive() and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None

    def _run(self) -> None:
        self._thread_id = threading.get_native_id()
        registered = []

        for index, (spec, _callback) in enumerate(self._bindings.items(), start=1):
            try:
                modifiers, key = parse(spec)
            except HotkeyError as exc:
                with self._lock:
                    self._failed[spec] = str(exc)
                continue
            if user32.RegisterHotKey(None, index, modifiers | MOD_NOREPEAT, key):
                self._ids[index] = spec
                registered.append(index)
            else:
                with self._lock:
                    self._failed[spec] = "already taken by another application"

        self._ready.set()

        try:
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY:
                    spec = self._ids.get(message.wParam)
                    callback = self._bindings.get(spec) if spec else None
                    if callback:
                        try:
                            callback()
                        except Exception:
                            pass
        finally:
            for index in registered:
                user32.UnregisterHotKey(None, index)
            self._ids.clear()
