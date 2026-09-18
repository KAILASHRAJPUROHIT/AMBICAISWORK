# Remote view

AMBIC MDM remote view is a bounded **snapshot session**, not continuous live streaming.

- An administrator chooses screen, front camera, back camera, and/or microphone.
- The agent captures at the requested interval for 30 seconds to 30 minutes, then stops.
- The server retains only the latest capture for each device and source. There is no capture history.
- Capture bytes remain behind the authenticated `/private/agent/v1/.../remote/snapshot/...` endpoint; they are never given a public URL.

## Android limits

Screen snapshots require the AMBIC MDM Accessibility service to be manually enabled once on each device in Android Settings. Device Owner cannot silently enable Accessibility services. Camera and microphone permissions can be granted by Device Owner, but Android always displays its own camera/microphone privacy indicator during capture. These platform indicators and consent boundaries are intentional and cannot be bypassed.

## Operational use

Use short sessions and only select required sources. Stop a session when finished. A remote start/stop request is queued like any other MDM command, so it takes effect when the device is reachable and checks in.
