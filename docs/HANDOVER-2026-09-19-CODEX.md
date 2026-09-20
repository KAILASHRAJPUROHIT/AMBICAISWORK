# AMBIC Digital MDM — 19 Sep 2026 handover

## Production state

- AWS instance: `i-09bdb219f061e62f1` (`ambic-mdm`, ap-south-1).
- Production server and web are now `v0.2.36`.
- Deployment completed through the built-in supervisor. Evidence: supervisor logged `PHASE done` and `OK 0.2.36`.
- The update was triggered by restarting only `mdmesh-supervisor-1`. It discovered the already-published signed `v0.2.36` release, mirrored `agent-236.apk`, then recreated `mdmesh-server-1` and `mdmesh-caddy-1`.
- No fleet agent rollout, kiosk command, reset, or device policy command was sent during this deployment.
- Updater status before restart was healthy but stale: it polls every 6 hours and had last seen `v0.2.35`.

## Redmi 14R / China-ROM agent

### Current result

- Redmi 14R (`2411DRN47C`, Android 16 / HyperOS China ROM) is enrolled as a Device Owner under `com.mdmesh.agent`.
- Installed no-GMS agent version: `0.2.37-cn-replace`, version code `237`.
- Device Owner survived the update.
- `CheckInService` restarted as a foreground service after package replacement.
- Production server received post-update check-ins at 12:42:57 IST-equivalent server log time, reporting `0.2.37-cn-replace`, `isDeviceOwner=true`, and network connectivity.
- The AOSP variant has no Firebase/FCM dependency. It uses normal check-ins, `TransportManager`, and `WakeKeepAlive`.

### Critical signing constraint

- The 14R was originally provisioned with this workstation's Android **debug** certificate.
- Installed certificate SHA-256: `d77678ef231293af3b88b6e6a24ca4e4d5d5b45491142b5b36a6675bccfedd15`.
- Production release certificate SHA-256: `6e18bbd5ad43b07b22a35c6bd1320cc01c743c98f2f1497161b51e2d17254130`.
- Android correctly refused the release-signed replacement with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Nothing changed during that failed attempt.
- The local AOSP debug APK matched the installed debug certificate exactly, so `adb install -r` succeeded and preserved the Device Owner.
- Future in-place updates for this exact 14R must be built with this workstation's debug keystore, or the device must be factory-reset and reprovisioned using the release-signed DPC. Do not attempt a release APK update on it.

### Local artifact/source facts

- Installed local APK: `agent-android/app/build/outputs/apk/aosp/debug/app-aosp-debug.apk`.
- Build command used:

```powershell
cd C:\AradhanaSystems\platform\ambic-digital-mdm\agent-android
.\gradlew.bat :app:assembleAospDebug "-PchinaInPlaceReplacement=true" "-PversionName=0.2.37" "-PversionCode=237"
```

- Install command used:

```powershell
adb -s 49a646a1 install -r C:\AradhanaSystems\platform\ambic-digital-mdm\agent-android\app\build\outputs\apk\aosp\debug\app-aosp-debug.apk
```

- Read-only verification commands:

```powershell
adb -s 49a646a1 shell dpm list-owners
adb -s 49a646a1 shell dumpsys package com.mdmesh.agent
adb -s 49a646a1 shell dumpsys activity services com.mdmesh.agent
```

## Code committed today

Current working branch: `restore-admin-menu`.

- `6e9a2b0 Harden sleeping device connectivity`
  - Agent wake keepalive changed from 10 to 5 minutes.
  - Console online window changed from 10 to 15 minutes.
  - Added websocket/open-close failure diagnostics.
  - Released/deployed as `v0.2.36`.

- `646f6d7 Add GMS-free China AOSP agent variant`
  - Added `gms` and `aosp` flavors.
  - Normal AOSP application id is `com.mdmesh.agent.cn` to prevent accidental replacement of the GMS Device Owner.
  - AOSP excludes Firebase and includes USB bootstrap support.

- `2304440 Separate China agent update channel`
  - Added separate supervisor AOSP APK handling and `/update/agent-cn.apk`.
  - Release workflow builds/uploads normal and AOSP APKs.
  - China rollout promotion is intentionally blocked until server-side agent-distribution telemetry exists.

- `ea8b268 Add private China in-place agent build`
  - Adds Gradle property `chinaInPlaceReplacement=true`.
  - This keeps the AOSP build at package `com.mdmesh.agent`, allowing a same-certificate Device Owner update without reset.
  - Adds manual, artifact-only GitHub workflow `.github/workflows/china-inplace-replacement.yml`.
  - Workflow does not create a release, push images, deploy AWS, or enter fleet rollout.

## Git / workflow caveat

- `restore-admin-menu` contains current MDM work.
- GitHub default branch `main` is far behind it.
- GitHub only permits `workflow_dispatch` workflows visible on the default branch. Therefore commit `3089255 Add private China replacement build workflow` was pushed to `main`; it contains **only** that inert manual workflow.
- The manual workflow was run successfully: `35441580790`.
- It built a release-signed APK artifact and verified the production release certificate. This artifact cannot update the debug-signed 14R, but remains valid for a future release-signed China-ROM Device Owner.

## Important unfinished work

1. China fleet channel is incomplete. Before any China APK rollout:
   - add `gms`/`aosp` distribution telemetry to device check-in/state;
   - filter China rollout candidates server-side;
   - expose separate GMS and China rollout UI;
   - keep China rollout manual-canary-only until tested.

2. Fix `supervisor/server.js` native-publish edge case before enabling AOSP release mirroring on native deployments:
   - `ensureApk(lastAospApk, '-cn')` still calls `publishApk(dest)` without a distinct target;
   - a native deployment with `PUBLISH_APK_TO` could overwrite the normal agent static path with the China APK.
   - Docker/Caddy production is not affected because it does not use `PUBLISH_APK_TO`.

3. FCM/WIF remains a separate Google IAM concern. Previous production logs showed WIF token acquisition errors caused by missing `iam.serviceAccounts.getAccessToken`. Do not change Google IAM without explicit user approval. The China AOSP 14R does not require FCM.

4. No automated device-side action was performed after the 14R upgrade. Validate sleep/wake behavior manually before treating AOSP connectivity as production-ready.

## Safety rules

- Existing enrolled tablets are production. Ask before sending commands, rolling agent APKs, changing kiosk state, policy changes, rebooting, locking, resetting, or enrolling.
- Do not factory-reset the 14R merely to change certificate strategy without explicit user approval.
- Never expose GitHub tokens, AWS credentials, WIF files, Google credentials, or Android device identifiers in chat/logs.
