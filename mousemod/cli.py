"""Command line for MouseMod - handy for scripting and for checking the link.

    python -m mousemod status
    python -m mousemod dpi 1600
    python -m mousemod rate 4000
    python -m mousemod profile Valorant
"""

from __future__ import annotations

import argparse
import sys

from .device import DeviceError, NotConnected, discover
from .service import MouseService
from .settings import set_dpi_stages, set_report_rate


def cmd_devices(_args) -> int:
    endpoints = discover()
    if not endpoints:
        print("no ATK hardware found")
        return 1
    for endpoint in endpoints:
        print(f"{endpoint.vendor_id:04X}:{endpoint.product_id:04X}  {endpoint.label}")
    return 0


def cmd_status(_args) -> int:
    service = MouseService()
    if not service.connect():
        print("mouse not reachable")
        return 1
    settings = service.current
    assert settings is not None and service.mouse is not None

    battery = service.battery() or {}
    print(f"device      : {service.mouse.endpoint.label}")
    print(f"firmware    : {service.mouse.firmware_version()}")
    print(f"battery     : {battery.get('percent', '?')}%"
          f"{' (charging)' if battery.get('charging') else ''}")
    print(f"report rate : {settings.report_rate_hz} Hz")
    print(f"dpi stages  : {settings.dpi_stages}  active #{settings.active_stage + 1}")
    print(f"lod         : {settings.lod}")
    print(f"motion sync : {settings.motion_sync}")
    print(f"debounce    : {settings.debounce_ms} ms")
    print(f"sleep       : {settings.sleep_seconds} s")
    print("buttons     :")
    for name, action in settings.buttons.items():
        print(f"  {name:<7} {action.describe()}")
    service.shutdown()
    return 0


def cmd_dpi(args) -> int:
    service = MouseService()
    if not service.connect():
        print("mouse not reachable")
        return 1
    assert service.mouse is not None and service.current is not None
    stages = list(service.current.dpi_stages)
    index = args.stage - 1 if args.stage else service.current.active_stage
    if not 0 <= index < len(stages):
        print(f"stage must be between 1 and {len(stages)}")
        return 1
    stages[index] = args.value
    written = set_dpi_stages(service.mouse, stages)
    print(f"stage {index + 1} set to {written[index]} DPI")
    service.shutdown()
    return 0


def cmd_rate(args) -> int:
    service = MouseService()
    if not service.connect():
        print("mouse not reachable")
        return 1
    assert service.mouse is not None
    set_report_rate(service.mouse, args.value)
    print(f"report rate set to {args.value} Hz")
    service.shutdown()
    return 0


def cmd_profile(args) -> int:
    service = MouseService()
    if not args.name:
        for profile in service.store.profiles:
            apps = f"  [{', '.join(profile.applications)}]" if profile.applications else ""
            print(f"{profile.name}{apps}")
        return 0
    if not service.connect():
        print("mouse not reachable")
        return 1
    if service.apply_profile_named(args.name):
        print(f"applied '{args.name}'")
        service.shutdown()
        return 0
    print(f"no profile named '{args.name}'")
    service.shutdown()
    return 1


def cmd_save(args) -> int:
    service = MouseService()
    if not service.connect():
        print("mouse not reachable")
        return 1
    profile = service.save_current_as(args.name)
    print(f"saved current configuration as '{profile.name}'" if profile else "failed")
    service.shutdown()
    return 0 if profile else 1


def cmd_gui(args) -> int:
    from .ui import main as gui_main

    return gui_main(show_window=not getattr(args, "tray", False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mousemod", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("devices", help="list attached ATK endpoints").set_defaults(func=cmd_devices)
    sub.add_parser("status", help="show the live configuration").set_defaults(func=cmd_status)

    dpi = sub.add_parser("dpi", help="set a DPI stage")
    dpi.add_argument("value", type=int)
    dpi.add_argument("--stage", type=int, help="1-based stage, default is the active one")
    dpi.set_defaults(func=cmd_dpi)

    rate = sub.add_parser("rate", help="set the report rate in Hz")
    rate.add_argument("value", type=int, choices=[125, 250, 500, 1000, 2000, 4000, 8000])
    rate.set_defaults(func=cmd_rate)

    profile = sub.add_parser("profile", help="apply a profile, or list them")
    profile.add_argument("name", nargs="?")
    profile.set_defaults(func=cmd_profile)

    save = sub.add_parser("save", help="save the live configuration as a profile")
    save.add_argument("name")
    save.set_defaults(func=cmd_save)

    gui = sub.add_parser("gui", help="launch the window and tray icon")
    gui.add_argument("--tray", action="store_true", help="start minimised to the tray")
    gui.set_defaults(func=cmd_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_gui(args)
    try:
        return args.func(args)
    except (NotConnected, DeviceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
