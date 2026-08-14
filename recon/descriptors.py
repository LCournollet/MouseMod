"""Dump and decode the HID report descriptor of every ATK collection."""

import hid

VID = 0x373B

ITEM_NAMES = {
    0x05: "Usage Page", 0x06: "Usage Page", 0x09: "Usage", 0x0A: "Usage",
    0x15: "Logical Min", 0x25: "Logical Max", 0x26: "Logical Max",
    0x75: "Report Size", 0x95: "Report Count", 0x85: "Report ID",
    0xA1: "Collection", 0xC0: "End Collection",
    0x81: "Input", 0x91: "Output", 0xB1: "Feature",
}


def decode(desc):
    """Minimal short-item walker: enough to see report IDs and sizes."""
    out = []
    i = 0
    while i < len(desc):
        prefix = desc[i]
        size = prefix & 0x03
        size = 4 if size == 3 else size
        tag = prefix & 0xFC
        key = prefix
        data = desc[i + 1 : i + 1 + size]
        value = int.from_bytes(data, "little") if data else None
        name = ITEM_NAMES.get(key) or ITEM_NAMES.get(tag) or f"item {key:#04x}"
        out.append(f"{name}={value:#x}" if value is not None else name)
        i += 1 + size
    return "  ".join(out)


def main():
    for d in sorted(hid.enumerate(), key=lambda x: (x["product_id"], x["path"])):
        if d["vendor_id"] != VID:
            continue
        dev = hid.device()
        try:
            dev.open_path(d["path"])
        except Exception as exc:
            print(f"{d['product_id']:04X} up={d['usage_page']:#06x} u={d['usage']:#x}"
                  f"  OPEN FAILED: {exc}")
            continue
        try:
            desc = bytes(dev.get_report_descriptor())
        except Exception as exc:
            desc = b""
            print(f"  descriptor error: {exc}")
        finally:
            dev.close()

        print(f"\n### PID {d['product_id']:04X}  usage_page={d['usage_page']:#06x} "
              f"usage={d['usage']:#x}  ({d['product_string']})")
        print(f"    path: {d['path'].decode()}")
        print(f"    raw ({len(desc)}B): {desc.hex(' ')}")
        if desc:
            print(f"    {decode(desc)}")


if __name__ == "__main__":
    main()
