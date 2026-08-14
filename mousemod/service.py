"""Orchestration: keeps a live connection, applies profiles, drives automation.

Deliberately free of any UI dependency so the same logic backs both the window
and the command line.
"""

from __future__ import annotations

import threading
from typing import Callable

from .device import DeviceError, Mouse, NotConnected, connect
from .hotkeys import HotkeyManager
from .profiles import Profile, ProfileStore, seed_from_device
from .settings import (
    Settings,
    apply_settings,
    read_settings,
    set_active_stage,
)
from .watcher import ForegroundWatcher

Listener = Callable[[str, object], None]


class MouseService:
    """Owns the device connection, the profile store and the automation.

    Emits events by name so a front end can subscribe without this module
    knowing anything about it: ``connected``, ``disconnected``, ``profile``,
    ``settings``, ``battery``, ``error``.
    """

    def __init__(self) -> None:
        self.store = ProfileStore.load()
        self.mouse: Mouse | None = None
        self.current: Settings | None = None
        self.active_profile: Profile | None = None

        self._listeners: list[Listener] = []
        self._lock = threading.RLock()
        self._watcher = ForegroundWatcher(self._on_foreground_change)
        self._hotkeys = HotkeyManager()

    # -- events ------------------------------------------------------------

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, event: str, payload: object = None) -> None:
        for listener in list(self._listeners):
            try:
                listener(event, payload)
            except Exception:
                pass

    # -- connection --------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.mouse is not None

    def connect(self) -> bool:
        """Attach to the mouse and read its current state."""
        with self._lock:
            self.disconnect()
            try:
                self.mouse = connect()
                self.current = read_settings(self.mouse)
            except (NotConnected, DeviceError) as exc:
                self.mouse = None
                self.current = None
                self._emit("disconnected", str(exc))
                return False

            if not self.store.profiles:
                self.store = seed_from_device(self.current)
                self.store.save()
                self.active_profile = self.store.fallback()

            self._emit("connected", self.mouse.endpoint)
            self._emit("settings", self.current)
            return True

    def disconnect(self) -> None:
        with self._lock:
            if self.mouse is not None:
                self.mouse.close()
                self.mouse = None
            self.current = None

    def ensure_connected(self) -> bool:
        if self.connected:
            return True
        return self.connect()

    def refresh(self) -> Settings | None:
        """Re-read the device, reconnecting once if the link dropped."""
        with self._lock:
            if not self.ensure_connected():
                return None
            assert self.mouse is not None
            try:
                self.current = read_settings(self.mouse)
            except (DeviceError, OSError):
                self.disconnect()
                if not self.connect():
                    return None
                return self.current
            self._emit("settings", self.current)
            return self.current

    def battery(self) -> dict | None:
        with self._lock:
            if not self.ensure_connected():
                return None
            assert self.mouse is not None
            try:
                info = self.mouse.battery()
            except (DeviceError, OSError):
                self.disconnect()
                return None
            self._emit("battery", info)
            return info

    # -- profiles ----------------------------------------------------------

    def apply_profile(self, profile: Profile, force: bool = False) -> bool:
        """Push a profile to the device, writing only what differs."""
        with self._lock:
            if not self.ensure_connected():
                return False
            assert self.mouse is not None
            if not force and self.active_profile is profile and self.current is not None:
                return True
            try:
                baseline = None if force else self.current
                self.current = apply_settings(self.mouse, profile.settings, baseline)
            except (DeviceError, OSError) as exc:
                self.disconnect()
                self._emit("error", f"could not apply '{profile.name}': {exc}")
                return False

            self.active_profile = profile
            self._emit("profile", profile)
            self._emit("settings", self.current)
            return True

    def apply_profile_named(self, name: str) -> bool:
        profile = self.store.get(name)
        return self.apply_profile(profile) if profile else False

    def save_current_as(self, name: str) -> Profile | None:
        """Snapshot what is on the mouse right now into a new profile."""
        with self._lock:
            settings = self.refresh()
            if settings is None:
                return None
            profile = self.store.add(Profile(name=name, settings=settings.copy()))
            self.store.save()
            return profile

    def factory_reset(self) -> bool:
        """Reset the device itself. PC-side profiles are untouched."""
        with self._lock:
            if not self.ensure_connected():
                return False
            assert self.mouse is not None
            try:
                self.mouse.restore_factory()
            except (DeviceError, OSError) as exc:
                self.disconnect()
                self._emit("error", f"factory reset failed: {exc}")
                return False
            self.active_profile = None
            self.refresh()
            return True

    def cycle_dpi(self, step: int = 1) -> int | None:
        """Move to the next/previous DPI stage on the device."""
        with self._lock:
            if not self.ensure_connected() or self.current is None:
                return None
            assert self.mouse is not None
            count = max(1, len(self.current.dpi_stages))
            index = (self.current.active_stage + step) % count
            try:
                set_active_stage(self.mouse, index)
            except (DeviceError, OSError) as exc:
                self.disconnect()
                self._emit("error", f"DPI switch failed: {exc}")
                return None
            self.current.active_stage = index
            if self.active_profile:
                self.active_profile.settings.active_stage = index
            self._emit("settings", self.current)
            return index

    def cycle_profile(self, step: int = 1) -> Profile | None:
        with self._lock:
            if not self.store.profiles:
                return None
            if self.active_profile in self.store.profiles:
                index = self.store.profiles.index(self.active_profile)
            else:
                index = -1
            target = self.store.profiles[(index + step) % len(self.store.profiles)]
            return target if self.apply_profile(target) else None

    # -- automation --------------------------------------------------------

    def start_automation(self) -> None:
        self.reload_hotkeys()
        if self.store.auto_switch:
            self._watcher.start()

    def stop_automation(self) -> None:
        self._watcher.stop()
        self._hotkeys.stop()

    def set_auto_switch(self, enabled: bool) -> None:
        self.store.auto_switch = enabled
        self.store.save()
        if enabled:
            self._watcher.start()
            self._on_foreground_change(self._watcher.current)
        else:
            self._watcher.stop()

    def reload_hotkeys(self) -> dict[str, str]:
        """Re-register every hotkey. Returns the ones that could not be bound."""
        self._hotkeys.clear()
        self._hotkeys.bind("ctrl+alt+d", lambda: self.cycle_dpi(1))
        self._hotkeys.bind("ctrl+alt+p", lambda: self.cycle_profile(1))
        for profile in self.store.profiles:
            if profile.hotkey:
                self._hotkeys.bind(profile.hotkey, self._profile_callback(profile.name))
        self._hotkeys.start()
        failures = self._hotkeys.failed
        if failures:
            self._emit("error", "hotkeys unavailable: " + ", ".join(failures))
        return failures

    def _profile_callback(self, name: str) -> Callable[[], None]:
        def run() -> None:
            self.apply_profile_named(name)

        return run

    def _on_foreground_change(self, executable: str | None) -> None:
        if not self.store.auto_switch:
            return
        profile = self.store.resolve(executable)
        if profile and profile is not self.active_profile:
            self.apply_profile(profile)

    # -- shutdown ----------------------------------------------------------

    def shutdown(self) -> None:
        self.stop_automation()
        self.disconnect()
