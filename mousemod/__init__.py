"""MouseMod - native configuration for ATK / VXE mice.

Speaks the vendor HID protocol directly, so no browser and no vendor driver
are involved. See PROTOCOL.md for the wire format.
"""

__version__ = "0.1.0"

from .device import DeviceError, Endpoint, Mouse, NotConnected, connect, discover
from .settings import ButtonAction, Settings, apply_settings, read_settings

__all__ = [
    "ButtonAction",
    "DeviceError",
    "Endpoint",
    "Mouse",
    "NotConnected",
    "Settings",
    "apply_settings",
    "connect",
    "discover",
    "read_settings",
]
