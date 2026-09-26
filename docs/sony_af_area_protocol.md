# Sony remote AF-area protocol — findings from Creators' App v3.5.0

Derived 2026-09-26 by static analysis of Sony's own `Creators' App - v3.5.0.apk`
(jadx, `tools/decompile/jadx`). Interoperability work against hardware we own,
for the same PTP-IP surface `SonyPtpIpController.kt` already drives.

## Why this matters

`MainActivity.updateCameraTrackingRegion()` currently says:

> Sony's current PTP surface exposes autofocus but not a verified movable
> AF-area property. Existing gimbal centering puts the deterministic gold
> target under the camera's central AF area.

That is the reason the gimbal has to physically centre a piece before the Sony
can focus on it. **The property exists.** The app sets an AF area position
directly, so focus can be aimed at the piece wherever it sits in frame, without
moving the gimbal at all.

## What was found

Sony's app is not packed (≈30,200 classes across 3 dex files, ~11,000 under
`jp.co.sony`), so these came straight out of the enums.

### Operation codes (`ptpip.base.packet.EnumOperationCode`)

| Name | Code | Notes |
|---|---|---|
| `SDIO_SetExtDevicePropValue` | `0x9205` | already `OC_SetControlDeviceA` in our controller |
| `SDIO_ControlDevice` | `0x9207` | already `OC_SetControlDeviceB` |
| `SDIO_GetAllExtDevicePropInfo` | `0x9209` | already used — **reports per-property set-ability** |
| `SDIO_GetFocalMarkerInfo` | `0x920D` | not implemented here; focus-marker feedback |

### Device property codes (`ptpip.base.transaction.EnumDevicePropCode`)

| Name | Decimal | Hex | In our controller? |
|---|---|---|---|
| **`AFAreaPosition`** — "AF Area Position(x,y)" | 53810 | **`0xD232`** | **missing — this is the gap** |
| `FocusArea` | 53804 | `0xD22C` | yes (`PROP_FocusArea`) — the area *mode* |
| `FocusIndication` | 53779 | `0xD213` | yes — focus confirmation |
| `FunctionOfTouchOperation` | 53891 | `0xD2C3` | yes (`PROP_FunctionOfTouchOperation`) |
| `RemoteTouchOperationEnableStatus` | 53892 | `0xD2C4` | no — gates whether remote touch is accepted |
| `CancelRemoteTouchOperationEnableStatus` | 53893 | `0xD2C5` | no |
| `OnePushAFExecutionState` | 53861 | `0xD265` | no — one-push AF state |
| `FocusMagnifierPosition` | 53808 | `0xD230` | no |

### The (x,y) encoding — `ptpip.button.RangePosition`

Decompiled verbatim:

```java
public RangePosition(int x, int y) {
    AdbAssert.isTrue("MIN <= x", x >= 0);
    AdbAssert.isTrue("MIN <= y", y >= 0);
    AdbAssert.isTrue("x <= MAX_X", x <= 639);
    AdbAssert.isTrue("y <= MAX_Y", y <= 479);
    this.mValue = ((x << 16) & 0xFFFF0000) + (y & 0xFFFF);
}
```

So the payload is **one UINT32: x in the high 16 bits, y in the low 16**, in a
fixed **640 x 480** coordinate space — *not* sensor pixels, and not normalised
floats. `RangePosition implements IControlValue` and is handed straight to
`pressButton(...)`, alongside `EnumButton.CancelRemoteTouchOperation` for
clearing it (`ptp.remotecontrol.controller.liveview.TouchOperationController`).

Converting from our own detector output is therefore:

```
x = round(boxCx * 639)     // boxCx, boxCy are already normalised 0..1
y = round(boxCy * 479)
value = (x << 16) | y
```

## Proposed sequence (untested against the camera)

1. `SDIO_GetAllExtDevicePropInfo (0x9209)` — confirm `0xD232` is present and
   settable on the ZV-E10 II specifically. **Do this first**; everything below
   depends on it, and the answer comes from the camera, not from the app.
2. Set `FocusArea (0xD22C)` to a flexible-spot mode (value set still to be
   read off `EnumFocusArea`).
3. Set `AFAreaPosition (0xD232)` to the packed value above.
4. Trigger AF as today (`PROP_AutoFocus 0xD2C1` = 2 engage / 1 release).
5. Poll `FocusIndication (0xD213)` for the lock, as today.

## Open questions

- Whether `0xD232` is writable on this body, or only reports where the area is.
  Step 1 settles it.
- Whether it needs `RemoteTouchOperationEnableStatus (0xD2C4)` asserted first.
- The exact `EnumFocusArea` value for flexible spot.
- Whether the 640x480 space maps to the full frame or to the live-view crop.

## DJI Ronin v2.2.2 — not analysable this way

Its `classes.dex` defines **7 classes**, all `com.AppGuard.AppGuard`: the app is
commercially packed and the real code is decrypted in memory at runtime. The
BLE UUIDs (`0000FFF0/FFF4/FFF5`) and `com.dji.gimbal.GimbalCtrlCmd` /
`GimbalJni` appear only as strings in the encrypted blob — no class definitions,
so jadx cannot reach them.

Static RE would need a runtime DEX dump from a rooted device. The existing route
remains the practical one: the HCI snoop capture that produced `DumlProtocol.kt`
in the first place (507 frames, checksums verified 100%). Combined-axis motion
is not being pursued (operator decision, 2026-09-26), so the remaining gimbal
questions are speed and accuracy, which are answerable by empirical calibration
without touching the app.
