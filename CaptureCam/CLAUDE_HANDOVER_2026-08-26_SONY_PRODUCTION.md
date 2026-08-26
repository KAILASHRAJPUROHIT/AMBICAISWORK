# CaptureCam Sony Production Handover — 2026-08-26

## Purpose and authority

This document is the current handover for the Sony ZV-E10 II CaptureCam work. It supersedes conclusions in `CLAUDE_HANDOVER_2026-08-23_SONY_LIVEVIEW.md` wherever the two conflict. The older document remains useful only for historical logs and protocol discovery.

The code is a production candidate, not a production release. The latest build compiles, installs, and sustains approximately 25 FPS. The final five-frame tag consensus and automatic focus-backoff ladder have not yet had a positive physical test with a real tag and ornament after the latest install. Do not call the system production-ready until the acceptance test in this document passes.

Do not begin with speculative edits. Reproduce the current candidate first, collect the exact timing trace, then fix only observed failures.

## Executive state

- Active branch: `codex/sony-production-2026-08-25`
- Current code commit before this handover: `295a1d9` — `Add five-frame Sony tag consensus burst`
- Previous stabilization commit: `ed19e8d` — `Stabilize Sony production capture and focus recovery`
- Prior capture-speed commit: `d04b305` — `Speed and stabilize Sony original capture`
- Clean pre-Sony checkpoint: branch `checkpoint-pre-sony-2026-08-23`, commit `3666fea8d7015477653bd409a0ad83f0ae81b73e`
- First Sony draft after that checkpoint: `2fa40ff`
- Do not merge the Sony branch into `master` or `production-legacy-flow` until the physical E2E acceptance test passes.
- Latest APK was built and installed successfully on the Redmi tablet.
- The app was deliberately force-stopped at the end of testing. ADB remained connected. Camera, gimbal, and server live state must therefore be re-established before testing.
- Tablet ADB endpoint: `192.168.0.22:5555`
- Sony camera address used by the integration: `192.168.0.14`
- No Sony password or other credentials are included here. Use the existing app preferences/configuration.

## Repositories and push policy

The branch must remain present and identical in both repositories:

1. Organisation: `https://github.com/AradhanaJewellers/aradhana-catalogue-tool.git`
2. Personal: `https://github.com/KAILASHRAJPUROHIT/ambic-catalogue-studio.git`

Local remotes:

- `origin` fetches from the organisation repository and currently has push URLs for both repositories.
- `personal` fetches and pushes to the personal repository.

Push and verify both explicitly after any handover or production-candidate change. Never assume a successful push to one means the other is current.

## User requirements that must not drift

The required production flow is:

1. Detect the jewellery label rapidly and reliably.
2. Resolve the label/category using the authoritative laptop/server data.
3. Reset the gimbal to centre and the 16–50 PZ lens fully wide for the next label.
4. Guide and automatically centre the ornament.
5. Use Sony focus information plus deterministic local image measurements. No local LLM or cloud detector.
6. Capture either one angle or three angles, as selected by the operator.
7. One physical shutter actuation per requested angle. No accidental duplicate capture.
8. Preserve the full-resolution original. Current verified transfer is original JPEG; RAW delivery is not yet proven.
9. Combine three selected views without reducing source detail.
10. Stage locally and release the UI for the next item while upload continues in the background.
11. Keep DSLR mode and smartphone mode as an explicit hard switch. Do not silently fall back from Sony to phone capture.

The camera and tablet stay on the current LAN/Wi-Fi topology. The user explicitly dropped camera-hotspot and USB-to-tablet alternatives. The camera is physically distant from the laptop/tablet USB path.

## What is implemented now

### 1. Sony live-view transport

`SonyPtpIpController.kt` now owns a persistent HTTP live-view pump over its Sony SSH direct-TCPIP channel.

Key properties:

- One pump owns the stream.
- JSch input buffer: 1 MB.
- Channel packet handling: 64 KB.
- Frames are delivered through a latest-one-frame handoff.
- Stale frames are dropped instead of queued. This prevents the former multi-second growing preview delay.
- Live-view stall timeout: `750 ms`.
- Transport-health poll: `250 ms`.
- Transport-health log interval: `15,000 ms`.
- Reopen/recovery is serialized to avoid the old proactive-refresh and reactive-pump paths fighting over one Sony session.

`SonyProductionCamera.kt`:

- Uses three pooled mutable Bitmap buffers.
- Runs the live loop on a display-priority thread.
- Does not add a pacing sleep.
- Records source FPS, decoded FPS, dropped frames, reopen count, source gap, and frame age.

`MainActivity.kt`:

- Uses a latest-wins UI renderer.
- Sony preview render cadence is `40 ms`, targeting 25 FPS.
- Scanner/detection work must not queue UI frames.

Last observed candidate behaviour:

- Approximately `24.6–25.4 FPS` during healthy operation.
- One earlier run recorded one dropped frame over 1,503 frames.
- A sporadic maximum source gap of about `278 ms` was observed after the improvements.
- Before the improvements, Sony-source stalls reached roughly `775 ms`; barcode ML work remained only about `9–32 ms`. The scanner was not the original source-stall cause.
- Latest start after `295a1d9`: full-wide reset completed at `19:56:02.605`; preview reported `25.0 FPS` initially with `dropped=0`.

Still unproven:

- Ten-minute zero-backlog soak.
- Clean recovery across the camera's previously observed approximately 82–84 second connection boundary.
- No frame-age growth during tag scanning and capture transfer.

### 2. Five-frame label consensus

Commit `295a1d9` adds the bounded Sony label burst in `MainActivity.kt`.

Behaviour:

- Normal scanning continues until the first non-empty decoded label.
- That first decode starts a five-frame confirmation burst.
- The burst uses the current Sony-native live-view JPEG plus the next four distinct frames.
- Each frame is decoded immediately, in arrival order, on the single barcode executor.
- During the burst, the analysis interval is zero. The next frame enters once the prior ML task finishes.
- Acceptance requires at least three matching votes out of five.
- The middle JPEG among the matching votes becomes label evidence.
- A failed/unstable burst returns to scanning with: `Label changed or blurred — hold it steady`.
- UI progress: `Confirming label N/5…`.
- Tag scanning does not start until the full-wide lens reset finishes.
- The old forced two-second tag preview was removed.
- The old UI-thread Bitmap-to-JPEG recompression path was removed.
- `SonyProductionCamera.currentLiveViewJpeg()` returns a copied native live-view JPEG.
- The category server remains authoritative after local consensus.
- `stableTagCode` is `@Volatile`.

Constants:

- `SONY_TAG_BURST_FRAMES = 5`
- `SONY_TAG_BURST_MAJORITY = 3`

Important scope: “visible clearly” currently means the first successful barcode decode. There is no separate pre-decode computer-vision label-presence trigger.

Status: compiled and installed. Not physically confirmed after the final install because no real tag was presented before testing stopped.

### 3. Paired-jewellery detector and focus fix

The live failure on a TOPS 22 pair was diagnosed:

- Full-frame detection found two earrings.
- The union centre lay in the empty gap between them.
- The old code locked a small centred category ROI around that empty gap.
- ROI gold detection then failed, unlocked, reacquired full-frame, and repeated every frame.
- Gimbal and autofocus followed that oscillation, producing the visible “panic”.

Fix in `MainActivity.kt`:

- `isSplitPairProfile` recognises `HOOP_PAIR`, `STUD_PAIR`, and `DROP_PAIR`.
- Paired categories remain on the full-frame detector and do not lock the small centred composition ROI.
- Pair midpoint remains valid for gimbal composition/centring.
- Autofocus and sharpness use one real gold cluster, currently the left cluster, rather than the empty midpoint.
- A single-item ROI lock needs at least three genuine gold points inside the proposed ROI.
- Automatic Sony touch-AF is limited to seven commands per physical pose.
- Manual tap-to-focus bypasses this automatic circuit breaker.

The first pair-aware live trace placed focus on a real left earring around `x=0.3375, y=0.3396` instead of the empty centre. A complete physical E2E confirmation remains required.

### 4. Automatic focus-backoff ladder

The current policy implements the user's requirement: when detail remains blurred, zoom one step wider, settle, refocus, re-evaluate, and repeat until focused or fully wide.

Key behaviour:

- Focus evaluation delay: `1,000 ms`.
- Maximum automatic AF commands per physical pose: `7`.
- `backOffOneZoomForFocus()` divides the current zoom by `ZOOM_STEP_RATIO = 1.25`.
- The new lower value becomes `maxUsableZoom`, a hard ceiling for the rest of that pose.
- Current AF-attempt state is cleared, but the pose-wide AF budget remains.
- The existing `smoothZoomTo` path performs the move and settle.
- Every later zoom ceiling uses `min(hardware ceiling, maxUsableZoom)`, preventing a return to a failed zoom level.
- This applies to main and side-angle paths.
- At fully wide unresolved focus, UI says: `Still blurred at full wide — move the stand slightly back`.
- The old active `Sony cannot confirm detail` dead-end was removed from `MainActivity`.

An older message, `Focus not confirmed — check distance/light`, still exists in `SonyGoldServoController.kt`. That controller is dormant because `TRACKING_PIPELINE_ACTIVE = false`; do not edit or reactivate it blindly.

Important fixed defect: `triggerCameraAutoFocus()` returns a Boolean. The caller records an AF attempt only when the Sony command was actually dispatched. Previously the 650 ms command cooldown could reject a command after the caller had permanently marked the level attempted.

Sony AF details:

- Uses `RemoteTouchOperation`.
- Earlier measured command RTT: approximately `9–30 ms`.
- It does not require SSH teardown.
- Tag focus area: Wide, property value `1`.
- Jewellery focus area: Tracking Spot L, property value `518`.
- `isCameraFocusLocked` accepts Sony focus indication 2/6 or state 5 only with exact command acknowledgement, fresh focal metadata, and local sharpness confirmation.
- UI may also display raw Sony focus state for diagnosis.

Status: compiled and installed. The full focus ladder has not yet been physically observed after the latest install.

### 5. Camera quality/control profile

The startup profile currently requests:

- Exposure mode: Manual (`1` in the latest property logs).
- ISO: Auto (`16777215`).
- White balance: Auto (`2`).
- Still format: RAW+JPEG (`2`).
- JPEG quality: Extra Fine (`1`).
- Image size: L (`1`).
- Transfer size: original JPEG (`1`).
- RAW type: lossless compressed (`6`).
- Aspect: 3:2 (`1`).
- DRO: off (`1`).
- Creative Look: Standard (`1`).
- Aperture: f/8 (`800`).
- Shutter: 1/100.
- Exposure compensation: 0 initially.
- AF mode: AF-C (`32772`).
- Metering: Multi (`32769`).
- Focus area changes from Wide for tags to Tracking Spot L for jewellery.

Latest logs showed the hardwall settings applying without property mismatch. This does not prove every setting produces ideal jewellery exposure in every light-box condition.

Auto-exposure adjustment occurs after framing. Earlier over-darkening was reduced by gating and serialising control changes, but production exposure quality still needs physical validation.

Critical limitation: the E2E flow has verified transfer of original Sony JPEG files only, typically `DSC*.JPG` around 17–18 MB. The camera reports RAW+JPEG, but RAW capture and transfer through the app are not yet proven. Do not claim that RAW is delivered until an `.ARW` is received, staged, uploaded, and inspected.

### 6. Focus, peaking, exposure, and composition overlays

The tablet overlays include:

- Sony-style focus map: warm/clear/cool focus-plane assistance.
- Peaking over locally measured sharp micro-detail.
- Dual clipping overlay: red for highlight clipping and blue for shadow clipping.
- Histogram and numeric under/over clipping percentages.
- Category silhouette and mount-rail guidance.
- Target scale/occupancy and stand-distance assistance.

These overlays are calculated by CaptureCam from Sony live-view pixels. They are not a mirror of Sony's on-camera OSD. Genuine Sony AF/focal metadata is used where available, but peaking, histogram, clipping, and local sharpness are app calculations.

Relevant files:

- `CameraAssistAnalyzer.kt`
- `BoundsOverlayView.kt`
- `CaptureCompositionProfile.kt`
- `CaptureHardwareProfile.kt`
- `StandDistanceGuide.kt`
- `MaterialDetector.kt`

`CaptureCompositionProfile.kt` maps stock categories to silhouettes, mount guidance, target aspect/area, and physical-size estimates.

Current occupancy hard gate is `CAPTURE_MIN_OCCUPANCY = 0.75`. The user verbally requested roughly 70% frame occupancy. Do not silently change the production gate; compare actual framing and agree the final tolerance based on captured examples.

### 7. Gimbal and item tracking

- Gimbal: DJI RSC2 over BLE through `RSC2Controller.kt`.
- The app uses deterministic gold-colour geometry and Sony metadata, not an LLM.
- `DINO_SERVO_ENABLED = false`.
- `TRACKING_PIPELINE_ACTIVE = false` for the old `SonyGoldServoController` path.
- The gimbal performs fine centring. It cannot create meaningful side angles by simply panning around a stationary flat subject.
- For side views, the operator physically rotates the ornament/stand and confirms the angle.
- When the operator starts the next item, the intended behaviour is gimbal centre plus lens fully wide to make the next label easy to find.
- The 16–50 PZ lens has a maximum optical ratio of 3.125 (`50/16`).
- Full-wide reset holds the wide command for 1,800 ms with at most three bounded attempts.

### 8. Still capture and per-angle shutter count

The old handover's conclusion that the full-resolution shutter path was blocked is obsolete. Sony shutter and original download work physically.

Current production code:

- `SonyProductionCamera.captureStill` requests one verified original per view.
- `MainActivity.captureFullRes` explicitly performs one physical shutter per requested angle.
- The former two-frame/best-of-five production capture was removed because it doubled shutters and added about 25–30 seconds per item.
- A burst diagnostic remains available through `BleDiagnostics.testBurst`; it is not the production flow.

The last documented E2E run is in `E2E_TEST_2026-08-25_LOCKET_22.md`. It predates the latest tag/focus changes and must not be treated as final acceptance.

That run recorded:

- First valid tag: `18:23:50.820`.
- Jewellery phase: `18:23:53.417`.
- First original `DSC01491.JPG`: `18:24:56.484`.
- Fifth original `DSC01495.JPG`: `18:25:45.507`.
- Next-tag ready: `18:25:51.087`.
- Total: approximately `120.267 s`.
- Individual originals: approximately 17–18 MB.
- Total transfer per original: about 4.8–5.5 seconds.
- Download portion: about 3.7–4.3 seconds.

Five originals appeared although the normal target was three. Operator interaction or retakes may have contributed, and that trace lacked per-view sequence IDs. Current source intends exactly one shutter per requested view, but a new trace must prove it.

Live view remains active while the original transfers. However, the per-angle callback/UI progression may still depend on transfer completion. The user's target is for angle 2 positioning to begin while angle 1 transfers, and for any blur warning to arrive asynchronously. Validate the present timing before redesigning it.

The operator can choose after the main shot:

- `Complete` for an item needing only one angle.
- `Proceed to angle 2` for the three-angle flow.

### 9. Local staging and background upload

`CaptureUploadQueue.kt` stages capture files locally before the UI advances. WorkManager then handles server upload in the background.

Expected behaviour:

- `uploadCapturedSet()` begins full-wide lens reset immediately and in parallel.
- A successful local stage releases the operator to the next item.
- Network upload does not keep the UI on a blocking upload screen.
- Job states include queued, uploading, and needs-review.
- Default server address is `https://ARADHANA.local:7660`.
- The old fixed Ethernet URL is mapped to the mDNS endpoint.

Laptop LAN-to-Wi-Fi survival is intended through mDNS, but still needs a real production failover test. No server process or server-health result was captured after the app was stopped on 2026-08-26.

The catalogue editing/output workflow is a separate repository at `C:\Users\kaila\Desktop\JewelleryCatalogTool`. Do not alter its approved/rejected/Ornate NX routing while testing CaptureCam unless the user explicitly requests it.

## Current truth table

| Capability | Source state | Physical proof | Production status |
|---|---|---|---|
| Sony SSH/PTP connection | Implemented | Repeatedly connected | Needs long recovery soak |
| 25 FPS preview | Implemented | Approximately 24.6–25.4 FPS observed | Candidate |
| No growing five-second lag | Latest-wins implemented | Short runs improved | Needs 10-minute proof |
| Five-frame tag consensus | Compiled/installed | No positive post-install tag test | Unverified |
| Authoritative category lookup | Implemented | Worked in earlier E2E | Re-test with consensus |
| Pair detector stability | Implemented | Initial left-lobe trace seen | Needs full pair E2E |
| Sony touch AF | Implemented | Commands/RTT observed | Candidate |
| Zoom-back focus ladder | Compiled/installed | Not physically exercised after install | Unverified |
| Manual tap focus | Implemented | Previously operated | Re-test |
| Gimbal centring | Implemented | Previously operated | Re-test after app restart |
| One shutter per requested view | Source intends one | Previous E2E produced five originals | Must prove |
| Original JPEG transfer | Implemented | 17–18 MB originals received | Verified basic path |
| RAW delivery | Camera property requested | No `.ARW` delivered/verified | Not implemented/proven |
| One-angle Complete option | Implemented | UI path exists | Re-test |
| Three-angle composition | Implemented | Earlier composite praised by user | Re-test with latest code |
| Background upload | Implemented | Queue architecture exists | Timing/failover proof needed |
| DSLR/smartphone hard switch | Implemented intent | Needs regression test | Candidate |

## Exact next test — do this before code changes

### A. Reproduce the candidate

1. Switch/pull `codex/sony-production-2026-08-25`.
2. Confirm the worktree is clean.
3. Build unit tests and debug APK.
4. Connect ADB and install the APK.
5. Clear logcat before launching.
6. Confirm camera and gimbal are powered and the tablet is on the intended network.
7. Launch CaptureCam.
8. Confirm the initial full-wide reset completes before presenting a label.

### B. Tag test

Present one real, clearly visible label and keep it steady.

Required evidence:

- Time the first label becomes readable on screen.
- First successful decode starts the burst.
- Exactly five distinct burst frames/votes are recorded.
- At least three values match.
- Category is resolved by the server.
- No forced two-second label preview remains.
- Record first decode, burst accepted, category request, category response, and jewellery-screen timestamps.
- Preview remains at least 25 FPS with no growing frame age.
- If the label changes or blurs, the burst must reject and return to scanning rather than accept mixed values.

### C. Pair and focus test

Prefer TOPS, BALI, or another split-pair category for the first physical ornament test.

Required evidence:

- Pair processing remains full-frame. It must not oscillate between ROI locked/lost around the empty centre.
- Composition midpoint may guide the gimbal, but AF target must land on a real gold lobe.
- Initial automatic AF commands must not exceed seven for the physical pose.
- If maximum zoom is blurred, logs must show a monotonic ladder such as roughly `3.125 -> 2.5 -> 2.0 -> 1.6 -> 1.28 -> 1.0`.
- The code must never climb above the last failed zoom ceiling during that pose.
- Stop backing off at the first Sony-lock-plus-local-sharp frame.
- If fully wide is still blurred, show the stand-distance message and wait for the operator.
- The overlay sharpness result must correspond to micro-detail on the actual ornament, not the empty gap.

### D. Capture test

For the main view:

- Confirm focus before shutter.
- Record command, shutter acknowledgement, object event, download start, download end, and UI-advance timestamps.
- Exactly one original must arrive.
- Inspect the full original for sharpness, exposure, clipping, framing, and correct tag/category association.

Then test both branches:

1. One-angle item: choose `Complete`. The app must stage locally, return to next-tag mode, centre the gimbal, and go fully wide without waiting for server upload.
2. Three-angle item: choose `Proceed to angle 2`, capture angles 2 and 3, and prove exactly one original per angle. Confirm previous transfers do not freeze preview or cause duplicate shutters.

After the set:

- Confirm local staged files and metadata.
- Confirm background upload job success.
- Confirm the server receives the correct label/category/name.
- Confirm the composite preserves original source dimensions/detail as designed.
- Confirm the next item is ready promptly.

### E. Stability test

Run at least ten minutes, including repeated tags, focus, original transfer, idle periods, and at least one recovery event.

Acceptance:

- Preview stays at least 25 FPS in normal operation.
- No growing preview/frame-age backlog.
- No five-second visual delay.
- Recovery from a dead/wedged Sony session does not spend tens of seconds in futile HTTP-only retries.
- No concurrent reconnect paths fight over the Sony session.
- Gimbal reconnects after BLE interruption.
- Laptop server remains reachable through the intended LAN/Wi-Fi transition.

## Production-ready gate

Do not declare production-ready until all are true in one instrumented build:

1. Five-frame real-tag consensus passes and rejects a deliberately moved/changed tag.
2. Server category resolution succeeds.
3. Pair ROI does not oscillate.
4. The zoom-back focus ladder is physically observed and produces a genuinely sharp original.
5. Exactly one shutter and one original occur for each requested view.
6. One-angle Complete works.
7. A complete three-angle set is staged, composed, named, uploaded, and associated with the correct item.
8. UI advances without waiting on remote upload.
9. Gimbal centres and lens returns fully wide for the next item.
10. Ten-minute preview test has no latency growth and recovers cleanly from a Sony disconnect.
11. Smartphone mode still works after Sony changes.

## Guardrails for further work

- No local LLM. Keep detection deterministic unless the user explicitly reverses this decision.
- Do not re-enable DINO servo or the dormant tracking pipeline.
- Do not copy or modify Sony's Creators' App APK. This implementation uses the discovered Sony protocol behaviour in CaptureCam.
- Do not add another concurrent Sony control/reconnect owner. One arbitration path must own session recovery.
- Do not increase buffers as a substitute for dropping stale preview frames. Large queues recreate the five-second lag.
- Do not issue focus, exposure, zoom, and reconnect commands concurrently without the existing control arbitration.
- Do not restore burst capture to production merely to choose a best photo. The present requirement is one shutter per requested view.
- Do not claim RAW, 30 FPS, or production stability without physical evidence.
- Do not tune category thresholds from one item. Preserve logs and compare multiple stock categories.
- Do not merge into stable branches before the production gate passes.

## File reading order for Claude

Read in this order:

1. `CLAUDE_HANDOVER_2026-08-26_SONY_PRODUCTION.md` — this document.
2. `app/src/main/java/com/aradhana/capturecam/MainActivity.kt` — state machine, scanning, composition, AF, capture flow.
3. `app/src/main/java/com/aradhana/capturecam/sony/SonyProductionCamera.kt` — camera lifecycle, live loop, still capture.
4. `app/src/main/java/com/aradhana/capturecam/sony/SonyPtpIpController.kt` — SSH/PTP/HTTP transport and pump.
5. Locate/read `MaterialDetector.kt` — deterministic gold detection.
6. Locate/read `CaptureCompositionProfile.kt`.
7. Locate/read `CaptureHardwareProfile.kt`.
8. Locate/read `StandDistanceGuide.kt`.
9. Locate/read `CameraAssistAnalyzer.kt`.
10. Locate/read `BoundsOverlayView.kt`.
11. Locate/read `CaptureUploadQueue.kt`.
12. Locate/read `UploadClient.kt`.
13. Locate/read `RSC2Controller.kt`.
14. `E2E_TEST_2026-08-25_LOCKET_22.md` — earlier measured baseline, not final acceptance.
15. `CLAUDE_HANDOVER_2026-08-23_SONY_LIVEVIEW.md` — historical investigation only.

Some package paths changed during development. Use `rg --files | rg '<filename>'` instead of assuming every file lives in the same package.

## Build, install, launch, and logs

PowerShell:

```powershell
Set-Location 'C:\Users\kaila\Desktop\CaptureCam-master-checkout\CaptureCam'
git switch codex/sony-production-2026-08-25
git pull --ff-only
git status --short --branch

$env:JAVA_HOME='C:\Tools\jdk-17.0.12+7'
.\gradlew.bat testDebugUnitTest assembleDebug

$adb='C:\platform-tools\adb.exe'
& $adb connect 192.168.0.22:5555
& $adb -s 192.168.0.22:5555 install -r 'app\build\outputs\apk\debug\app-debug.apk'
& $adb -s 192.168.0.22:5555 logcat -c
& $adb -s 192.168.0.22:5555 shell monkey -p com.aradhana.capturecam -c android.intent.category.LAUNCHER 1
& $adb -s 192.168.0.22:5555 logcat -v time CaptureCam:V SonyProduction:V SonyPtpIp:V '*:S'
```

APK output:

`app\build\outputs\apk\debug\app-debug.apk`

Stop safely:

```powershell
$adb='C:\platform-tools\adb.exe'
& $adb -s 192.168.0.22:5555 shell am force-stop com.aradhana.capturecam
```

## Minimum data to preserve from every E2E run

- Git commit and APK build timestamp.
- Tablet address, camera address, and connection times.
- Camera/gimbal startup state.
- First preview frame and full-wide completion times.
- Source FPS, decoded FPS, render FPS if available, dropped count, max gap, and frame age.
- First visible tag, first decode, each of five votes, consensus, category request/response.
- Category/profile selected.
- Gold bounds/points, pair clusters, ROI transitions, gimbal target.
- Every zoom command and acknowledged zoom state.
- Every AF command, Sony focus state, local sharpness score, and zoom-back decision.
- Every exposure change and clipping percentages.
- Per-view capture sequence ID, shutter request/acknowledgement, Sony object handle, download start/end, source filename, byte size, checksum if available.
- Local stage, UI release, WorkManager start, server response, and final upload state.
- Count of physical shutter actuations versus requested views.
- Full-resolution originals and final composite for visual inspection.

## Immediate status when this handover was written

- Source tree was clean at `295a1d9` before adding this document.
- Latest unit-test/debug build had completed successfully: 47 Gradle tasks.
- Latest APK had installed successfully.
- Tablet ADB was still reachable at `192.168.0.22:5555` during the last session.
- CaptureCam was intentionally stopped; no app PID was present.
- No positive tag or focus-ladder test was attempted after the final install.
- Therefore the next action is the instrumented physical E2E test above, not another blind refactor.
