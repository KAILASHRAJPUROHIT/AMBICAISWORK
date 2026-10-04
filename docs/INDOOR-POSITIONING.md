# In-store (indoor) positioning

Answers "where is this device inside the store?" without buying any hardware. GPS does not work indoors and the
network location is only good to tens of metres, so devices position themselves from the shop's own Wi-Fi.

## How it works

1. **Floor plan.** In the console (**Indoor map → 1 · Floor plan**) set the store's real width and depth in metres, upload a
   picture of the plan, draw interior walls and name zones (Counter 2, Vault, Billing...). Saved per customer
   (`indoorMap`).
2. **Survey.** (**2 · Survey**) Carry a device around, tap the spot you stand on in the plan, press **Record here**. The
   console sends `device.indoorSurvey {x, y, samples}`; the device averages 1-5 Wi-Fi scans, adds the magnetic field
   strength and uploads one fingerprint (`indoorFingerprint`). Repeat about every 2 m along aisles and around counters.
3. **Positioning on the device.** Every device downloads the plan and survey (`GET /public/agent/v1/indoor`, device
   authenticated, never the picture) and runs a wall-aware particle filter locally (`core/.../indoor`):
   - Wi-Fi scans are matched against the survey (blended from the 4 nearest surveyed points);
   - the step detector and compass move the estimate while the device is carried, and particles cannot cross walls;
   - the magnetic field is a weak secondary cue.
   The estimate (`x`, `y`, uncertainty radius, zone name, time) is reported in telemetry as `dynamic.indoor`.
4. **Where is it?** (**3 · Where is it?**) shows every device on the plan with its uncertainty circle and zone;
   grey means the position is older than 10 minutes. **Locate in store** sends `device.indoorLocate` for an immediate
   estimate (the result also shows in the device's Recent commands).

Nothing runs on a device until its customer has a floor plan. With no plan the tracker is idle and no sensors are used.

## Accuracy: what to expect

- Published research on Wi-Fi + walking + magnetic fusion reports roughly 0.7-0.9 m for people walking with a phone that
  has a gyroscope, in surveyed test spaces. A device sitting still gets a fingerprint-only fix, typically 2-4 m. Zone-level
  answers ("at Counter 2") are the dependable result.
- The simulated-store unit tests (`ParticleFilterTest`) show about 0.4 m walking / 0.6 m still, but that simulation uses the
  same signal model as its survey and has no metal fixtures or crowds. **Measure the real error in the shop** before relying
  on a number: stand a device on known marks and compare with the console.
- Better surveys give better positions: 15 points is the floor for a small shop; more points along aisles help. Re-survey
  (Delete whole survey, then record again) after moving counters or access points.
- The Redmi 14R has no gyroscope, so its walking track is rougher than a tablet's.
- Android limits Wi-Fi scans (about 4 per two minutes for a foreground app); the agent uses the system's latest results
  between its own scans, so a position can lag by up to a minute.
- Phone hotspots and randomised addresses (locally administered MACs) are ignored.

## Version limits

- One floor plan per customer (single floor). Multiple floors need a floor id on the plan and each fingerprint.
- Magnetic matching only nudges; it is not a standalone positioning method.
- Position history is not stored; the console shows the latest estimate from telemetry.

## Parts

| Part | Where |
|---|---|
| Engine (fingerprints, particle filter, wall model) | `agent-android/core/.../indoor/` (`IndoorModel`, `ParticleFilter`, `IndoorEngine`) |
| Wi-Fi / magnetic readers, download + survey upload | `WifiScanner`, `MagneticReader`, `IndoorRepository` |
| Step + compass tracker (service) | `agent-android/app/.../service/IndoorTracker.kt` |
| Commands | `device.indoorLocate`, `device.indoorSurvey` (capabilities `indoorLocate`, `indoorSurvey`) |
| Server | `IndoorResource` (`/private/indoor/v1`), `IndoorAgentResource` (`/public/agent/v1/indoor`), Liquibase `26.10.05-indoor-positioning` |
| Console | `web/src/pages/IndoorPage.tsx`, `components/IndoorPlanCanvas.tsx`, `api/indoor.ts` |
