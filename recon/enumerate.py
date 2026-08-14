"""Recon phase 1 - read-only HID enumeration.

Lists every HID interface exposed by ATK devices (VID 0x373B, 0x3554) plus a
summary of everything else, so we can identify which interface carries the
vendor/config protocol. Nothing is written to any device.
"""

import hid

ATK_VIDS = {0x373B, 0x3554}


def fmt(d):
    return (
        f"  path         : {d['path'].decode('utf-8', 'replace')}\n"
        f"  vid:pid      : {d['vendor_id']:04X}:{d['product_id']:04X}\n"
        f"  manufacturer : {d.get('manufacturer_string')!r}\n"
        f"  product      : {d.get('product_string')!r}\n"
        f"  serial       : {d.get('serial_number')!r}\n"
        f"  release      : {d.get('release_number'):#06x}\n"
        f"  usage_page   : {d.get('usage_page'):#06x}\n"
        f"  usage        : {d.get('usage'):#06x}\n"
        f"  interface    : {d.get('interface_number')}\n"
    )


def main():
    devs = hid.enumerate()
    atk = [d for d in devs if d["vendor_id"] in ATK_VIDS]

    print(f"=== ATK interfaces ({len(atk)}) ===\n")
    for d in sorted(atk, key=lambda x: (x["product_id"], x["path"])):
        print(fmt(d))

    print(f"=== other HID devices ({len(devs) - len(atk)}) ===")
    seen = set()
    for d in devs:
        if d["vendor_id"] in ATK_VIDS:
            continue
        key = (d["vendor_id"], d["product_id"])
        if key in seen:
            continue
        seen.add(key)
        print(
            f"  {d['vendor_id']:04X}:{d['product_id']:04X}  "
            f"{d.get('manufacturer_string')} / {d.get('product_string')}"
        )


if __name__ == "__main__":
    main()
