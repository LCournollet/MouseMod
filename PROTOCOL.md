# ATK / COMPX mouse configuration protocol

Reverse-engineered from the ATK HUB web app bundle (`hub.atk.pro`, v3.2.16,
`index-O22l5tpG.js`) and verified live against an **ATK F1 EXTREME**.

## Device identity

| | VID | PID | Product string |
|---|---|---|---|
| Mouse (wired) | `0x373B` | `0x1045` (4165) | `ATK F1 EXTREME` |
| 8K dongle | `0x373B` | `0x1159` (4441) | `Wireless mouse 8k dongle Light` |

Bundle entry for the mouse:

```js
{vendorId:14139, productId:4165, usagePage:65284, usage:2,
 custom:{name:"ATK F1 EXTREME", sensor:PAW3950Ultra,
         mouseCidMid:"2,50", firmwareMark:"f1",
         noDpiRGB:true, noBottomButton:true}}
```

`mouseCidMid: "2,50"` is confirmed by the live `GetMouseCIDMID` response
(`cid=2, mid=0x32`).

## Transport

The WebHID filter advertises usage page `0xFF04`, but that collection is only a
7-byte feature report (report ID 6). Chrome exposes every collection of the
physical device through one `HIDDevice`, and the config traffic actually runs on:

**usage page `0xFF02`, usage `0x02` — report ID `8`, 16-byte input + 16-byte output.**

```
06 02 ff  Usage Page (0xFF02)
09 02     Usage (2)
a1 01     Collection (Application)
85 08       Report ID (8)
95 10 81 00   Input  (16 bytes)
95 10 91 00   Output (16 bytes)
c0
```

Windows paths (interface 1, collection 5):

```
\\?\HID#VID_373B&PID_1045&MI_01&Col05#...   mouse
\\?\HID#VID_373B&PID_1159&MI_01&Col05#...   dongle
```

Requests are **output reports** (not feature reports); the reply arrives as an
input report on the same collection.

## Frame format

16 bytes, prefixed by report ID `0x08` on the wire.

| Offset | Field |
|---|---|
| 0 | `commandId` |
| 1 | `commandStatus` (0 = ok, 1 = rejected/unsupported) |
| 2–3 | `eepromAddress`, **big endian** |
| 4 | `dataValidLen` |
| 5–14 | payload (10 bytes) |
| 15 | `checkSum` |

```python
checksum = (85 - (sum([0x08] + list(frame[:15])) & 0xFF)) & 0xFF
```

The report ID (`8`) participates in the checksum.

Responses read back through hidapi include the report ID, so everything shifts
by one:

| Offset | Field |
|---|---|
| 0 | report ID (`0x08`) |
| 1 | `commandId` (echoed — use this to match the reply) |
| 2 | `commandStatus` |
| 3–4 | address |
| 5 | `dataValidLen` |
| 6–15 | payload |

## Command IDs

```
 1 DownLoadData              14 GetCurrentConfig
 2 DownLoadDriverStatus      15 SetCurrentConfig
 3 GetWirelessMouseOnline    16 GetMouseCIDMID
 4 GetBatteryLevel           18 GetMouseVersion
 5 SetWirelessDonglePair     19 DongleExitPair
 6 GetWirelessDonglePairResult  20 Set4KRGBMode
 7 SetEEPROM                 21 Get4KRGBMode
 8 GetEEPROM                 22 SetFarDistanceMode
 9 RestoreFactory            23 GetFarDistanceMode
10 ReportMouseStatus         24 SetDongleLightMode
13 EnterUSBUpgradeMode       25 GetDongleLightMode
                             29 GetDongleVersion
90/91 mouse upgrade status reports
```

`GetCurrentConfig` / `SetCurrentConfig` switch the **onboard profile**.

## EEPROM map

Most scalar settings are stored as a value byte immediately followed by a
check byte: `crc = (85 - value) & 0xFF`. This was verified on every scalar read.

| Addr | Field |
|---|---|
| 0 | `reportRate` (+1 CRC) |
| 2 | `maxDpi` — number of active DPI stages (+3 CRC) |
| 4 | `currentDpi` — selected stage (+5 CRC) |
| 10 | `silentHeight` — LOD (+11 CRC) |
| 12, 20, 28, 36 | `dpi1/3/5/7` — two DPI stages per record, 4 bytes each: `xDpi, yDpi, dpiEx, crc` |
| 44, 52, 60, 68 | `dpi1/3/5/7Color` |
| 76–95 | DPI RGB + article lamp (effect, brightness, speed, enable) |
| 96, 100, 104, 108, 112, 116 | `key0..key5` — button mapping, 4 bytes each |
| 160 | `decorationLight` |
| 169 | `stabilizationTime` — debounce (+170 CRC) |
| 171 | `motionSync` (+172 CRC) |
| 173 | `closeLedTime` — sleep timer (+174 CRC) |
| 175 | `linearCorrection` (+176 CRC) |
| 177 | `rippleControl` (+178 CRC) |
| 179 | `moveCloseLights` (+180 CRC) |
| 181 | `sensorEnable` (+182) |
| 183 | `sensorTime` (+184) |
| 185 | `sensorMode` (+186) |
| 187 | `rfTxTime` (+188) |
| 189 | `angle` — sensor rotation |
| 227 | `rollingDelay` |
| — | `keyShortcuts0..5`, `macro0..15` (10-byte paged records) |

### Report rate encoding

`1000Hz=1, 500Hz=2, 250Hz=4, 125Hz=8, 2000Hz=16, 4000Hz=32, 8000Hz=64`

### DPI encoding (PAW3950Ultra)

Each stage is `xDpi, yDpi, dpiEx`. `dpiEx` carries the 9th/10th bits and the
scaling flags: bits 2–3 extend X, bits 6–7 extend Y, bit 0/4 double X/Y, bit
1/5 select the high-range formula.

```
low range  (dpi <= 10000):  raw = dpi/10 - 1        dpi = 10 * (raw + 1)
high range (dpi <= 30000):  raw = (dpi - 10050)/50  dpi = 50 * raw + 10050
above 30000: same as high range on dpi/2, with the doubling flag set
```

### Buttons

`buttonKeys = ["left","right","center","side1","side2","bottom"]`
mapped to addresses `key0..key5`.

Each entry is `[keyClass, value1, value2]` plus a check byte
(`85 - sum` of the three). Factory defaults, confirmed live:

```
key0 left   = 01 01 00   key3 side1  = 01 08 00
key1 right  = 01 02 00   key4 side2  = 01 10 00
key2 center = 01 04 00   key5 bottom = 02 01 00
```

`keyClass 6` means macro; `value2` then encodes the macro repeat mode.
The F1 EXTREME sets `noBottomButton`, so `key5` is unused on this model.

## Macros

16 slots, `768 + 384 * n` (so `macro0 = 768` … `macro15 = 6528`). Each slot is
read and written as ordinary 10-byte EEPROM pages.

Slot layout:

| Offset | Contents |
|---|---|
| 0–30 | fixed header, always `[8] + [2]*8 + [255]*22` |
| 31 | number of actions |
| 32… | actions, 5 bytes each |
| after the last action | `crc = (85 - sum(count byte + action bytes)) & 0xFF` |

An action is five bytes:

| Byte | Contents |
|---|---|
| 0 | bit 7 = key down, bit 6 = key up, neither = wheel; bits 0–2 = key type |
| 1 | `value1` — HID usage, modifier bitmask, mouse mask, or wheel direction |
| 2 | `value2` |
| 3–4 | delay in milliseconds, **big endian** |

Key types: `0` modifier, `1` key, `2` media, `3` power, `4` mouse, `5` move XY,
`6` wheel.

Verified encodings: `A` down = `81 04 00 …`, `A` up = `41 04 00 …`,
wheel = `06 ff 00 …`.

Modifiers are sent as type 0 with a bitmask rather than a usage:
`0xE0→0x01, 0xE1→0x02, 0xE2→0x04, 0xE3→0x08, 0xE4→0x10, 0xE5→0x20,
0xE6→0x40, 0xE7→0x80`.

A wheel notch is two actions: one carrying the direction (`1` up, `255` down)
and one carrying `0` to release it.

A slot holds at most **70** actions.

### Binding a macro to a button

Button assignment `[6, slot, mode]`, where `slot` is zero-based and `mode` is:

| Value | Meaning |
|---|---|
| 253 | repeat while the button is held |
| 254 | play once |
| 255 | repeat until any key is pressed |
| 1–252 | repeat that many times |

### A bug worth not copying

The web driver reads a slot as `chunks = 5 * count / 10`, then takes two actions
per chunk. For an odd action count that loop reads one action too many and
returns it as part of the macro. MouseMod reads `ceil(count * 5 / 10)` pages and
keeps exactly `count` actions.

## Live readout (F1 EXTREME, wired)

```
GetMouseCIDMID   -> cid=2 mid=50          matches the bundle's "2,50"
GetMouseVersion  -> 03 01
GetBatteryLevel  -> 5f 01 10 3f           0x5f = 95
GetWirelessMouseOnline -> online=1, rfId ab 04 e3

reportRate         @0   = 0x01   crc ok
maxDpi             @2   = 0x04   crc ok    4 DPI stages
currentDpi         @4   = 0x02   crc ok
silentHeight (LOD) @10  = 0x04   crc ok
dpi1               @12  = 27 27 00         (0x27+1)*10 = 400 DPI
key0               @96  = 01 01 00 53      left, crc 85-2 ✓
stabilizationTime  @169 = 0x00   crc ok
motionSync         @171 = 0x01   crc ok    ON
closeLedTime       @173 = 0x06   crc ok
linearCorrection   @175 = 0x00   crc ok
rippleControl      @177 = 0x00   crc ok
angle              @189 = 0x00   crc ok
```

## Dongle path

The dongle answers its own commands (`GetDongleVersion` -> 2,
`GetWirelessMouseOnline` -> mouse offline while the cable is plugged) but
rejects EEPROM reads when no mouse is live on RF. Wireless config must be
re-verified with the cable unplugged.

## Controller API surface

The web app's mouse controller (`$Jt`, provider COMPX) exposes exactly:

`getVersion`, `getPowerInfo`, `getMouseInfo`, `getMouseCidMid`,
`startPairing`/`getPairingStatus`, `getWirelessMouseOnline`, `resetDevice`,
`getCurrentKeyMatrix`/`setKey`, `setShortcutAction`,
`getLightConfig`/`setLightConfig`, dongle + decoration light,
`setMouseReportRate`, `setMouseDpiConfig`, `setMouseDpiValues`,
`setMouseDpiColors`, `setMousePerformance`, `getMouseFunction`/`setMouseFunction`
(motion sync, linear/ripple correction, sleep, debounce, LOD, far distance,
sensor angle, DPI list, rolling delay, bhop), `getMacro`/`setMacro` (16 slots),
`getProfile`/`setProfile`, `getDongleVersion`.

Everything above is reachable through `GetEEPROM`/`SetEEPROM` plus the handful
of dedicated command IDs — no firmware flashing involved.
