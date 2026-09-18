# Handover — 2026-09-18 (Claude → Codex)

Session started with `am back lets implement this` (continuing FCM setup from an overnight
handover), then the user asked for a stream of new features in quick succession. Everything below
is in order. **I ran low on context mid-feature** — see "IN PROGRESS" at the bottom for exactly
where to pick up.

## Shipped and deployed live (production server + all 4 tablets)

- **v0.2.26**: FCM wake channel fully live (Firebase project attached to `ambic-mdm-prod`, IAM
  granted, `AMBIC_FCM_PROJECT_ID` set on the server, `google-services.json` wired via
  `MDM_GOOGLE_SERVICES_B64` CI secret — see `RELEASING.md`). Also the app-inventory pre-scan
  (`AppInventoryCache`) from the prior session. Rolled out to all 4 devices (TAB1/2/3/PRO) —
  had to manually nudge TAB2 (see "known rollout gap" below).
- **v0.2.27**: Fixed custom-APK upload 413 (Tomcat `maxPostSize` defaulted to 2MB — patched in
  `docker/entrypoint.sh` via a `sed 0,/pat/` on `server.xml`, capped at 500MB).
- **v0.2.28**: Library-app update pushing with per-device pending status (the closest
  achievable thing to "trigger Play Store updates" without re-enrolling into AMAPI — user
  explicitly declined AMAPI re-enrollment since it needs a factory reset per device). Generalizes
  the existing agent-rollout machinery (`AgentRollout.trackingMode`: `"version"` for the agent's
  own self-update, unchanged; new `"command"` mode for any Library app, tracked via a new
  `agentRolloutCommand` join table since there's no installed-version record for arbitrary
  packages). New endpoints under `/private/agent/v1/rollout/apps`. Web: `DeployModal`'s
  "Push to device(s)" now routes single-APK Library versions through this tracked path;
  `AppRolloutStatus` panel on the Apps page shows live progress; `DevicesPage` gets an
  "Update pending" badge.
  - **Known gap, not fixed**: Lite (Device Admin, non-owner) devices can't actually receive a
    silent install today — `InstallManager.kt` unconditionally requests
    `USER_ACTION_NOT_REQUIRED` and treats the resulting `STATUS_PENDING_USER_ACTION` as a hard
    failure instead of launching the system install-confirmation UI. Flagged to the user, not
    fixed — needs its own careful pass on a security-sensitive path.

## Committed, NOT yet released (on `restore-admin-menu` branch, needs a version bump + tag to ship)

- **Kiosk header rebranding** (`d1f279e`... actually check `git log`, commit message
  "Kiosk header shows device name + org"): kiosk header now shows the console's device name
  (`device.description`) + "Aradhana Jewellers" + "powered by AMBIC DIGITAL" instead of a
  generic "AMBIC MDM Kiosk" string. `KioskApplyPayload` gained `deviceLabel`/`orgName`.
- **Battery/Wi-Fi kiosk status bar**: new `KioskStatusSource.kt` (`:core`), rendered top-start in
  `KioskLauncherActivity`'s `launcherGrid`/`splashView`, polled every 15s. Compiled and
  launched clean on the emulator (idle/splash paths only — could not force the emulator into an
  active kiosk-grid state to screenshot it live; recommend a quick visual check on TAB1 before
  wide release).
- **Wallpaper + kiosk accent colour push** (commit `d66ab1f`): new `device.wallpaper` command
  (plain `WallpaperManager`, NOT a Device-Owner API — just the normal `SET_WALLPAPER` permission,
  works on Lite too) and `device.kioskTheme` command (merges into the persisted kiosk theme live,
  no full re-entry needed). Note: true system-wide Material You accent colour has no public API
  independent of wallpaper — this instead colours the kiosk's own chrome (status bar, exit-menu
  icon) via `KioskThemeDto.accentColor`. New `WallpaperPanel` on the Settings page. Zero server
  changes needed (opaque commands + reused the existing raw-upload/commit flow already used for
  Custom APK hosting).

All three of the above compiled clean (`:app:compileDebugKotlin`, `:core:test`,
`:policy:testDebugUnitTest` all green) and were smoke-tested on the `ambic-mdm-frp-test` emulator
(installs, launches, no crash in logcat) before committing. **Not yet tagged/released** — bundle
them into the next release alongside whatever remote-view work lands.

## IN PROGRESS — remote view / camera / mic (the big one, incomplete)

User wants: view any device's screen, front/back camera, and mic from the console, "without
disrupting user work." Scoped this out explicitly with the user beforehand:

- **Real Android platform constraint** (confirmed via code research, not assumption): a
  non-privileged Device-Owner app has **no silent path to true live video/audio streaming**.
  - Screen: `MediaProjection` needs a fresh consent dialog *every session* — no DPM bypass exists.
  - Screen (alternative): `AccessibilityService.takeScreenshot()` (API 30+) has **no per-call
    dialog and no persistent notification** — genuinely silent — but Device Owner **cannot
    silently enable an accessibility service**: `setPermittedAccessibilityServices` only
    allowlists it, the actual toggle needs `WRITE_SECURE_SETTINGS`, which DO does not grant. So
    this needs a **one-time manual enable** during device setup (Settings → Accessibility),
    exactly like this app's existing `PermissionsChecklistActivity` rows (Notification access,
    Usage access, etc. — none of those are DO-silent either, same category of limitation).
  - Camera/mic: `CAMERA`/`RECORD_AUDIO` **are** DO-silent-grantable via
    `setPermissionGrantState` (normal runtime permissions) — but Android's camera/mic-in-use
    indicator dot is unavoidable while actually capturing, by design, for any app.
  - **Decision made with user**: periodic snapshot capture (screenshot every N seconds, a still
    photo per camera, a short audio clip), NOT continuous live streaming — tractable to build
    correctly in one session, matches the "silent to the extent Android allows" answer the user
    gave earlier when asked. A time-boxed **session** (default 5 min, admin-started/stopped),
    not always-on background surveillance.

### What's actually built and compiling (server side — DONE, compiled + unit tests pass)

- `common/.../util/AgentAuth.java` — extracted the device-bearer-token check out of
  `AgentResource.authenticate()` into a shared static helper (was private/duplicated-risk before).
  `AgentResource.java` now delegates to it. **Compiled + tested clean.**
- `common/.../domain/RemoteSnapshot.java`, `mapper/RemoteSnapshotMapper.java`,
  `persistence/RemoteSnapshotDAO.java` — the "latest capture per device+kind" store. Bytes stored
  inline as `BYTEA` (not filesystem) since each kind keeps only ONE row (upserted), never a
  history — simplest correct choice, no orphaned-file cleanup ever needed.
- Liquibase changeset `26.09.18-remote-snapshot` (appended to `db.changelog.xml`) — creates
  `remoteSnapshot` table, `UNIQUE (deviceNumber, kind)`.
- `server/.../rest/resource/RemoteSessionResource.java` (`/private/agent/v1/devices/{deviceId}/
  remote/...`) — `POST /start` (queues `device.remoteSessionStart`, generates a sessionId,
  clamps duration 30s–30min / interval 1–60s), `POST /stop`, `GET /latest` (metadata only),
  `GET /snapshot/{kind}` (streams the actual bytes — **deliberately a private, session-cookie-
  authenticated endpoint, never a public URL**, since these captures are sensitive; same-origin
  `<img src="...">` tags carry the session cookie automatically so this just works from the web
  console with no extra plumbing).
- `server/.../rest/resource/RemoteSnapshotUploadResource.java`
  (`/public/agent/v1/remote/snapshot`) — device-authenticated (via `AgentAuth`, NOT an admin
  session — the device itself calls this) multipart upload. 8MB cap enforced by reading with a
  bounded loop (never buffers unbounded attacker data before rejecting).
- Both resources registered in `PrivateRestModule.java` / `PublicRestModule.java`.
- **Verified**: `mvn -pl common,server -am compile` and `mvn -pl common,server -am test` both
  green (via `docker run maven:3.9-eclipse-temurin-17`, since there's no local Maven on this
  machine — use `MSYS_NO_PATHCONV=1 docker run --rm -v "/c/AradhanaSystems/platform/
  ambic-digital-mdm:/src" -w /src maven:3.9-eclipse-temurin-17 sh -c "mvn -q -B -pl common,server
  -am -DskipTests compile"` pattern, Git Bash mangles `-w /src` and `/sdcard/...` adb paths
  otherwise — see git history this session for the exact incantations that worked, including for
  `adb shell`/`adb pull` with `MSYS_NO_PATHCONV=1` + doubled leading slashes).

### What's built but NOT YET WIRED (client side — this is where to resume)

Files that exist and are structurally complete but **not yet compiled/tested**:

- `agent-android/proto/.../RemoteSession.kt` — `RemoteSessionStartPayload` (sessionId,
  durationSec, intervalSec, kinds list).
- `agent-android/proto/.../DeviceAction.kt` — added `REMOTE_SESSION_START`,
  `REMOTE_SESSION_STOP`, `REMOTE_SESSION_CAPABILITY_KEY` constants. **Note**: deliberately NOT
  added to `ADVERTISED_KEYS` (that list is unconditional/always-advertised) — remote-session
  capability needs to be gated on `isDeviceOwner`, same as `appManagementKeys` already is in
  `AgentModule.kt`. **This gating is NOT wired yet** — see TODO below.
- `agent-android/core/.../permission/ScreenCaptureAccessibilityPermission.kt` — new
  `PermissionCheck` row (mirrors `NotificationAccessPermission.kt` exactly), checks
  `AccessibilityManager.getEnabledAccessibilityServiceList()` for
  `"com.mdmesh.agent/com.mdmesh.core.remote.ScreenCaptureAccessibilityService"`. **Already
  registered** in `PermissionRegistry.kt` (added before `BatteryOptimizationPermission`).
- `agent-android/core/.../remote/ScreenCaptureAccessibilityService.kt` — the actual
  `AccessibilityService`, `takeScreenshot()` wrapped in a suspend fun via a companion `instance`
  ref (set in `onServiceConnected`/cleared in `onDestroy`, same idiom as
  `KioskWatchdogService.suppressed`). No event handling — exists solely for the screenshot API.
- `agent-android/core/.../remote/RemoteSnapshotUploader.kt` — multipart POST to
  `/rest/public/agent/v1/remote/snapshot`, using `DeviceIdentity.current()`/`.secret()` for the
  bearer token (confirmed this is the right store — `ServerConfigStore` only has the base URL,
  `DeviceIdentity`/`DeviceIdStore` has the enrollment id+secret).
- `agent-android/core/.../remote/RemoteCameraCapture.kt` — Camera2 (not CameraX — no new
  dependency) single-frame JPEG capture, front or back via `CameraCharacteristics.LENS_FACING`.
  Picks the output size closest to 1280×960 (deliberately small — monitoring snapshot, not a
  keepsake photo, keep upload fast).
- `agent-android/core/.../remote/RemoteMicCapture.kt` — `MediaRecorder`, 6s AAC clip to
  `cacheDir`, read back as bytes, temp file always deleted in `finally`.

### TODO — exact next steps, in order

1. **`RemoteCaptureService.kt`** (put in `:app`, package `com.mdmesh.agent.service`, mirror
   `CheckInService.kt`'s foreground-service shape exactly — notification channel, `startForeground`
   with `FOREGROUND_SERVICE_TYPE_CAMERA or FOREGROUND_SERVICE_TYPE_MICROPHONE or
   FOREGROUND_SERVICE_TYPE_DATA_SYNC` on API 34+ — **Android 14 requires the camera/mic FGS types
   be declared explicitly when the service uses those APIs, on top of the existing
   `FOREGROUND_SERVICE_CAMERA`/`FOREGROUND_SERVICE_MICROPHONE` manifest permissions, which are
   NOT YET ADDED to `AndroidManifest.xml`**). `@AndroidEntryPoint`, injects
   `RemoteSnapshotUploader`, `RemoteCameraCapture`, `RemoteMicCapture`, and calls
   `ScreenCaptureAccessibilityService.captureJpeg()` (companion object, no injection needed).
   Reads session config (sessionId/durationSec/intervalSec/kinds) from the starting `Intent`'s
   extras. Runs a coroutine loop on `lifecycleScope` (or a dedicated `SupervisorJob` scope):
   every `intervalSec`, for each enabled kind, capture → upload (best-effort, don't let one
   failed upload stop the loop), until `durationSec` elapses (`System.currentTimeMillis()` vs. a
   stored `expiresAt`) or `stopSelf()` is called. Expose a `companion object` `requestStop()` or
   just have the stop handler call `context.stopService(Intent(context,
   RemoteCaptureService::class.java))` directly (simpler, no extra plumbing needed).
2. **`RemoteSessionStartHandler.kt` / `RemoteSessionStopHandler.kt`**
   (`agent-android/core/.../command/handlers/`) — mirror `KioskEnterHandler.kt`'s shape. Start
   handler decodes `RemoteSessionStartPayload`, starts `RemoteCaptureService` via
   `ContextCompat.startForegroundService` with the payload packed into the Intent extras
   (needs a `Context` injected — but `RemoteCaptureService` is an `:app` class and `:core`
   handlers can't reference `:app` classes directly! **Resolve this with an interface**: define
   e.g. `interface RemoteCaptureController { fun start(payload: RemoteSessionStartPayload);
   fun stop() }` in `:core`, implement it in `:app` (thin wrapper that builds the Intent and
   calls `startForegroundService`/`stopService`), provide it via Hilt `@Binds` in `AgentModule.kt`
   — same shape as `CapabilitySource`/`HardwareIdSource` interface-in-core/impl-in-app pattern
   already used elsewhere in this codebase, e.g. `provideCapabilitySource`/
   `provideHardwareIdSource` in `AgentModule.kt`). Stop handler just calls `controller.stop()`.
3. **`DeviceOwnerInitializer.kt`** — add `Manifest.permission.CAMERA` and
   `Manifest.permission.RECORD_AUDIO` to the `permissions` buildList (same silent
   `setPermissionGrantState` loop already there for READ_PHONE_STATE etc.) — **NOT YET DONE**.
4. **`AndroidManifest.xml`** — **NOT YET DONE**, needs:
   - `<uses-permission android:name="android.permission.CAMERA" />`
   - `<uses-permission android:name="android.permission.RECORD_AUDIO" />`
   - `<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CAMERA" />`
   - `<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />`
   - `<uses-permission android:name="android.permission.BIND_ACCESSIBILITY_SERVICE" />` (system
     permission, but the `<service>` declaration itself is what actually needs
     `android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"` — see
     `KioskWatchdogService`'s manifest entry in `:kiosk`'s own `AndroidManifest.xml` for the
     exact shape to copy, including the `<meta-data android:resource="@xml/...">` pointing at an
     accessibility-service-config XML — **a new
     `agent-android/app/src/main/res/xml/screen_capture_accessibility_config.xml` needs to be
     created too**, minimal: no event types needed since `onAccessibilityEvent` is a no-op, but
     Android still requires the config resource to exist for the service to bind.)
   - `<service android:name="com.mdmesh.core.remote.ScreenCaptureAccessibilityService"
     android:enabled="true" android:exported="false"
     android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE">` +
     `<intent-filter><action android:name="android.accessibilityservice.AccessibilityService" /></intent-filter>`
     + the meta-data pointing at the new xml config. **Note**: unlike `KioskWatchdogService`
     (toggled enabled/disabled at runtime because it's Lite-tier-conditional),
     `ScreenCaptureAccessibilityService` can just ship `android:enabled="true"` always — the real
     gate is whether the *user* has turned it on in system Accessibility settings (that's the
     one-time manual step), not the component's own enabled state.
   - `<service android:name=".service.RemoteCaptureService" android:exported="false"
     android:foregroundServiceType="camera|microphone|dataSync">` with the matching
     `PROPERTY_SPECIAL_USE_FGS_SUBTYPE`-style property if needed (check whether `camera`/
     `microphone` types need one — `specialUse` does, plain `camera`/`microphone` typically
     don't).
5. **`AgentModule.kt`** — wire:
   - `@Binds` (or `@Provides`) for the new `RemoteCaptureController` interface → its `:app` impl.
   - `@Provides @IntoSet fun provideRemoteSessionStartHandler(...)` and `...StopHandler(...)`.
   - Gate `device.remoteSession` capability advertising on `isDeviceOwner`, same as
     `appManagementKeys`: something like
     `deviceActionKeys = DeviceAction.ADVERTISED_KEYS + if (deviceOwner)
     listOf(DeviceAction.REMOTE_SESSION_CAPABILITY_KEY) else emptyList()` in
     `provideCapabilityCollector`.
6. **Compile check**: `cd agent-android && ./gradlew.bat --no-daemon :app:compileDebugKotlin
   :core:test :policy:testDebugUnitTest` — fix whatever breaks (there WILL be a couple of small
   issues, e.g. imports, the `RemoteCaptureController` interface wiring). Then
   `:app:assembleDebug`, install on the `ambic-mdm-frp-test` emulator (already Device Owner from
   earlier in this session), launch, check logcat for `FATAL`/Hilt errors (the emulator's fake
   camera/mic won't produce meaningful captures, but this at least proves the DI graph and
   service-start path don't crash — same verification depth used for every other feature this
   session).
   - **Already verified**: `:core:compileDebugKotlin` alone compiles clean as of this handover
     (only one pre-existing-style deprecation warning on `createCaptureSession`). Fixed one real
     bug along the way: `ScreenCaptureAccessibilityPermission.kt` used
     `AccessibilityManager.FEEDBACK_ALL_MASK` (doesn't exist) instead of
     `AccessibilityServiceInfo.FEEDBACK_ALL_MASK` (the correct constant) — already corrected in
     the committed version, so don't re-diagnose this if you see it referenced in earlier
     conversation/thinking. `:app` has NOT been compiled yet since `RemoteCaptureService.kt` and
     the handler files (step 1/2 above) don't exist yet — that's the actual next compile target.
7. **Web console UI** — NOT STARTED AT ALL. Needs (in `agent-android` — sorry, in `web/`):
   - `web/src/api/remoteView.ts`: `startRemoteSession(deviceId, {durationSec, intervalSec,
     kinds})`, `stopRemoteSession(deviceId)`, `getLatestSnapshots(deviceId)` — hits
     `/private/agent/v1/devices/{id}/remote/start|stop|latest`, mirrors `api/appRollout.ts`'s
     shape (already-established pattern this session).
   - A new tab on `DeviceDetailPage.tsx` (e.g. `'remote'`, alongside `'control'`/`'telemetry'`/
     etc.) rendering a new `RemoteViewPanel.tsx`: Start/Stop buttons (with duration/interval/kinds
     controls), then once active, poll `getLatestSnapshots` every few seconds and render
     `<img src="/rest/private/agent/v1/devices/{id}/remote/snapshot/{kind}?_={capturedAt}">` for
     screen/cameraFront/cameraBack (cache-bust via the `_=` query param since `capturedAt`
     changes), and an `<audio controls src="...">` for `mic`. Session-cookie auth makes these
     `<img>`/`<audio>` tags "just work" without extra token plumbing — confirmed this is safe
     specifically because the retrieval endpoint is `/private/...`, never `/public/...`.
8. **Docs**: once working, write `docs/REMOTE-VIEW.md` explaining the snapshot-not-live-video
   architecture decision and the one-time accessibility-enable step, for the user's own reference
   (they'll want to know why it's not literally live video, and need to know to enable
   Accessibility once per device during setup) — referenced from `RemoteSessionResource.java`'s
   class doc comment already, which currently points at a file that doesn't exist yet.

### NOT started at all (user asked, explicitly deferred to "once this is enabled tested and setup")

- "Anywhere administrator" mode: any enrolled device, given a separate admin password (distinct
  from the kiosk exit PIN), temporarily becomes a control center that can view/control other
  devices' screens/cameras/mics. This is a mobile client for the same remote-session APIs above —
  architecting those APIs device-agnostic (which they already are — plain REST, no web-specific
  assumptions) means this should be a relatively contained follow-on once the console-side
  version is proven. Not scoped in detail yet.

## Process notes for whoever picks this up

- User is decisive and fast-moving — expect messages to stack up mid-task; they explicitly said
  "implement all thats queued" rather than one at a time. Keep shipping in the same style: small
  real commits, compile-check every module touched, smoke-test on the emulator when feasible,
  don't over-promise on Android platform constraints (be upfront the way this doc has been).
- Production is 4 live tablets in a working jewellery store (Aradhana Jewellers) — TAB1, TAB2,
  TAB3, TAB PRO. Don't push a new agent APK release without the user's explicit go-ahead if
  they're not actively present/watching (this was an explicit self-imposed rule from the prior
  overnight session, and held up fine — the user then explicitly authorized daytime releases
  when present).
- `restore-admin-menu` is the actual working branch this whole session, pushed to
  `ambic` remote's `mdm-main` (NOT `origin` — origin points at a different, unrelated repo,
  `MDMesh-app/MDMesh` — always double check `git remote -v` before pushing, this tripped up an
  earlier session).
- No local Maven or full Android SDK gradle cache assumptions — use the Docker Maven pattern
  above for server/common, and the existing `./gradlew.bat` wrapper (already proven working all
  session) for the Android side.
