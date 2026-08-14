"""Diagnostic: figure out the exact transport (output vs feature, report size)."""

import time
import traceback

import hid

VID = 0x373B


def build(command_id, address=0, valid_len=0):
    buf = bytearray(16)
    buf[0] = command_id
    buf[2] = (address >> 8) & 0xFF
    buf[3] = address & 0xFF
    buf[4] = valid_len
    buf[15] = (85 - (sum([8] + list(buf[:15])) & 0xFF)) & 0xFF
    return bytes(buf)


def show_descriptor(dev):
    for attr in ("get_report_descriptor", "get_input_report"):
        print(f"    has {attr}: {hasattr(dev, attr)}")
    if hasattr(dev, "get_report_descriptor"):
        try:
            desc = dev.get_report_descriptor()
            print(f"    report descriptor ({len(desc)} bytes): {bytes(desc).hex(' ')}")
        except Exception as exc:
            print(f"    descriptor error: {exc}")


def try_write(dev, frame, pad_to):
    payload = b"\x08" + frame + b"\x00" * (pad_to - 1 - len(frame))
    n = dev.write(payload)
    print(f"    write({len(payload)}B) -> {n}")
    return n


def main():
    targets = [
        d
        for d in hid.enumerate()
        if d["vendor_id"] == VID and d["usage_page"] == 0xFF04 and d["usage"] == 2
    ]
    frame = build(18)  # GetMouseVersion
    print(f"frame: {frame.hex(' ')}\n")

    for info in targets:
        print(f"=== {info['product_string']} {info['product_id']:04X} ===")
        dev = hid.device()
        try:
            dev.open_path(info["path"])
        except Exception as exc:
            print(f"    open failed: {exc}")
            continue
        show_descriptor(dev)

        for size in (17, 33, 65):
            try:
                if try_write(dev, frame, size) <= 0:
                    continue
                for _ in range(5):
                    data = dev.read(size, 300)
                    if data:
                        print(f"    READ: {bytes(data).hex(' ')}")
                        break
                else:
                    print("    read: empty")
            except Exception:
                print("    " + traceback.format_exc().strip().splitlines()[-1])

        print("    -- feature report attempt --")
        try:
            n = dev.send_feature_report(b"\x08" + frame)
            print(f"    send_feature_report -> {n}")
            data = dev.get_feature_report(8, 17)
            print(f"    get_feature_report -> {bytes(data).hex(' ')}")
        except Exception:
            print("    " + traceback.format_exc().strip().splitlines()[-1])

        dev.close()
        print()


if __name__ == "__main__":
    main()
