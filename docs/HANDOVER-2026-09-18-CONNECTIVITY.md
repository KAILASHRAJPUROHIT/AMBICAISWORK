# Production connectivity handover — 18 Sep 2026

## Scope and safety

- Production fleet: TAB1, TAB2, TAB3, TAB PRO. All are Android 16 Device Owner tablets in a jewellery store.
- User reports sleeping tablets go offline; `Sync now` does not reliably wake them; commands remain pending.
- Never factory-reset, exit kiosk, alter enrollment, or promote an agent rollout fleet-wide without explicit user approval.
- User previously approved: server/console deployment, a TAB3-only canary, and this connectivity diagnosis.
- AWS production host: `i-09bdb219f061e62f1` in `ap-south-1`, Linux user `ubuntu`, project `/home/ubuntu/ambic-digital-mdm`.
- MDM: `https://mdm.ambicdigital.in`.

## Root cause: confirmed

Sleeping-device FCM wake delivery fails server-side because Google Workload Identity Federation cannot mint an impersonated Google access token.

Production log captured after v0.2.31 deployment:

```text
FCM wake error ... Unable to acquire Google WIF access token for scope https://www.googleapis.com/auth/firebase.messaging
```

This means:

1. Device FCM registration is working. The server receives and stores fresh FCM tokens from tablets.
2. `AMBIC_FCM_PROJECT_ID` is set in the production server container.
3. The server cannot impersonate the Google service account, so no FCM message reaches a sleeping tablet.
4. WebSocket is not a sufficient fallback: a sleeping/Dozing device can lose it.

Earlier direct Python WIF test on this EC2 instance failed with the more specific Google error:

```text
Permission 'iam.serviceAccounts.getAccessToken' denied
```

The missing IAM permission is **Service Account Token Creator** on the target service account for the federated AWS principal.

## Required user action — Google Cloud IAM

The In-app browser has been opened at the target service-account permissions URL and is currently at Google sign-in. User must sign in; do not enter user credentials.

Target service account:

```text
ambic-mdm-server@ambic-mdm-prod.iam.gserviceaccount.com
```

Grant this role on that service account:

```text
roles/iam.serviceAccountTokenCreator
```

Grant it to exactly this member:

```text
principalSet://iam.googleapis.com/projects/246932236741/locations/global/workloadIdentityPools/ambic-mdm-production-aws/attribute.aws_role/ambic-mdm-prod-google-wif
```

Important: the final value is the AWS **role name** `ambic-mdm-prod-google-wif`, not its full ARN. The pool's documented/default AWS mapping maps `attribute.aws_role` to the assumed role name. The prior UI attempt used an ARN and failed with an invalid/unknown principal-type error.

`roles/iam.workloadIdentityUser` may already exist; do not remove it. Token Creator is additionally required for `iam.serviceAccounts.getAccessToken` when using the configured service-account impersonation URL.

After saving the IAM binding, wait 1–3 minutes for IAM propagation.

## Exact validation after IAM propagation

1. Open MDM → Devices → a sleeping/offline tablet (TAB1 is device `da665a3f-cdae-4fd3-bce3-09e6801e0926`).
2. Click `Sync now` once. This is non-disruptive: it queues no policy or device command; it only calls the server wake path.
3. In AWS EC2 Instance Connect, manually type (browser terminal corrupts pasted commands):

```bash
sudo docker compose logs --since 5m server | grep 'FCM wake'
```

Expected success:

```text
FCM wake accepted (HTTP 200) for token ending ...<redacted suffix>
```

Expected device result: fresh TAB1 check-in within about a minute; pending normal commands should progress.

If it still fails, collect the full redacted error via:

```bash
sudo docker compose logs --since 5m server | grep -Ei 'FCM wake|GoogleWif|permission|HTTP'
```

Never paste or publish full FCM registration tokens.

## Changes made today

### v0.2.30 — agent durable recovery

Commit:

```text
4f19936 Rearm device check-in after normal service starts
```

Agent changes:

- `CheckInService.onStartCommand()` now idempotently schedules WorkManager and `WakeKeepAlive` on every service start.
- `AdminPolicyComplianceActivity` arms both recovery paths immediately after normal QR provisioning.
- Fixes a real defect where the Doze-resistant AlarmManager recovery chain was armed only at boot/update, not during initial normal enrollment.

Local verification passed:

```text
agent-android\gradlew.bat --no-daemon :app:compileDebugKotlin :core:test :policy:testDebugUnitTest
```

v0.2.30 server/console was deployed. Its TAB3-only canary was not promoted. It remained `0/1 updated, 1 installing`.

### v0.2.31 — server diagnostics and null-safe WebSocket cleanup

Commit:

```text
fdd61a0 Harden wake diagnostics and cleanup
```

Files changed:

- `server/src/main/java/com/hmdm/notification/AgentWakeHub.java`
  - Ignores null `Session` in `unregister`; JSR-356 error callbacks can legally omit a session, while `ConcurrentHashMap.remove(key, null)` throws.
- `server/src/main/java/com/hmdm/rest/AgentWakeEndpoint.java`
  - Logs a real error cause/stack instead of the usually empty `Throwable.getMessage()`.
- `server/src/main/java/com/hmdm/service/FcmSenderService.java`
  - Logs redacted successful FCM acceptance (`HTTP 200`) as well as failures. Never logs full registration token.

Release:

```text
tag: v0.2.31
GitHub release workflow: 35326901396
result: success
```

Production update:

```text
v0.2.27 -> v0.2.31
supervisor apply result: done
verified update status: current 0.2.31, latest 0.2.31, APK available true
```

Why it reported 0.2.27 rather than expected 0.2.30 during this apply: restarting `supervisor` re-read its persisted/version environment. Do not assume the prior displayed version was the actual durable server image. Final verified production state is v0.2.31.

## Current production state

- Server/console: v0.2.31 deployed and healthy.
- Supervisor auto-update is enabled. Its normal poll interval is 6 hours; it was manually restarted to detect v0.2.31.
- No fleet agent rollout was started or promoted today.
- Existing TAB3-only v0.2.30 canary exists/stuck. Do not promote it. Cancel/recreate only after FCM is validated and with user approval for the next agent canary.
- TAB1 currently reports agent 0.2.26 and Always-on connectivity. It has been seen online, but recency has still drifted to several minutes, consistent with wake failure.
- TAB1 page contains a pending `device.kioskTheme` command from existing work. Do not use destructive controls.
- A historical unrelated `app.install` failed with `INSTALL_PARSE_FAILED_NOT_APK`. Public `https://mdm.ambicdigital.in/files/agent.apk` was independently checked today and is valid: HTTP 200, `application/vnd.android.package-archive`, valid ZIP/APK magic `50 4B 03 04`. Do not conclude agent release APK is corrupt from that old command alone.

## Browser state

In-app browser originally had MDM and AWS tabs. A Google Cloud service-account permissions tab was opened but may not persist in shared state. If needed reopen:

```text
https://console.cloud.google.com/iam-admin/serviceaccounts/details/ambic-mdm-server@ambic-mdm-prod.iam.gserviceaccount.com/permissions?project=ambic-mdm-prod
```

AWS EC2 Instance Connect:

```text
https://ap-south-1.console.aws.amazon.com/ec2-instance-connect/ssh/home?addressFamily=ipv4&connType=standard&instanceId=i-09bdb219f061e62f1&osUser=ubuntu&region=ap-south-1&sshPort=22
```

## Relevant source files

```text
agent-android/app/src/main/kotlin/com/mdmesh/agent/service/CheckInService.kt
agent-android/app/src/main/kotlin/com/mdmesh/agent/service/WakeKeepAlive.kt
agent-android/app/src/main/kotlin/com/mdmesh/agent/service/KeepAliveReceiver.kt
agent-android/app/src/main/kotlin/com/mdmesh/agent/service/AmbicFirebaseMessagingService.kt
agent-android/core/src/main/kotlin/com/mdmesh/core/transport/TransportManager.kt
server/src/main/java/com/hmdm/notification/AgentWakeHub.java
server/src/main/java/com/hmdm/rest/AgentWakeEndpoint.java
server/src/main/java/com/hmdm/service/FcmSenderService.java
server/src/main/java/com/hmdm/service/GoogleWifTokenService.java
docs/FCM-WAKE-SETUP.md
```

## Next sequence

1. User signs into Google Cloud and adds the Token Creator binding above.
2. Verify FCM `HTTP 200` acceptance and fresh sleeping-device check-in.
3. Run one TAB3-only v0.2.31 agent canary after explicit user confirmation; no fleet promotion.
4. Confirm durable recovery behaviour after device sleep/Doze on TAB3.
5. Only after successful canary and explicit approval, roll agent to remaining production tablets.
