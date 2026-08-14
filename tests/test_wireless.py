"""Verify the dongle path. Unplug the USB cable first, then run:

    python -m tests.test_wireless

Read-only apart from one DPI-stage switch that is restored before exit.
"""

import sys

sys.path.insert(0, ".")

from mousemod import read_settings
from mousemod.device import Mouse, discover
from mousemod.settings import set_active_stage


def main() -> int:
    endpoints = discover()
    if not endpoints:
        print("no ATK hardware found")
        return 1

    print("== endpoints ==")
    for endpoint in endpoints:
        print(f"  {endpoint.vendor_id:04X}:{endpoint.product_id:04X}  {endpoint.label}")

    wired = [e for e in endpoints if not e.is_dongle]
    dongles = [e for e in endpoints if e.is_dongle]

    if not dongles:
        print("\nno dongle attached - plug in the 8K receiver")
        return 1
    if wired:
        print("\nthe mouse is still enumerating over USB; unplug the cable first")
        return 1

    endpoint = dongles[0]
    print(f"\n== talking to the mouse through {endpoint.label} ==")

    with Mouse(endpoint) as mouse:
        status = mouse.wireless_status()
        print(f"  mouse online : {status['online']}  rf id {status['rf_id']}")
        if not status["online"]:
            print("  move the mouse to wake it, then run this again")
            return 1

        print(f"  dongle fw    : {mouse.dongle_version()}")
        cid, mid = mouse.cid_mid()
        print(f"  cid,mid      : {cid},{mid}")
        battery = mouse.battery()
        print(f"  battery      : {battery['percent']}%  charging={battery['charging']}")

        before = read_settings(mouse)
        print(f"  report rate  : {before.report_rate_hz} Hz")
        print(f"  dpi stages   : {before.dpi_stages}  active #{before.active_stage}")
        print(f"  lod          : {before.lod}")
        print(f"  motion sync  : {before.motion_sync}")

        print("\n== write test over RF ==")
        target = (before.active_stage + 1) % len(before.dpi_stages)
        set_active_stage(mouse, target)
        readback = read_settings(mouse).active_stage
        ok = readback == target
        print(f"  active stage {before.active_stage} -> {target}, read back {readback}  "
              f"{'OK' if ok else 'MISMATCH'}")

        set_active_stage(mouse, before.active_stage)
        restored = read_settings(mouse).active_stage
        print(f"  restored to {restored}  {'OK' if restored == before.active_stage else 'FAILED'}")

        passed = ok and restored == before.active_stage
        print("\n" + ("WIRELESS PATH VERIFIED" if passed else "WIRELESS TEST FAILED"))
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
