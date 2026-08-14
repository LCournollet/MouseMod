"""Codec checks plus a live read-only dump. Run: python -m tests.test_read"""

import sys

sys.path.insert(0, ".")

from mousemod import connect, read_settings
from mousemod.protocol import decode_dpi, encode_dpi, quantize_dpi


def test_codec():
    print("== DPI codec ==")
    # Known-good value read off the device: raw 0x27,0x27,0x00
    assert decode_dpi(0x27, 0x27, 0x00) == (400, 400), decode_dpi(0x27, 0x27, 0x00)
    print("  decode(0x27,0x27,0x00) = 400 DPI   ok")

    for dpi in (100, 400, 800, 1600, 3200, 6400, 10000, 12000, 20000, 26000, 30000, 42000):
        encoded = encode_dpi(dpi, dpi)
        back = decode_dpi(*encoded)[0]
        status = "ok" if back == dpi else f"-> {back}"
        print(f"  {dpi:>6} -> {encoded[0]:#04x} {encoded[1]:#04x} {encoded[2]:#04x}  {status}")
        assert quantize_dpi(dpi) == back
    print("  round-trip stable")


def test_live_read():
    print("\n== live read ==")
    mouse = connect()
    with mouse:
        print(f"  endpoint      : {mouse.endpoint.label}")
        cid, mid = mouse.cid_mid()
        print(f"  cid,mid       : {cid},{mid}")
        print(f"  firmware      : {mouse.firmware_version()}")
        battery = mouse.battery()
        print(f"  battery       : {battery['percent']}%  charging={battery['charging']}")

        s = read_settings(mouse)
        print(f"  report rate   : {s.report_rate_hz} Hz")
        print(f"  dpi stages    : {s.dpi_stages}  (active #{s.active_stage})")
        print(f"  lod           : {s.lod}")
        print(f"  motion sync   : {s.motion_sync}")
        print(f"  linear corr.  : {s.linear_correction}")
        print(f"  ripple ctrl   : {s.ripple_control}")
        print(f"  debounce      : {s.debounce_ms} ms")
        print(f"  sleep         : {s.sleep_seconds} s")
        print(f"  sensor angle  : {s.sensor_angle}")
        print("  buttons:")
        for name, action in s.buttons.items():
            print(f"    {name:<7} {action.action},{action.value1},{action.value2}"
                  f"  {action.describe()}")


if __name__ == "__main__":
    test_codec()
    test_live_read()
