# AMBIC Digital MDM — 2026-09-17 handover

## Scope and current objective

Today’s main work was stabilising Android QR Device Owner enrollment, retaining the existing enrolled devices, and improving the MDM console/agent behaviour around FRP, kiosk, device names, and connectivity.

The immediate next validation is **Tablet 3**: it was factory-reset after Android showed **“Couldn’t set up your device / For help, contact your IT admin”** after QR provisioning. A new agent release is now live. Reset Tablet 3 and scan the fresh QR in the MDM console. Do not reuse an older QR.

User context:

- Four tablets are being enrolled.
- Existing enrolled devices are named **TAB1** and **TAB3**.
- Do not reset, re-enroll, or broadly roll out a new agent to existing devices without asking first.
- User explicitly requested asking before changes that could affect enrollment. They explicitly authorised the current v0.2.22 enrollment fix and its server/console deployment.
- Admin passcode was changed by the user in the console to `Ambic@2026`.

## Repositories and deployment path

Working repository:

`C:\AradhanaSystems\platform\ambic-digital-mdm`

Current local branch:

`frp-fix-on-real-base`

Git remotes:

```text
ambic  https://github.com/KAILASHRAJPUROHIT/AMBICAISWORK.git
origin https://github.com/MDMesh-app/MDMesh.git
```

Important: local branch is divergent from `ambic/main`. Do **not** force-push. Release tags trigger the production image build successfully even when local HEAD is not on remote `main`.

Release mechanism:

1. Commit local code.
2. Tag `vX.Y.Z` and push tag to remote `ambic`.
3. GitHub Actions builds signed Android APK plus server/web/supervisor images.
4. Open `https://mdm.ambicdigital.in/settings` and deploy **server + console** through the update UI, or automatic updates may deploy it if enabled.
5. Do not click **Promote to fleet** in the Agent rollout section unless the user explicitly approves rollout to existing devices.

Latest successful release:

- Version: `v0.2.22`
- Commit: `2182055 Defer Device Owner policies until setup completes`
- GitHub Actions run: <https://github.com/KAILASHRAJPUROHIT/AMBICAISWORK/actions/runs/35227477507>
- Build duration: 6m46s, completed successfully.
- Production server confirmed as `0.2.22` in Settings.
- Latest agent endpoint confirmed live after deployment:

```text
https://mdm.ambicdigital.in/files/agent.apk
HTTP 200
Content-Type: application/vnd.android.package-archive
Last-Modified: Thu, 17 Sep 2026 13:38:48 GMT
```

The current console has a fresh, single-use QR open on `/enroll`. At handover it said it expires **Sep 18, 2026, 07:09 PM** and embeds Wi-Fi SSID `admin`. Generate another via **New code** if it expires.

## Current production state verified after v0.2.22 deployment

- Server and console v0.2.22 are live.
- Console Devices page showed **2 total / 2 online**.
- Existing devices were intact:
  - `TAB3` — ID `68470ab9-401d-41b1-b0a2-8f7bdc59aaa8`
  - `TAB1` — ID `da665a3f-cdae-4fd3-bce3-09e6801e0926`, currently marked **FRP pending**
- Existing agent rollout UI still says `v0.2.20 · canary 2 / 2 updated` and exposes **Promote to fleet**. We deliberately did not press it.
- Automatic updates were shown as enabled in console Settings. It likely applied server/console v0.2.22 quickly after the release became verified.

## QR enrollment failure: diagnosis and fix

### Symptom

The user repeatedly saw this on a factory-reset Android 16 tablet during QR Device Owner enrollment:

1. Scan QR.
2. Android downloads the AMBIC Digital MDM APK.
3. Android shows “Getting ready for work setup” / “Just a sec”.
4. Android fails with **“Couldn’t set up your device”** and a Reset button.

It occurred before the agent’s first server check-in. It did not damage or alter existing enrolled tablets.

### What was already fixed in v0.2.19

v0.2.19 added the Android 12+ compliant Device Owner provisioning path:

- Handles `ACTION_GET_PROVISIONING_MODE`.
- Uses `ACTION_ADMIN_POLICY_COMPLIANCE` activity.
- Reads `EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE`.
- Saves server/token details.
- Calls `setResult(RESULT_OK)` and `finish()` before asynchronous check-in scheduling.

This was required but did not fully solve the intermittent Android 16 failure.

### Root cause addressed in v0.2.22

The remaining problem was likely synchronous policy mutation from `DeviceAdminReceiver` callbacks, still on Android Setup Wizard’s critical provisioning path. The old callbacks performed work such as organisation ID, package protection, location, permissions, password-token and baseline policy configuration. On Android 16/OEM setup wizard this can make setup abort after the DPC is downloaded.

v0.2.22 moves that policy work out of provisioning callbacks and into the normal app launch after setup completes.

Files changed by v0.2.22:

### `agent-android/app/src/main/kotlin/com/mdmesh/agent/admin/DeviceOwnerInitializer.kt`

New shared initializer. It only runs when this app is Device Owner and applies baseline Device Owner policy:

- Organization ID `mdmesh-fleet` on Android S+.
- User-control-disabled packages.
- Location enabled.
- Runtime permission auto-grant policy.
- Reset-password token setup.
- Self-grants for phone-state and foreground/background location permissions.

### `agent-android/app/src/main/kotlin/com/mdmesh/agent/admin/AdminReceiver.kt`

- `onEnabled()` now does no policy work.
- On Android S+, `onProfileProvisioningComplete()` returns immediately.
- On legacy Android versions, it saves enrollment info and schedules worker asynchronously using `goAsync()`.
- Existing kiosk overlay-related imports/logic retained.

### `agent-android/app/src/main/kotlin/com/mdmesh/agent/ui/MainActivity.kt`

After the UI is set, it launches `DeviceOwnerInitializer.apply(applicationContext)` using `Dispatchers.Default`. This places Device Owner policy application after Setup Wizard has handed control to the DPC.

Local verification performed before release:

```powershell
agent-android\.\gradlew.bat :app:compileReleaseKotlin :core:test
git diff --check
```

Both passed.

### How to validate v0.2.22

1. On the failed Tablet 3, tap Reset and complete the factory reset.
2. At first “Hi there” screen, do not sign into Google.
3. Tap screen six times to open QR provisioning.
4. Use the fresh console QR generated after v0.2.22 deployment.
5. Let Android download/setup finish.
6. Confirm tablet appears in Devices after initial check-in.
7. Name it in console if necessary and verify FRP/kiosk behaviour after normal check-in.

If it still fails, do not immediately add more provisioning policies. Capture:

- Exact Android screen wording and point of failure.
- Whether Wi-Fi remains connected.
- Whether agent download completed.
- Timestamp and tablet model/Android patch version.
- Server logs, if AWS access becomes available.

The best next engineering step would be Android device logs around Setup Wizard / DevicePolicyManager provisioning, not guesswork.

## Earlier release history today

### v0.2.19

QR provisioning reliability fix. Successful workflow:

<https://github.com/KAILASHRAJPUROHIT/AMBICAISWORK/actions/runs/35221341462>

### v0.2.20

FRP delivery/capability fixes. Successful workflow:

<https://github.com/KAILASHRAJPUROHIT/AMBICAISWORK/actions/runs/35221659788>

### v0.2.21

Commit `518c0e5`, deployed server/console successfully:

<https://github.com/KAILASHRAJPUROHIT/AMBICAISWORK/actions/runs/35225655940>

Important functional changes:

- Console device cards show friendly device names first and UUID second.
- Dashboard uses friendly device names.
- Kiosk UI indicates current kiosk state and preserves confirmed app selection.
- FRP action disabled after done/pending state.
- Exiting kiosk goes to the agent MainActivity rather than OEM Home.
- Default connectivity was changed from adaptive/battery saver to always-on for new agent installs:

```kotlin
fun get(): String = prefs.getString(KEY, DeviceAction.POWER_ALWAYS_ON) ?: DeviceAction.POWER_ALWAYS_ON
```

v0.2.21 agent rollout was not promoted to all existing devices. That remains intentional.

## FRP state

Existing TAB1 currently displays **FRP pending**. Do not factory-reset it until the command has completed. Earlier work fixed a capability mismatch around `factoryResetProtection` vs `policy.factoryResetProtection` and added automatic queueing of FRP apply work for Device Owner enrollment.

The user requested:

- “Apply verified FRP accounts” disabled/greyed after FRP enabled.
- Existing pending indicator in device list.

v0.2.21/v0.2.20 contain the relevant UI/server work. New agent installs via v0.2.22 carry it. Existing agents need an approved rollout or otherwise need to check in/update before this can complete reliably.

## Connectivity and pending commands

Agent connection design:

- Persistent WebSocket: `wss://.../agent/ws/...`
- OkHttp ping: 50 seconds.
- Reconnect cap: 60 seconds.
- Battery-saver mode falls back to periodic work/alarm, about 10 minutes.

The user saw pending `device.ring` and `app.install` commands while a device used **Battery-saver** connectivity. On an enrolled device, the short-term user action is:

1. Wake device.
2. In console click **Connectivity: Always-on**.
3. Click **Sync now**.

Future fresh agents now default to always-on. Do not present persistent connectivity as a guarantee when Wi-Fi, Android background limits, or OEM battery policy breaks it; it should improve prompt delivery substantially.

## Other work performed before this handover

Claude had started FRP auto-enable/pending badge changes before running out of usage. The code state then included:

- New `FrpApplyService.java` shared by manual FRP apply and enrollment auto-queue.
- `FrpRecoveryAccountResource.apply()` refactored to use shared service.
- Device Owner enrollment auto-queues FRP after `updateEnrollmentMode(deviceId, "deviceOwner")` in `AgentResource.enroll()`.
- Mapper/DAO additions for querying pending FRP device numbers.
- Endpoint added in `FrpRecoveryAccountResource`.
- Frontend changes in `web/src/lib/frp.ts` and `web/src/pages/DevicesPage.tsx` for FRP pending display.

Claude had not completed/verified all frontend work at that point. Later release work should be checked against working tree/history before making assumptions.

User’s outstanding feature requests:

1. When entering kiosk, if device already in kiosk, display that state.
2. Selected kiosk apps should be reflected when reopening kiosk workflow.
3. Device friendly name visible in admin dashboard.
4. Re-enable the extensive settings visible when exiting MDM/kiosk mode; user says they were missing.
5. Grey out verified FRP apply once enabled.
6. Persistent server connection and smooth command delivery.
7. Background scan of all apps, including system apps, after Device Owner enrollment, so kiosk selection is ready.

Items 1, 2, 3, and part of 5 were addressed in v0.2.21 UI work. Validate in production before further edits. Item 6 was partially addressed for fresh agents by default always-on connectivity. Item 7 was explicitly deferred; it has not been implemented or verified.

## Google Workload Identity Federation (unrelated, incomplete)

This was attempted earlier to allow the AWS EC2 instance to access Google APIs without a Google service-account key.

Files/paths on AWS EC2:

```text
/etc/ambic-mdm/google-wif.json
/opt/ambic-mdm/wif-check
```

IMDSv2 read succeeded and returned AWS role:

```text
ambic-mdm-prod-google-wif
```

WIF config required `imdsv2_session_token_url`; this was added.

Final WIF test still failed with:

```text
Permission 'iam.serviceAccounts.getAccessToken' denied
google.auth.exceptions.RefreshError: Unable to acquire impersonated credentials
```

The external pool principal needs the Google service-account **Service Account Token Creator** permission (`iam.serviceAccounts.getAccessToken`) on:

```text
ambic-mdm-server@ambic-mdm-prod.iam.gserviceaccount.com
```

Attempts to grant using the console initially used an invalid principal format with `arn:aws:iam...`; Google rejected it. This is unrelated to the Android QR failure. Do not work on it unless required for a Google API feature.

## AWS access and evidence limits

Local AWS CLI on the developer machine does not have usable credentials:

```text
aws sts get-caller-identity
NoCredentials
```

No direct AWS server logs were inspected by Codex. Deployment/update was through the MDM web console and GitHub release pipeline. Do not claim AWS logs were checked.

## Safe continuation checklist

1. Let user attempt fresh Tablet 3 enrollment with current v0.2.22 QR.
2. If it succeeds, confirm initial check-in/device appears, then test a harmless command such as Sync and validate name/kiosk/FRP state.
3. Do not alter existing device enrollment, factory-reset, or promote agent rollout without asking.
4. If it fails, collect exact screen/timestamp/device info and obtain Android/AWS logs before changing provisioning callbacks again.
5. After enrollment is stable, implement the requested post-enrollment all-app/system-app scan. Make it idempotent, asynchronous, and non-blocking so it cannot affect Setup Wizard.
6. Verify kiosk state and selected app persistence in real console/device flow.
7. Revisit FRP pending only after agent/server command delivery is proven; never reset while it says pending.

