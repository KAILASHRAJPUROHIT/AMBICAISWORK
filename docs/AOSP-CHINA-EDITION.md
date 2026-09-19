# AMBIC MDM China / AOSP edition

## Purpose

`aosp` is a separate Device Owner APK for China-ROM and GMS-free Android devices. It shares the
same policy, kiosk, command, inventory, telemetry and HTTPS/WebSocket protocol as the GMS agent,
but deliberately excludes Firebase and FCM.

## Build outputs

```powershell
cd C:\AradhanaSystems\platform\ambic-digital-mdm\agent-android
.\gradlew :app:assembleAospRelease -PmdmBaseUrl=https://mdm.ambicdigital.in/
```

Package: `com.mdmesh.agent.cn`.

The existing production APK remains `com.mdmesh.agent` (`gms` flavor). The packages are distinct;
the China APK cannot replace a deployed GMS Device Owner by accident.

## Enrollment

China ROMs without GMS do not support Android Enterprise's six-tap QR provisioning. Use a factory
reset device with USB debugging enabled, install this APK manually, then set it as Device Owner:

```powershell
.\tools\provision-aosp-device.ps1 -Serial SERIAL -ApkPath .\agent-android\app\build\outputs\apk\aosp\release\app-aosp-release.apk
```

The provisioner installs the China APK, binds it as Device Owner only when no other owner exists,
then prompts for a freshly minted enrollment token. It never wipes, clears an owner, or changes a
device managed by another DPC.

The device must have no accounts or existing Device Owner. `dpm` can be blocked by OEM policy; do
not bypass locked bootloaders or security controls. Enroll using a server-minted single-use token
through the dedicated provisioner once added. Never copy a production device secret between devices.

## Connectivity

Without FCM, reachability is provided by the agent WebSocket while awake plus `WakeKeepAlive` during
Doze. China devices require OEM-specific battery exemption testing. The server must treat the
heartbeat as a fallback, not an instant wake mechanism.

## Intentional GMS gaps

- Managed Google Play and Play app delivery
- Android Enterprise QR / zero-touch provisioning
- FCM wake delivery
- Google Play Integrity and Google location services

All other features remain subject to Android Device Owner APIs and the OEM's policy implementation.
