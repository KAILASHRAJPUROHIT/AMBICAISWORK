# Sony ZV-E10 II jewellery capture capability audit

Date: 2026-08-23  
Camera: Sony ZV-E10 II / ZV-E10M2  
Current lens: Sony E PZ 16–50 mm F3.5–5.6 OSS II / SELP16502  
Android app path: `CaptureCam` diagnostics Sony PTP-IP-over-SSH panel

## Status legend

- **Use now**: supported by the camera and already available or directly implementable through the current PTP connection.
- **Validate**: code/property exists, but the exact behaviour still needs a controlled physical test on this camera.
- **Camera setup**: useful, but currently set on the camera menu rather than by the Android app.
- **Later**: useful future work; not needed for the safe first automatic loop.
- **Do not use**: reduces catalogue fidelity, conflicts with RAW, or creates unsafe target behaviour.
- **Unavailable**: not provided by this body/lens or not supported for this model by Sony's remote interfaces.

## Current end-to-end status

| Function | Status | Evidence |
|---|---|---|
| PTP-IP over Wi-Fi with Sony Access Authentication/SSH | Use now | Connected successfully to the physical camera at `192.168.0.14`. |
| Live View JPEG | Use now | Sustained about 10 fps; decoded frames around 160–190 KB. |
| Optical power zoom direction | Use now | Tele and wide direction physically confirmed. |
| Granular optical zoom | Validate | Implemented as 120 ms velocity pulses followed by fresh-frame measurement. |
| Half-press autofocus without shutter | Validate | Implemented through Sony S1 property only; no capture/S2 command in this path. |
| Deterministic gold detection | Validate | Strict hue, component, isolation, highlight, temporal and center-guide gates implemented. No ML/AI/network detector. |
| Gimbal pan/tilt | Use now | RSC 2 control and camera-mount axis mapping already established. |
| Combined gold → gimbal → AF → zoom loop | Validate | Build passes. Must be visually tested with automatic motion off first. |
| Full-resolution shutter/download | Blocked | Existing shutter sequence acknowledges commands but has not produced a physical capture. Do not call it until separately fixed. |

## Camera features, one by one

### Sensor, still image and file quality

| # | Feature | Jewellery value | Decision |
|---:|---|---|---|
| 1 | 26 MP APS-C back-illuminated Exmor R sensor, 6192 × 4128 stills | Strong base resolution for engraving, stone edges and later square crops. | Use now. |
| 2 | No optical low-pass filter | Preserves fine texture and edge detail; also increases moiré risk on repetitive patterns. | Use now; inspect fine mesh patterns. |
| 3 | 12-bit Sony ARW RAW | Maximum recoverable highlight/shadow and color information. | Use now after shutter/download is fixed. |
| 4 | Lossless compressed RAW | RAW quality without lossy RAW compression. | Preferred master format. |
| 5 | RAW + JPEG | RAW archival master plus immediately usable catalogue preview. | Preferred capture pair. |
| 6 | JPEG Extra Fine | Lowest JPEG compression offered by the camera. | Preferred catalogue JPEG. |
| 7 | HEIF | Efficient and high quality, but weaker compatibility with current catalogue/Ornate NX `.Jpg` workflow. | Do not use for production. |
| 8 | L/M/S image sizes | L is 26 MP; smaller sizes enable Smart Zoom but throw away resolution. | Always use L/26 MP. |
| 9 | 3:2 full-sensor aspect | Captures all sensor pixels; the tool can crop to the required square later. | Use 3:2, then deterministic crop. |
| 10 | Pixel Shift Multi Shooting | Body does not provide it. | Unavailable. |
| 11 | Lens shading compensation | Corrects corner darkness for compatible lenses. | Camera setup: Auto. |
| 12 | Chromatic aberration compensation | Reduces colored fringes around bright metal/stone edges. | Camera setup: Auto. |
| 13 | Distortion compensation | Improves geometry, especially at the kit lens's wide end. | Camera setup: Auto. |

### Focus and design-detail verification

| # | Feature | Jewellery value | Decision |
|---:|---|---|---|
| 14 | Fast Hybrid AF: phase + contrast detection | Fast coarse acquisition plus contrast confirmation. | Use now. |
| 15 | Up to 759 still-image phase-detection points | Wide frame coverage, but the tool must not let the camera choose a face/background. | Use with controlled center focus area. |
| 16 | AF-S / Single-shot AF | Jewellery is stationary; locks focus instead of continuously breathing. | Preferred mode. |
| 17 | Center Fix / Spot S-M / Expand Spot | Prevents people, cabinets and background objects from stealing focus. | Preferred: Spot M or Center Fix. |
| 18 | AF half-press/S1 | Lets the app focus without taking a photo. | Implemented; physical validation pending. |
| 19 | Aperture Drive in AF: Focus Priority | Prioritizes AF performance instead of quiet aperture operation. | Camera setup: Focus Priority. |
| 20 | DMF | Allows manual correction after autofocus for difficult reflective surfaces. | Useful operator fallback. |
| 21 | Manual Focus | Useful for locked macro sets, but unsuitable for automatic power-zoom framing without remote focus-position control. | Optional/manual. |
| 22 | Focus Magnifier | 1× or 6.1× view for checking tiny engraving. | Camera/operator diagnostic; remote PTP mapping not yet implemented. |
| 23 | AF in Focus Magnifier | Autofocuses a smaller region than normal Spot. | Later; useful for extreme detail but not required for first closed loop. |
| 24 | Peaking Display | Camera highlights sharp edges in MF/DMF. | Camera screen only for this workflow. Android computes its own sharpness score. |
| 25 | Focus Map | Movie-only; unavailable while streaming or with digital zoom. | Do not use for still catalogue automation. |
| 26 | Focus Bracket, 2–299 shots | Can create focus stacks for deep/high-relief jewellery where one plane is insufficient. | Later, after reliable shutter/download. |
| 27 | Subject Recognition AF | Recognizes humans, animals and birds—not jewellery. In the showroom it can prefer faces. | Disable. |
| 28 | Product Showcase Set | Designed to shift focus to a product held in front of a presenter, not isolated jewellery catalogue capture. | Disable. |
| 29 | App sharpness measurement | Normalized deterministic gradient energy inside the selected gold component; measured after AF and every zoom step. | Use now. |
| 30 | App focus gate | Requires three stable post-AF sharpness readings; retries AF twice, then blocks zoom and asks for distance/light correction. | Use now. |

### Zoom and framing

| # | Feature | Jewellery value | Decision |
|---:|---|---|---|
| 31 | 16–50 mm optical power zoom | Real optical framing without interpolation; controllable by Sony remote zoom property. | Use now. |
| 32 | Remote Zoom Speed: Variable or Fixed 1–8 | Slow fixed speed makes 120 ms pulses more repeatable. | Camera setup: Fixed, speed 1. |
| 33 | Short tele/wide velocity pulses | ZV-E10 II does not expose a verified absolute zoom position in this workflow. Closed-loop pulses are safer. | Use now: 120 ms, one pulse at a time. |
| 34 | Target-size feedback | Stops zoom when the selected component's long edge reaches about 55% of the frame. | Use now; tune from physical samples. |
| 35 | Re-focus after zoom | Zoom changes focus/field geometry; every tele pulse invalidates the old focus measurement. | Mandatory. |
| 36 | Optical zoom only setting | Preserves maximum quality and RAW compatibility. | Camera setup: Optical zoom only. |
| 37 | Smart Zoom | Crops the sensor at M/S size. It does not improve captured design detail. | Do not use. |
| 38 | Clear Image Zoom, up to ~2× for stills | Processed enlargement; unavailable with RAW/RAW+JPEG and disables important still AF/tracking behaviour. | Do not use. |
| 39 | Digital Zoom | Interpolated enlargement with visible quality loss. | Never use. |
| 40 | Step Zoom | Can jump to 1×/1.5×/2×/4× and may cross into processed zoom modes. | Do not use for precision framing. |
| 41 | Preset Focus/Zoom, five positions | Useful for repeatable physical stations with the same lens, but remote recall is not implemented and positions are lens-specific. | Later/manual. |
| 42 | Absolute optical zoom position through Sony SDK | Sony's published compatibility footnote for this feature does not include ZV-E10M2. | Unavailable/unsupported assumption; use feedback pulses. |

### Exposure, color and lighting

| # | Feature | Jewellery value | Decision |
|---:|---|---|---|
| 43 | Manual Exposure | Prevents brightness/color changes between catalogue items. | Preferred. |
| 44 | ISO 100–32000, expanded 50–102400 | Low ISO preserves fine detail and smooth gradients. | Use ISO 100; ISO 200 only if light requires. Avoid extended ISO 50. |
| 45 | ISO AUTO limits and minimum shutter | Useful when staff lighting varies, but less consistent than a fixed studio setup. | Fallback only. |
| 46 | Aperture control | Controls depth of field and diffraction. | Target f/7.1–f/8 on kit lens; validate per item depth. |
| 47 | Electronic shutter only, 1/8000–30 s | No mechanical vibration, but susceptible to LED banding. | Use with stable continuous lights and a flicker-safe shutter. |
| 48 | Variable Shutter | Fine shutter adjustment can suppress LED/fluorescent bands. | Use under shop lighting; start near 1/100 s for 50 Hz power and tune. |
| 49 | Exposure compensation ±5 EV | Already exposed through the PTP controller; useful if not in full Manual mode. | Validate; secondary to manual exposure. |
| 50 | 1,200-zone metering | Good general metering, but reflective gold can mislead automatic exposure. | Use only as a starting point. |
| 51 | Histogram | Reveals full-scene clipping/underexposure. | Use; app can compute its own live histogram later. |
| 52 | Zebra | Useful for protecting metal highlights. Sony remote peaking/zebra support is not published for this model through current SDK. | Camera screen/manual; app uses deterministic clipping metrics. |
| 53 | White balance 2500–9900 K | Essential for repeatable gold tone. | Use a measured custom WB under final lights. |
| 54 | Custom WB 1/2/3 | Locks a known neutral reference for the station. | Preferred over AWB. |
| 55 | AWB | Can shift from item to item as gold coverage changes. | Do not use for the final production preset. |
| 56 | D-Range Optimizer | Alters JPEG tone mapping and can reduce catalogue consistency. | Disable; preserve RAW. |
| 57 | Creative Look / Picture Profile | Can alter gold hue, contrast and sharpness. | Standard/Neutral only; disable stylized profiles. |
| 58 | Soft Skin Effect | Irrelevant and potentially destructive to fine detail. | Disable. |
| 59 | Lens Optical SteadyShot | Useful handheld; can cause micro-corrections on a locked gimbal/tripod. | Test OFF for stationary capture; enable only if vibration proves real. |
| 60 | In-body stabilization | Body has no still-image IBIS; relies on the lens. | Unavailable. |
| 61 | Built-in flash | Body has none; external flash sync is only 1/30 s. | Prefer high-CRI continuous diffused lighting. |

### Monitoring, networking and transfer

| # | Feature | Jewellery value | Decision |
|---:|---|---|---|
| 62 | Wi-Fi 5 GHz | Enough bandwidth for current 10 fps PTP Live View; lower interference than 2.4 GHz. | Use now with strong signal. |
| 63 | PTP-IP Live View | Supplies the deterministic detector and focus metric. | Use now. |
| 64 | USB 3.2 5 Gbps | Potentially faster/more stable control and transfer. | Later Android USB-host/PTP integration. |
| 65 | USB streaming: 1080p up to 60p; 4K up to 30p | Could reduce detection latency and improve focus measurement, but requires Android UVC integration and changes camera mode. | Later. |
| 66 | HDMI 4K 4:2:2 10-bit | Highest-quality monitor feed, but needs capture hardware and cabling. | Optional station upgrade, not required. |
| 67 | Original-size remote image transfer | Needed for catalogue output and design-quality validation. | Use after shutter/download is fixed. |
| 68 | Remote RAW/JPEG destination controls | Can save to destination only, camera only, or both. | Prefer camera + destination when reliable. |
| 69 | Sony Camera Remote SDK | Official support includes ZV-E10M2, but SDK targets Windows/Linux/macOS—not Android. | Possible PC bridge, not used in current direct-tablet app. |
| 70 | Sony Camera Remote Command/PTP | Officially supports ZV-E10M2 and PTP-IP. This is the protocol family used by the Android controller. | Use now; obtain official corporate command reference for long-term hardening. |
| 71 | Firmware 1.02 | Latest Sony-listed ZV-E10M2 firmware as of this audit; improves stability. | Verify camera body is 1.02 before production. |
| 72 | Cnct. while Power OFF | Allows a paired smartphone to connect by Bluetooth while the camera is off and browse/transfer images from the memory card through Creators' App. It does not start Remote Shooting, SSH/PTP-IP, Live View, zoom, focus or shutter control. | Optional for smartphone retrieval only. CaptureCam still requires camera power On and Remote Shooting On. |

## Lens reality: automation versus actual macro detail

The current SELP16502 is ideal for automatic framing because it has motorized 16–50 mm optical zoom. Its minimum focus distance is 0.25 m at wide and 0.30 m at tele, with only 0.215× maximum magnification. It can make good catalogue images of medium pieces, but its optical magnification—not the 26 MP sensor—is the limiting factor for very small engraving and stone-seat detail.

Sony's SEL30M35 30 mm F3.5 Macro is a true 1.0× macro lens. That is about 4.65 times the linear optical magnification of 0.215×. It has no power zoom, so the app can still point the gimbal and autofocus, but framing requires a fixed physical camera/item distance or a motorized rail. Recommended split:

- 16–50 mm power zoom: automated routine catalogue framing.
- 30 mm 1:1 macro: rings, hallmarks, engraving and diagnostic detail shots.

## Recommended production preset

1. Latest body firmware, currently Sony-listed 1.02.
2. Still mode; Manual Exposure.
3. RAW + JPEG; lossless compressed RAW; JPEG Extra Fine; L/26 MP; 3:2.
4. Optical zoom only.
5. Remote Zoom Speed: Fixed, 1 (Slow).
6. AF-S; Center Fix or Spot M; Subject Recognition AF Off; Product Showcase Off.
7. Aperture Drive in AF: Focus Priority.
8. ISO 100; f/7.1–f/8; start at 1/100 s under Indian 50 Hz lighting, then use Variable Shutter if bands remain.
9. Measured custom white balance under the final diffused high-CRI lights.
10. Lens shading/chromatic aberration/distortion compensation Auto.
11. Creative Look Standard/Neutral; Soft Skin Off; DRO Off.
12. Stabilization Off while mechanically locked; re-enable only if testing shows vibration.
13. Setup > Power Setting Option > Power Save Start Time: Off.
14. Setup > Power Setting Option > Power Save by Monitor: Does Not Link.
15. Setup > Power Setting Option > Auto Monitor OFF: Does not turn OFF.
16. Setup > USB > USB Power Supply: On. Keep a battery installed and verify the camera shows that USB power is actually being supplied.
17. Setup > Power Setting Option > Auto Power OFF Temp.: High for the fixed tripod station. Keep the body ventilated; this raises the shutdown threshold and does not remove thermal protection.

## Sources

- Sony ZV-E10M2 specifications: https://www.sony.co.in/electronics/support/e-mount-body-zv-e-series/zv-e10m2/specifications
- Sony ZV-E10M2 Help Guide menu/function index: https://helpguide.sony.net/ilc/2430/v1/en/contents/232h_list_of_menu_items_ilc2430.html
- Sony zoom types and quality limitations: https://helpguide.sony.net/ilc/2430/v1/en/contents/0401B_available_zoom.html
- Sony Remote Zoom Speed: https://helpguide.sony.net/ilc/2430/v1/en/contents/201h_zoom_speed_remote.html
- Sony focus modes and difficult reflective subjects: https://helpguide.sony.net/ilc/2430/v1/en/contents/0405C_focus_mode.html
- Sony focus areas: https://helpguide.sony.net/ilc/2430/v1/en/contents/0405C_autofocus_area.html
- Sony Focus Magnifier: https://helpguide.sony.net/ilc/2430/v1/en/contents/0405_focus_magni.html
- Sony AF in Focus Magnifier: https://helpguide.sony.net/ilc/2430/v1/en/contents/0405J_AF_in_focus_magni.html
- Sony Peaking Display: https://helpguide.sony.net/ilc/2430/v1/en/contents/0405M_peaking_display.html
- Sony Focus Bracket: https://helpguide.sony.net/ilc/2430/v1/en/contents/0407G_bracket_setting.html
- Sony RAW format: https://helpguide.sony.net/ilc/2430/v1/en/contents/0404M_file_format.html
- Sony lens compensation: https://helpguide.sony.net/ilc/2430/v1/en/contents/0414M_lens_comp.html
- Sony variable shutter: https://helpguide.sony.net/ilc/2430/v1/en/contents/201h_anti_flicker_setting.html
- Sony remote shooting destinations/formats: https://helpguide.sony.net/ilc/2430/v1/en/contents/201h_remote_shoot_setting.html
- Sony Camera Remote SDK model/OS support: https://support.d-imaging.sony.co.jp/app/sdk/en/index.html
- Sony Camera Remote Command/PTP model support: https://support.d-imaging.sony.co.jp/app/cameraremotecommand/en/index.html
- Sony ZV-E10M2 firmware 1.02: https://www.sony.com/electronics/support/software/00353892
- Sony Cnct. while Power OFF: https://helpguide.sony.net/ilc/2430/v1/en/print.pdf
- Sony Power Save Start Time: https://helpguide.sony.net/ilc/2430/v1/en/contents/0601B_power_save_start_time.html
- Sony Power Save by Monitor: https://helpguide.sony.net/ilc/2430/v1/en/contents/202h_power_save_by_monitor.html
- Sony Auto Monitor OFF: https://helpguide.sony.net/ilc/2430/v1/en/contents/201h_auto_monitor_off.html
- Sony USB Power Supply: https://helpguide.sony.net/ilc/2430/v1/en/contents/0601B_usb_power_supply.html
- Sony Auto Power OFF Temp.: https://helpguide.sony.net/ilc/2430/v1/en/contents/0601L_auto_power_off_temperature.html
- Sony SELP16502 specifications: https://www.sony.com/electronics/support/lenses-e-mount-lenses/selp16502/specifications
- Sony SEL30M35 macro specifications: https://www.sony.co.in/electronics/support/lenses-e-mount-lenses/sel30m35/specifications

## Hardware recovery log

### 2026-08-23 17:56 IST — manual DSLR restart

- The Sony became unreachable from the tablet at `192.168.0.14`; CaptureCam stayed running, selected phone fallback, and retried with bounded backoff.
- The operator manually restarted the DSLR. This was physical intervention, not an app-controlled wake/restart.
- The camera returned on the same IP. CaptureCam authenticated and restored Sony PTP/IP Live View automatically without an app or tablet restart.
- The RSC 2 remained connected through the recovery.
- Result: app-side reconnect/fallback recovery passed. Automatic recovery from a powered-off/unreachable body cannot replace a physical restart unless the camera itself keeps its remote-control network service available.

### 2026-08-23 18:28 IST — repeat dropout near the 30-minute boundary

- The first new connection failure was logged at `18:28:15`, approximately 32 minutes after the operator's `17:56` manual DSLR restart.
- Both the PC and tablet then reported `192.168.0.14` unreachable. CaptureCam itself remained foregrounded, retained phone-camera fallback and continued its capped 15-second Sony reconnect loop.
- The operator pressed the physical shutter several times and selected still-image mode. The body was awake, but its Wi-Fi remote service remained unreachable; a physical shutter wake is therefore not sufficient to restore this remote session.
- The timing matches the camera's selectable `30 Min` power-save interval. This is a strong diagnosis, not yet a direct read of the camera menu value.
- Required station hardwall: `Power Save Start Time = Off`, `Power Save by Monitor = Does Not Link`, `Auto Monitor OFF = Does not turn OFF`, and `USB Power Supply = On` with a battery inserted and confirmed USB-power indication.
- Secondary thermal hardening for the fixed mount: `Auto Power OFF Temp. = High` with unrestricted ventilation. Do not bypass thermal protection.
- `Cnct. while Power OFF` is not a substitute: it supports paired-phone card access while off, not CaptureCam's Remote Shooting/PTP-IP Live View control.
