"""PC-side profiles.

Unlike the mouse's onboard config slots there is no limit here: profiles live
as JSON under %APPDATA%\\MouseMod and can be bound to applications so that the
right one is applied when a window takes focus.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .settings import Settings

APP_NAME = "MouseMod"
SCHEMA_VERSION = 1


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def profiles_file() -> Path:
    return config_dir() / "profiles.json"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "profile"


@dataclass
class Profile:
    name: str
    settings: Settings = field(default_factory=Settings)
    #: Executable names (case-insensitive, e.g. "valorant.exe") that select it.
    applications: list[str] = field(default_factory=list)
    hotkey: str | None = None

    @property
    def slug(self) -> str:
        return _slugify(self.name)

    def matches(self, executable: str | None) -> bool:
        if not executable:
            return False
        target = executable.lower()
        return any(app.lower() == target for app in self.applications)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "applications": self.applications,
            "hotkey": self.hotkey,
            "settings": self.settings.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(
            name=data.get("name", "Unnamed"),
            settings=Settings.from_dict(data.get("settings", {})),
            applications=list(data.get("applications", [])),
            hotkey=data.get("hotkey"),
        )


@dataclass
class ProfileStore:
    """The profile list plus which one is the fallback."""

    profiles: list[Profile] = field(default_factory=list)
    default_profile: str | None = None
    auto_switch: bool = True

    # -- lookup ------------------------------------------------------------

    def get(self, name: str) -> Profile | None:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def for_application(self, executable: str | None) -> Profile | None:
        """The profile bound to this executable, if any."""
        for profile in self.profiles:
            if profile.matches(executable):
                return profile
        return None

    def fallback(self) -> Profile | None:
        if self.default_profile:
            found = self.get(self.default_profile)
            if found:
                return found
        return self.profiles[0] if self.profiles else None

    def resolve(self, executable: str | None) -> Profile | None:
        return self.for_application(executable) or self.fallback()

    # -- mutation ----------------------------------------------------------

    def add(self, profile: Profile) -> Profile:
        base, index = profile.name, 2
        while self.get(profile.name):
            profile.name = f"{base} ({index})"
            index += 1
        self.profiles.append(profile)
        if self.default_profile is None:
            self.default_profile = profile.name
        return profile

    def remove(self, name: str) -> None:
        self.profiles = [p for p in self.profiles if p.name != name]
        if self.default_profile == name:
            self.default_profile = self.profiles[0].name if self.profiles else None

    def rename(self, old: str, new: str) -> None:
        profile = self.get(old)
        if profile is None or not new.strip():
            return
        profile.name = new.strip()
        if self.default_profile == old:
            self.default_profile = profile.name

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "default_profile": self.default_profile,
            "auto_switch": self.auto_switch,
            "profiles": [p.to_dict() for p in self.profiles],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileStore":
        return cls(
            profiles=[Profile.from_dict(p) for p in data.get("profiles", [])],
            default_profile=data.get("default_profile"),
            auto_switch=bool(data.get("auto_switch", True)),
        )

    def save(self, path: Path | None = None) -> Path:
        """Write atomically so a crash mid-save cannot truncate the file."""
        path = path or profiles_file()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "ProfileStore":
        path = path or profiles_file()
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            # A corrupt file must not stop the app from starting.
            backup = path.with_suffix(".corrupt")
            try:
                path.replace(backup)
            except OSError:
                pass
            return cls()


def seed_from_device(settings: Settings) -> ProfileStore:
    """Initial store built from whatever is currently on the mouse."""
    store = ProfileStore()
    store.add(Profile(name="Default", settings=settings.copy()))
    return store
