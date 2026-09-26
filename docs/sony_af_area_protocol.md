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
| `FunctionOfTouchOperation` | 53891 | `0xD283` | yes (`PROP_FunctionOfTouchOperation`) |
| `RemoteTouchOperationEnableStatus` | 53892 | `0xD284` | yes (`PROP_RemoteTouchOperationEnable`) |
| `CancelRemoteTouchOperationEnableStatus` | 53893 | `0xD285` | yes (`PROP_CancelRemoteTouchOperationEnable`) |
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

## Probe against the real ZV-E10 II — 2026-09-26

Run on the tablet via `SonyPtpIpController.logSonyPropertyProbe()` (CaptureCam
1.1.4), which dumps everything `0x9209` reports. **366 properties, 250
writable.** Result:

```
[PROBE] 0xD232 NOT REPORTED by this body      <- AFAreaPosition absent
[PROBE] 0xD265 NOT REPORTED by this body      <- OnePushAFExecutionState absent
[PROBE] 0xD230 NOT REPORTED by this body      <- FocusMagnifierPosition absent
[PROBE] 0xD22C writable=true enabled=true value=518 supported=[1,2,259,514,518]
[PROBE] 0xD283 writable=true enabled=true value=9 supported=[9,8,11,10,5,1]
[PROBE] 0xD284 writable=false enabled=true value=1   <- remote touch AVAILABLE
[PROBE] 0xD285 writable=false enabled=false value=0
```

**So the original hypothesis was wrong**: `AFAreaPosition (0xD232)` is in Sony's
app because the app ships for many bodies, but the ZV-E10 II does not expose it
as a device property at all. Do not build on it.

## What actually works: a CONTROL code, not a property

The position never was a device property. `RemoteTouchOperation` is an
`AbstractButton` whose value is the `RangePosition`, and buttons carry a
**control code** (`ptpip.base.transaction.EnumControlCode`), sent through
`SetControlDeviceA/B` — the identical mechanism this controller already uses for
the shutter:

| EnumControlCode | Decimal | Hex | Note |
|---|---|---|---|
| `S1Button` | 53953 | `0xD2C1` | already ours as `PROP_AutoFocus` |
| `S2Button` | 53954 | `0xD2C2` | already ours as `PROP_Capture` |
| **`RemoteTouchOperation`** | 53988 | **`0xD2E4`** | carries the packed (x,y) |
| **`CancelRemoteTouchOperation`** | 53989 | **`0xD2E5`** | clears it |

That `S1Button`/`S2Button` land exactly on the two codes we already drive
confirms the reading: these are control codes, and `setControlDeviceA/B` already
takes a 4-byte payload, so no new transport is needed.

`RemoteTouchOperationEnableStatus (0xD284)` reads **1** on this body, i.e. the
camera is advertising that it will accept remote touch.

## Proposed sequence (not yet implemented or tested)

1. `setControlDeviceB(0xD2E4, (x shl 16) or y, byteWidth = 4)` with
   `x = round(cx * 639)`, `y = round(cy * 479)` from the detector's normalised
   box centre.
2. Trigger AF as today (`0xD2C1` = 2 engage / 1 release).
3. Poll `FocusIndication (0xD213)` for the lock, as today.
4. `setControlDeviceB(0xD2E5, ...)` to clear the point between items.

## Open questions

- Whether `0xD2E4` is accepted while `FocusArea (0xD22C)` is 518, or whether the
  area mode must first move to a flexible-spot value from `[1, 2, 259, 514, 518]`.
- Whether the 640x480 space maps to the full frame or to the live-view crop.
- Whether the point persists across shots or needs re-issuing per item.

All four are answerable in one live test against the camera, since the cancel
code gives a clean way back.

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
