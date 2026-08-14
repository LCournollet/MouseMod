"""Live write round-trip. Every change made here is restored before exit.

Run: python -m tests.test_write
"""

import sys

sys.path.insert(0, ".")

from mousemod import connect, read_settings
from mousemod.settings import (
    set_active_stage,
    set_dpi_stages,
    set_lod,
    set_motion_sync,
)


def show(label, s):
    print(f"  {label:<10} rate={s.report_rate_hz} dpi={s.dpi_stages} "
          f"active={s.active_stage} lod={s.lod} sync={s.motion_sync}")


def main():
    mouse = connect()
    with mouse:
        original = read_settings(mouse)
        print("== before ==")
        show("original", original)

        failures = []

        def check(name, expected, actual):
            ok = expected == actual
            print(f"  {name:<16} expected {expected!r:<28} got {actual!r:<28} "
                  f"{'OK' if ok else 'MISMATCH'}")
            if not ok:
                failures.append(name)

        try:
            print("\n== writing ==")

            new_stage = (original.active_stage + 1) % len(original.dpi_stages)
            set_active_stage(mouse, new_stage)
            check("active stage", new_stage, read_settings(mouse).active_stage)

            new_dpi = list(original.dpi_stages)
            new_dpi[0] = 500 if new_dpi[0] != 500 else 600
            written = set_dpi_stages(mouse, new_dpi)
            check("dpi stages", written, read_settings(mouse).dpi_stages)

            new_lod = 1 if original.lod != 1 else 2
            set_lod(mouse, new_lod)
            check("lod", new_lod, read_settings(mouse).lod)

            set_motion_sync(mouse, not original.motion_sync)
            check("motion sync", not original.motion_sync,
                  read_settings(mouse).motion_sync)

        finally:
            print("\n== restoring ==")
            set_dpi_stages(mouse, original.dpi_stages)
            set_active_stage(mouse, original.active_stage)
            set_lod(mouse, original.lod)
            set_motion_sync(mouse, original.motion_sync)

            after = read_settings(mouse)
            show("restored", after)
            identical = after.to_dict() == original.to_dict()
            print(f"\n  state identical to original: {identical}")
            if not identical:
                failures.append("restore")

        print("\n" + ("ALL CHECKS PASSED" if not failures
                      else f"FAILED: {', '.join(failures)}"))
        return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
