"""Recon phase 2 - read-only protocol probe.

Speaks the COMPX/ATK vendor protocol extracted from the ATK HUB bundle:

  report id 8, 16-byte output report:
    [0] commandId
    [1] commandStatus
    [2:4] eepromAddress (big endian)
    [4] dataValidLen
    [5:15] payload
    [15] checksum = (85 - (sum([8] + bytes[0:15]) & 0xFF)) & 0xFF

Only read commands are issued here. Nothing is written to the device.
"""

import sys
import time

import hid

VID = 0x373B
# Config endpoint: usage page 0xFF02 / usage 2 carries report id 8,
# 16-byte input + 16-byte output. (0xFF04 is a 7-byte feature collection.)
CONFIG_USAGE_PAGE = 0xFF02

CMD = {
    "GetWirelessMouseOnline": 3,
    "GetBatteryLevel": 4,
    "GetEEPROM": 8,
    "GetCurrentConfig": 14,
    "GetMouseCIDMID": 16,
    "GetMouseVersion": 18,
    "GetDongleVersion": 29,
}

# EEPROM address map (subset), from CZt.Address in the bundle
ADDR = {
    "reportRate": 0,
    "maxDpi": 2,
    "currentDpi": 4,
    "silentHeight": 10,
    "dpi1": 12,
    "key0": 96,
    "stabilizationTime": 169,
    "motionSync": 171,
    "closeLedTime": 173,
    "linearCorrection": 175,
    "rippleControl": 177,
    "angle": 189,
}


def build(command_id, address=0, valid_len=0, payload=b""):
    buf = bytearray(16)
    buf[0] = command_id
    buf[1] = 0
    buf[2] = (address >> 8) & 0xFF
    buf[3] = address & 0xFF
    buf[4] = valid_len
    buf[5 : 5 + len(payload)] = payload
    buf[15] = (85 - (sum([8] + list(buf[:15])) & 0xFF)) & 0xFF
    return bytes(buf)


def find(usage_page=CONFIG_USAGE_PAGE, usage=2):
    return [
        d
        for d in hid.enumerate()
        if d["vendor_id"] == VID
        and d["usage_page"] == usage_page
        and d["usage"] == usage
    ]


def transfer(dev, frame, timeout_ms=1000):
    """Responses come back as: [0]=reportId(8) [1]=commandId [2]=status
    [3:5]=address [5]=dataValidLen [6:16]=data."""
    dev.write(b"\x08" + frame)
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        data = dev.read(64, 200)
        if data and len(data) > 1 and data[1] == frame[0]:
            return bytes(data)
    return None


def probe(info):
    label = f"{info['product_string']} ({info['vendor_id']:04X}:{info['product_id']:04X})"
    print(f"\n=== {label} ===")
    print(f"    {info['path'].decode()}")
    dev = hid.device()
    dev.open_path(info["path"])
    try:
        for name, cid in CMD.items():
            resp = transfer(dev, build(cid))
            if resp is None:
                print(f"  {name:<24} -> no response")
            else:
                print(f"  {name:<24} -> status={resp[2]:02x} data={resp[6:16].hex(' ')}")

        print("  --- EEPROM reads ---")
        for name, addr in ADDR.items():
            resp = transfer(dev, build(CMD["GetEEPROM"], address=addr, valid_len=10))
            if resp is None:
                print(f"  {name:<24} @{addr:<4} -> no response")
            else:
                vals = resp[6:16]
                crc_ok = ((85 - vals[0]) & 0xFF) == vals[1]
                print(f"  {name:<24} @{addr:<4} -> {vals[0]:#04x} "
                      f"(crc {'ok' if crc_ok else 'NO'})  raw={vals.hex(' ')}")
    finally:
        dev.close()


def main():
    devices = find()
    if not devices:
        print("No ATK vendor (0xFF04) interface found.")
        return 1
    for info in devices:
        try:
            probe(info)
        except Exception as exc:
            print(f"  !! {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
