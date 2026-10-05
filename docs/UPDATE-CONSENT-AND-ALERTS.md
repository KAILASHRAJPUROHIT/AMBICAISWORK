# Update consent popup, "stopped reporting" alerts, location retention, fleet map

## Two-way update consent (agent)

Updating the agent restarts the app, so when someone is using the device the update is offered first.

- Applies to any `app.install` of the agent's own package, whether sent by hand from the console or by the automatic rollout.
- **Screen off:** nobody to ask, so it installs straight away.
- **Screen on:** a 60-second popup opens, English above Hindi: "MDM update queued... your current app will close and re-open"
  with **Update now / अभी अपडेट करें** and **Update later / बाद में अपडेट करें**.
  - Update now, or no answer in 60 s: the update installs.
  - Update later: the device tells the server (the command shows **update deferred** in Recent commands, and an
    `updateDeferred` event appears on the timeline). The update is applied once the device is idle (screen off), at least
    30 minutes later.
  - A postponed update cannot wait forever: 24 hours after it was first offered, the popup returns without a "later" button.
- After the app restarts, the original command is reported **done** (or **failed**), and an `updateApplied` event is recorded.
- Console statuses: `waiting for user` (popup showing), `update deferred`, then `done`.

Code: `core/.../update/` (`UpdateConsentPolicy`, `UpdateConsentStore`, `UpdateConsentCoordinator`),
`app/.../update/UpdateConsentActivity.kt`, `AppInstallHandler` (self-update hook), `CheckInService` (once-a-minute `tick`).
The timings live in `UpdateConsentPolicy` and are covered by unit tests.

Choices made without the admin's explicit answer (change in `UpdateConsentPolicy` if wrong): no answer counts as "Update now";
"later" is limited to 24 hours; a postponed update waits for the screen to be off.

## "Device stopped reporting" alerts (server)

`DeviceSilentTask` runs every 5 minutes. A device with no check-in for `MDM_SILENT_MINUTES` (default 45, minimum 20) gets one
`deviceSilent` event, and `deviceBack` when it reports again. Both fire matching admin alert rules (Settings → alerts: choose
the event, or leave blank for all). State is kept in `deviceSilentState` so each outage alerts once.

## Location retention (server)

`LocationRetentionTask` deletes `device_location` rows older than `MDM_LOCATION_RETENTION_DAYS` (default 90, minimum 7), daily.

## Fleet map (console)

**Fleet map** shows every device's last position (grey when older than 30 minutes). Select a device to replay its trail for the
last 4 hours / today / 24 hours / 7 days with play and a slider, and export it as CSV. Tiles default to public OpenStreetMap;
set `VITE_TILE_URL` when building the console to use a different tile server.
