# FCM wake channel — one-time setup

The agent has a second wake channel built and compiling today (2026-09-18), alongside the
existing WebSocket ([`AgentWakeHub`](../server/src/main/java/com/hmdm/notification/AgentWakeHub.java)):
a silent, data-only, high-priority Firebase Cloud Messaging push, sent whenever the server would
otherwise call `wake()`. Play Services keeps its own connection alive through Doze specifically for
high-priority FCM delivery — something a custom WebSocket cannot do once a device's screen is off
and Doze (or MIUI's own battery manager) has killed the socket. This is why "Sync now" and pending
commands sometimes don't land until a device wakes up on its own.

**Cost: free.** FCM has no usage-based charge for sending messages, at any volume relevant here.

**Re-enrollment: none.** This ships as a normal app update through the same rollout pipeline
already used today (`app.install`, canary → fleet) — no factory reset, no new QR, no change to
Device Owner status or enrollment identity.

## What's already built (server + client code, compiles clean)

- `FcmSenderService` — sends the wake message via FCM's HTTP v1 API, authenticated through
  `GoogleWifTokenService` (no static Google credential, same WIF flow already proven working for
  AMAPI on `ambic-mdm-prod`).
- `AgentWakeHub.wake()` — now fires both channels (WebSocket if open, FCM if the device has a
  registered token) on every wake, not just the WebSocket.
- `devices.fcmToken` column + check-in wiring (server) so the device's current FCM token is stored
  and kept fresh, without ever being erased by a check-in that doesn't include one.
- `FcmTokenStore` + `AmbicFirebaseMessagingService` (client) — receives the token from Firebase,
  reports it on every check-in, and triggers an immediate check-in on a wake message.
- `AGENT-side capability` — none needed; this is transport, not a gated command.

None of this does anything yet. `FcmSenderService.isConfigured()` returns false until
`AMBIC_FCM_PROJECT_ID` is set, and the client SDK can't get a token without real Firebase config —
so today's build is safe to ship as-is; it simply doesn't send FCM pushes.

## Steps to actually turn it on (needs the Google Cloud console — same account as this morning's
## AMAPI/WIF work)

1. **Add Firebase to the existing `ambic-mdm-prod` GCP project** (no new project needed — Firebase
   layers directly onto a GCP project):
   `https://console.firebase.google.com/` → Add project → select `ambic-mdm-prod` from the
   existing-projects list → follow the wizard (Analytics can be skipped/declined).

2. **Register the Android app** in the Firebase console (Project settings → Your apps → Add app →
   Android):
   - Package name: `com.mdmesh.agent`
   - App nickname: anything, e.g. "AMBIC Digital MDM"
   - SHA-1: optional, skip unless prompted — not needed for FCM alone.
   - Download the generated `google-services.json`.

3. **Place the file** at `agent-android/app/google-services.json` in this repo, then apply the
   Gradle plugin — add to `agent-android/build.gradle.kts` (root, `plugins {}` block):
   ```kotlin
   id("com.google.gms.google-services") version "4.4.2" apply false
   ```
   and to `agent-android/app/build.gradle.kts` (`plugins {}` block):
   ```kotlin
   id("com.google.gms.google-services")
   ```
   (The dependency + service class + manifest entry are already in place — this is the only
   remaining code change, and it's exactly two lines plus the JSON file.)

4. **Grant the service account permission to send FCM messages** — same Cloud Shell flow as this
   morning's AMAPI IAM binding. Open `https://shell.cloud.google.com/?project=ambic-mdm-prod` and
   run:
   ```bash
   gcloud projects add-iam-policy-binding ambic-mdm-prod \
     --member="serviceAccount:ambic-mdm-server@ambic-mdm-prod.iam.gserviceaccount.com" \
     --role="roles/firebasecloudmessaging.admin"
   ```

5. **Set the project id on the server** — in `/home/ubuntu/ambic-digital-mdm/.env` on the AWS box:
   ```
   AMBIC_FCM_PROJECT_ID=ambic-mdm-prod
   ```
   then `sudo docker compose up -d --force-recreate server` to pick it up (same pattern as the
   OAuth env vars this morning — the compose file's `server.environment` block does NOT need a new
   entry, since `FcmSenderService` reads this one via plain `System.getenv`, not compose
   substitution — but if that changes, mirror the `AMBIC_GOOGLE_OAUTH_*` entries added to
   `docker-compose.yml` this morning).

6. **Release + verify**: bump the agent version, tag, push — the normal pipeline. Once a device
   checks in on the new build, confirm `devices.fcmToken` is populated for it
   (`SELECT number, fcmToken FROM devices WHERE fcmToken IS NOT NULL;`), then test "Sync now" on
   that device with its screen off for a few minutes first — it should now land within seconds
   instead of waiting for the ~15-minute periodic floor.

## What NOT to do

- Don't skip step 4 and assume WIF alone is enough — `roles/iam.workloadIdentityUser` (already
  granted) lets the AWS role impersonate the service account; it says nothing about what that
  service account itself can *do*. FCM sending needs its own IAM role, same two-step shape as
  AMAPI's `roles/androidmanagement.user` grant this morning.
- Don't create a static Firebase/Google service-account JSON key as a shortcut — the whole point
  of today's WIF work was avoiding exactly that; `FcmSenderService` already goes through
  `GoogleWifTokenService`, so there's no reason to.
