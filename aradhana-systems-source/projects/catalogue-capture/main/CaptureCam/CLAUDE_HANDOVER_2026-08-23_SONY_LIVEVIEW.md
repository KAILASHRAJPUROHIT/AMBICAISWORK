# CaptureCam Sony ZV-E10 II handover — for Codex (2026-08-24 update)

## 2026-08-24 NIGHT — reconnect-storm fix shipped and verified live; fps investigated, no regression found

### Reconnect fix (implemented from Codex's diagnosis above, all live-verified)

Codex correctly diagnosed the 40s-outage bug: `fetchLatestLiveViewSample()`
silently restarted a full 40-retry pump storm every time the previous one
gave up, because there was no terminal-failure latch. Implemented in
`SonyPtpIpController.kt`:

1. **`liveViewPumpFailedEpoch`** -- latches the epoch the pump gave up on;
   `startLiveViewPump()` refuses to restart for that epoch. Only a fresh
   `connectBlocking()` (new epoch) clears it. This is the fix for the
   storm-repeat bug itself.
2. **`LIVE_VIEW_HTTP_REJECT_MAX = 8`** -- a real HTTP 503 status line is
   strong evidence the session is alive but the producer wedged; give up
   after 8 consecutive 503s (~3.2s) instead of the full 16s budget.
3. **`LIVE_VIEW_SESSION_STALE_MS = 75_000L`** -- past the confirmed
   ~82-84s hard boundary, give up on the very first failure instead of
   retrying at all.
4. `sshSession` / `liveViewChannel` marked `@Volatile` per Codex's flag.

**Live-verified results** (real timestamps, three separate drop cycles):
- Fresh-session 503 storm: drop at :20.214 -> recovered :26.061 = **5.8s**
  (was 40+s before the fix).
- Stale-session drop (session age 1:58, past the 75s threshold): drop at
  :23.808 -> recovered :25.510 = **1.7s**, first-failure fast path worked
  exactly as designed.
- Third cycle: same pattern, ~1.5s recovery, no repeat storms observed in
  any of the three.

This is the shipped, working state. Deployed and running live on the
production tablet (192.168.0.22, wireless adb).

### FPS investigation -- NOT a regression, historical "25fps" was a measurement artifact

User reported "fps is stuttery" and later "earlier at the same shutter it
was 25" -- treated as a possible regression and investigated seriously
rather than dismissed.

**Ruled out, in order, all live-tested:**
1. **Camera dial mode (M vs Auto)** -- switched live, fps stayed in the
   same 6.2-9.3 band in both. Not mode-dependent.
2. **AF-C (continuous autofocus)**, added earlier today -- disabled it
   live, fps stayed 6.3-8.4, no change. Re-enabled (confirmed not the
   cause, and it's a real feature worth keeping).
3. **SSH cipher/compression** -- JSch was negotiating whatever cipher the
   camera offered first, in pure-Java with no hardware AES. Forced
   `cipher.s2c`/`cipher.c2s` to prefer `aes128-ctr` etc. first and disabled
   compression. No measurable change (still 6.7-9.3fps, same ~190KB/frame).
   Kept the change anyway (harmless, may help on worse WiFi) but it did not
   explain the number.

**Root cause of the "25fps" reference point**: found and ran the actual
historical test artifacts from earlier today
(`scratchpad/sony_liveview_test.mp4`, `measure_fps.py`/`measure_fps2.py`).
The video's **container** framerate is 25.93fps -- that's an `adb
screenrecord` encode-rate artifact, NOT a measurement of how often the
live-view image content actually changed. Running the actual crop-region
pixel-diff script (`measure_fps2.py`) against that same clip gives the
real content update rate: **0.50 FPS** (median gap 116ms... over a
6-second clip with only 3 real content changes detected). So "25" was
never a real live-view frame rate at all -- it was a screen-recorder
artifact for a mostly-static frame. Tonight's actual measured rate
(6.2-9.3fps, via the app's own `source`/`decoded` counters, which count
real distinct JPEGs received from the camera -- ground truth, not video
playback) is **12-18x faster** than what was really happening in that
earlier clip.

**Current understanding of the 6-9fps ceiling**: `jpegBytes` telemetry
added to the renderedFps log line shows each live-view JPEG is
~186-198KB. At the observed fps that's roughly 1.3-1.8MB/s sustained over
the tunnel. `dropped=0` throughout every sample -- the pump drains the
socket as fast as bytes arrive, so the app-side pipeline is NOT the
bottleneck. No camera menu setting for live-view image quality/resolution
was found (checked, user confirmed "nothing"). Working theory: this is
the ZV-E10 II's own embedded live-view HTTP server's real ceiling for
full-resolution JPEGs over this remote path, not something fixable from
the app side without finding an SDK/PTP property that controls live-view
JPEG size (PROP_LiveViewUrl 0xd278's query string
`%2a%3a%2a%3aimage%2fjpeg%3a%2a` may encode a format/size selector worth
decoding if this needs revisiting -- untested, flagging for fresh eyes).

**Unverified next step, if fps is revisited**: decode what the
`%21%2a%3a%2a%3aimage%2fjpeg%3a%2a%21%21%21%21%21` query suffix on the
LiveViewURL actually selects (looks like a DPS/format spec token from the
PTP-IP LiveView extension) -- there may be an alternate query value that
requests a smaller/faster live-view stream instead of full resolution.
Not attempted tonight; flagging as the most promising unexplored lever.

## 2026-08-24 EVENING — variable recovery time (1.4s to 40+s), open question for fresh eyes

### THE ACTUAL OPEN QUESTION

After the natural ~83s session boundary (or the ~45s HTTP-only close within it)
fires, recovery via the pump's own retry + SonyProductionCamera's reconnect
sometimes takes **~1.4-1.6s** (clean, fast, single SSH re-auth then done) and
sometimes takes **40+ seconds** (a long storm of `HTTP/1.1 503 Service
Unavailable` responses before it finally recovers). Both are measured live,
not estimated. **What determines which path happens, and can the slow path
be eliminated or shortened to consistently match the fast one?**

### Evidence for both cases (exact log excerpts)

**FAST case** (~1.4s), 2026-08-24 11:41:33-11:41:34:
```
11:41:33.302 W SonyProduction: Sony Live View lost; sessionAge=01:24
11:41:33.801 I SonyPtpIp: SSH authenticated to 192.168.0.14 as pkANY7
11:41:34.731 I SonyPtpIp: Sony PTP-IP-over-SSH handshake complete
11:41:34.751 I SonyPtpIp: Sony persistent Live View HTTP stream connected
```
Drop to fully recovered: 1.449s. SSH auth started only 0.5s after drop
detected, handshake itself took ~0.93s. This pattern repeated cleanly at
least 4-5 times earlier in the session (see "black-screen root cause" section
below for the original 4-sample confirmation of the ~82-84s boundary itself).

**SLOW case** (40+s), 2026-08-24 11:49:50-11:50:32ish:
```
11:49:50.193 W SonyPtpIp: Sony Live View HTTP rejected: 503 Service Unavailable
[... repeats every ~0.5s, dozens of times ...]
11:50:04.818 I SonyPtpIp: Live View pump stopped
[... 503 rejections CONTINUE even after pump stopped, dozens more ...]
11:50:32.940 W SonyProduction: Sony Live View lost; sessionAge=01:24
11:50:34.183 I SonyPtpIp: Sony persistent Live View HTTP stream connected
```
Here the 503 storm started ~42 seconds BEFORE `SonyProductionCamera` even
logged "Live View lost" -- meaning the LOW-LEVEL pump (`SonyPtpIpController
.runLiveViewPump`) was patiently retrying HTTP-only reopens against a
still-alive SSH/PTP session for its full budget
(`LIVE_VIEW_MAX_REOPEN_FAILURES=40 * LIVE_VIEW_REOPEN_RETRY_DELAY_MS=400ms`
= ~16s) BEFORE giving up ("Live View pump stopped" at 11:50:04.818), and the
503s kept coming for ANOTHER ~28 seconds after that before
`SonyProductionCamera`'s own higher-level failure detection
(`MAX_CONSECUTIVE_FRAME_FAILURES=8` in `startLiveLoop`, `SonyProductionCamera
.kt`) finally noticed and tore down for a full fresh SSH reconnect, which
THEN succeeded quickly once attempted.

### Working theory (unconfirmed -- this is the fresh-eyes question)

There appear to be TWO different failure/recovery paths depending on WHICH
part of the camera died:
1. **Session-level death** (the ~83s hard boundary, SSH/PTP session itself
   gone): the pump's HTTP-only retries are doomed from the start (nothing
   to reopen against), but apparently fail FAST/visibly enough that
   `SonyProductionCamera` notices quickly and does a fresh SSH reconnect
   almost immediately -- this is the ~1.4s fast case.
2. **HTTP-producer-only death** (the underlying SSH/PTP session is still
   technically alive, but the camera's internal HTTP live-view producer
   specifically has wedged/died, e.g. after being disturbed by something):
   the pump's HTTP-only retries look plausible (channel connects fine,
   Sony just keeps answering 503) so it burns its FULL ~16s budget
   patiently retrying something that will never succeed on its own, THEN
   `SonyProductionCamera` needs ANOTHER ~8 failed high-level fetch attempts
   before it gives up and forces the full reconnect that actually fixes it.
   This is the 40+s slow case.

If this theory is right, the fix is NOT a longer retry budget (already
tried extending it once today, from ~1s to ~16s, which is what CREATED the
"pump patiently wastes 16s before giving up" problem in the slow case --
before that change it would have failed over to a full reconnect faster,
just less patiently for genuinely transient blips). The right fix is
probably: detect NEAR THE START of a 503 storm whether the underlying SSH/
PTP session (`sshSession?.isConnected`, `hasOpenControlTransport()`) is
STILL alive, and if so, don't wait out the full HTTP-only retry budget --
escalate directly to a full session teardown+reconnect much sooner, since
patient HTTP-only retrying only makes sense when there's a real chance the
producer self-recovers, and this evidence suggests it often doesn't.

**Untested hypothesis, not yet implemented**: check `hasOpenControlTransport
()` partway through the HTTP-reopen retry loop (e.g. after ~5-8 failures,
~2-3s) -- if the control transport is confirmed still alive but HTTP keeps
502/503ing, that's the "producer wedged, session fine" signature; escalate
immediately to `SonyProductionCamera` triggering a fresh reconnect rather
than continuing to retry HTTP-only for the full ~16s.

### Also tried and reverted today, don't repeat these

1. **Proactive lease refresh via `0x9209`** (property-poll) at 30s into
   session, replacing reactive recovery. RESULT: made it worse -- put the
   camera's HTTP producer into a ~13s 503 state on ITS OWN, on a
   predictable 30s cadence. Reverted; do not re-add any periodic call to
   `readSonyProperties()`/`0x9209` as a keepalive or refresh mechanism.
2. **Proactive lightweight refresh via `SDIOConnect`** (opcode `0x9201`,
   tiny 8-byte responses, NOT the heavy property dump) at 65s into session,
   attempting to preempt the ~83s boundary. RESULT: the refresh call itself
   got stuck for ~12s (contending with the pump thread's own concurrent
   retry activity for the same session resources) and still returned
   `false` -- the drop happened anyway at the same ~80s mark. Reverted.
   Lesson: ANY proactive refresh attempt so far has collided with the
   pump's own reactive retry logic running concurrently on the same
   session -- that contention, not the specific opcode, is the real
   blocker for a "prevent it before it happens" approach. A future attempt
   would need actual mutual exclusion between "proactive refresh in
   progress" and "pump's reactive retry loop", not just reusing the
   existing `operationLock`.
3. **Removed a guaranteed-wasted 1-second wait**
   (`waitForPropertyEnabled(PROP_OperatingMode, 1_000L)` -- this camera's
   `5013` property NEVER reports `enabled=true`, confirmed by the code's
   own pre-existing comment, so this call always burned its full budget for
   nothing). KEPT this one -- it's safe and correct even though it didn't
   meaningfully move the FAST-case number (~1.4s before and after,
   suggesting this wait wasn't actually the dominant cost in the fast
   path -- SSH authentication itself is). Still worth having; does no harm.
4. **Dual-session tolerance probe**: opened a completely separate SSH
   session (via a standalone Python/paramiko script, not the app) while
   the app's session was active, to test whether the camera tolerates
   brief session overlap (which would enable a true make-before-break
   handoff with zero visible gap). RESULT: inconclusive -- the probe
   happened to launch in the middle of an already-in-progress 503 storm
   from an unrelated cause, so cause/effect couldn't be isolated. The
   second SSH session DID authenticate and DID open a PTP-IP tunnel
   successfully while the first session existed (in whatever state it was
   in) -- so a second session isn't flatly rejected at the SSH layer, but
   this doesn't confirm a clean overlapping handoff actually works. Script
   is saved at `scratchpad/test_dual_session.py` if picked up again --
   ONLY run it when the app's session is confirmed clean/steady-state
   first (check `renderedFps` telemetry for at least 10-15s of zero drops
   immediately before running it), so a real result isn't contaminated by
   coincidental unrelated instability like this run was.

## 2026-08-24 OPERATIONAL FINDING — Sony's own app must be fully closed, not just backgrounded

Hit this live: after ~2:30 of clean streaming, live view died with a
PERSISTENT 503 storm that did NOT clear on its own -- survived the stall
watchdog force-reopen, survived the pump's full ~16s retry budget, survived
a full SSH/PTP re-handshake attempt. This looked like a serious new bug.

**Actual cause:** Sony's own Creators' App (`jp.co.sony.ips.portalapp`) was
still running in the BACKGROUND on the tablet -- it had been launched
earlier this session for the control-catalog/FPS investigation and never
force-stopped, just left minimized. `am force-stop jp.co.sony.ips.portalapp`
fixed it INSTANTLY -- next connection attempt got a clean handshake and the
stream resumed at 25 FPS within half a second.

**Conclusion: the camera's single-remote-session lock is held even by a
BACKGROUNDED Sony app, not just a foregrounded one.** This is a real
operational constraint, not a CaptureCam bug -- no amount of client-side
retry/patience can work around another app already holding the one session
slot the camera allows.

**Action item for production use:** before/during any CaptureCam session,
confirm Sony's Creators' App is not just closed on-screen but actually
force-stopped (swiping it away in recent-apps may not be enough depending
on the device/OS -- use Settings > Apps > force-stop, or `adb shell am
force-stop jp.co.sony.ips.portalapp` during testing). If this keeps
happening in production, consider having CaptureCam itself detect this
failure mode specifically (persistent 503s with no clearing) and surface a
clear operator-facing message ("close Sony's app") rather than just
retrying silently forever -- not yet implemented, worth adding if this
recurs.

## 2026-08-24 LATEST update — black-screen root cause found AND fixed, verified live

**The 45s black-screen bug is fixed and verified against the real camera,
not just theorized.** Root cause was NOT the refresh timing constant (that
was a red herring, tried and disproven first) -- it was that
`refreshLiveViewLease()` called `readSonyProperties()` (PTP opcode `0x9209`)
on every proactive refresh, and this exact file already had a comment
(near `startKeepAliveThread`) documenting that this camera stops answering
`0x9209` once the remote session settles -- that constraint was respected
for the idle keepalive thread but NOT for live-view refresh. Calling it put
the camera's HTTP live-view producer into a ~13s string of `503 Service
Unavailable` responses, which then exhausted the pump's old 1-second retry
budget and forced a full SSH/PTP re-handshake (~10s) -- a **self-inflicted
~23s outage every 30s**, strictly worse than just letting Sony's natural
~45s close happen and recover via a plain HTTP reopen on the same session.

**Fix applied (`SonyPtpIpController.kt` + `SonyProductionCamera.kt`):**
1. Removed the entire proactive-refresh mechanism from
   `SonyProductionCamera.startLiveLoop` -- it only caused harm.
   `refreshLiveViewLease()` itself is now unused; left in place but nothing
   calls it (fair game to delete if picked up again, or repurpose for
   something that doesn't touch `0x9209`).
2. Removed the dead `leaseRefreshFailed` variable and the `if
   (leaseRefreshFailed)` branch -- since it's always false now, that branch
   was dead code. The graceful "preserve last frame, quick reconnect" path
   it used to gate is now taken UNCONDITIONALLY on any live-loop exit, since
   every exit now means the same thing that branch used to mean (a
   temporary hiccup the pump's own retry couldn't clear, not a genuinely
   dead camera -- a truly gone camera fails the loop's own
   `camera.isConnected` condition instead).
3. Extended `SonyPtpIpController`'s HTTP-reopen patience: `LIVE_VIEW_MAX_
   REOPEN_FAILURES` 5->40, new `LIVE_VIEW_REOPEN_RETRY_DELAY_MS=400L`
   (~16s total budget, was ~1s). Also extended `LIVE_VIEW_STALL_TIMEOUT_MS`
   (the keepalive-thread watchdog that force-closes a stalled channel)
   8s->20s so it can't fire mid-way through the pump's own longer retry
   window and cause a redundant second interruption.

**Verified live, twice, with real telemetry:**
- Natural cycle WITHOUT the refresh mechanism ran clean 11:12:18->11:13:00
  (~42s), zero failures, steady 24-25 FPS, `dropped` staying at 0-2 out of
  800+ frames. This is the exact symptom the operator originally reported
  (silent black flash every ~45s) and it did not recur.
- One separate edge case found: a session that had JUST been torn down and
  rebuilt by a control operation (autofocus test via
  `SonyPtpIpController.driveAutoFocus`/`runFreshControl`, confirmed by the
  `0x9207` AF press/release ops visible right before it in the log) hit a
  close only 14s into that fresh session's life (`sessionAge=00:14`) and
  needed the full ~8s patient-retry-then-reconnect path to recover. It DID
  recover cleanly on its own (25fps resumed within seconds, `preserveLast
  SonyFrame` kept the UI from flashing) -- just via the slower path, not
  the cheap HTTP-only one. Likely a DIFFERENT, narrower issue: sessions
  freshly rebuilt by `runFreshControl()` may have a shorter live-view
  producer lifetime than a long-running undisturbed one. NOT yet
  root-caused -- separate from the main bug, lower priority (the operator's
  reported symptom was about idle/continuous viewing, not immediately
  after issuing a zoom/focus/exposure command).

**FPS note:** with the property-poll refresh gone, sustained FPS also
improved to a steady **24-25 FPS** (was ~18-20 with the old broken refresh
fighting the stream every 30s). This lines up with -- and now essentially
matches -- Sony's own measured floor of ~23-30 FPS from the earlier
screen-recording test. The two problems (FPS ceiling and black screen)
turned out to be the same root cause wearing two symptoms.

**Not yet done:** the `runFreshControl()`-adjacent edge case above. Also
have not re-run this against a longer soak (10+ minutes) to rule out any
slower-building issue; the ~4 minutes of live monitoring here found no
regressions but is not a full endurance test.

## 2026-08-24 LATE update — pump validated live, new findings, new bug found

**Pump is confirmed working against the real camera.** Live telemetry samples,
sustained over 2+ minutes: `source == decoded` every single time, `dropped=0`
or `dropped=1` (never climbing). This proves the pump is never backlogged —
we're now camera-production-limited, not consumption-limited. `latestAgeMs`
sat in the 15-100ms range throughout (vs 5,000+ms before today's fix).
FPS observed: 9.5 to 22.2, averaging ~18-20 once past the first couple
seconds after (re)connect.

### NEW BUG FOUND: black screen every ~45s (operator-visible, confirmed live)

Root cause is in the logs, not a guess. Excluding the one deliberate
lease-refresh-triggered close, every `"Live View pump read failed: Sony Live
View HTTP stream closed"` line lands at **almost exactly 45-46s** after the
previous one:
```
10:47:31 -> 10:48:17 (46s) -> 10:49:52 -> 10:50:38 (46s) -> 10:51:24 (46s)
-> 10:52:10 (46s) -> 10:52:55 (45s)
```
This is **Sony's HTTP live-view server unilaterally closing the stream after
~45s**, independent of our code. Source/decoded counts are healthy right up
to each close -- not a bug in the pump, a server-side session timeout we
aren't preempting.

**The actual defect:** `SonyProductionCamera`'s proactive refresh
(`PROACTIVE_LIVE_SESSION_RENEW_MS`) is set to fire before a **90s** watchdog
that was assumed, not measured. The REAL timeout is ~45s. Because our
refresh timer (90s) is later than the real close (45s), the stream always
dies on its own first -- we're reacting (reopen-after-failure), never
preempting. Each reopen is fast (<1s, confirmed by source-counter resets in
the logs) but **nothing is drawn to the screen during that gap** -> visible
black flash. Operator confirmed seeing this live.

**Fix, not yet applied (still read-only per operator instruction this
session):**
1. Change `PROACTIVE_LIVE_SESSION_RENEW_MS` from `70_000L` to something
   under 45s -- e.g. `35_000L` -- so the refresh happens BEFORE Sony's own
   close, not after.
2. Separately: `onFrame`'s bitmap holder (`MainActivity`/diagnostics side)
   should keep displaying the LAST GOOD bitmap during any reopen gap instead
   of clearing to black. Even with fix #1 tuned correctly, any late refresh
   or transient network hiccup should degrade to "slightly stale frame"
   rather than "black screen" -- much better failure mode for an operator
   watching a live feed.

### FPS ceiling clarified: not fixed at 20, but not "60" either

Operator asked for 60 FPS "for max gold detection accuracy" -- pushed back
because (a) detection accuracy depends on per-frame quality not capture
rate, motion reaction time is the real benefit of higher FPS, and (b)
source==decoded proves we're camera-limited already, more client code can't
push past what the camera sends.

**New finding, from Sony's OWN app strings** (`app_strings.txt` in
`C:\Users\kaila\AppData\Local\Temp\claude\...\scratchpad\`, extracted from
Creators' App 3.4.1 base.apk via a simple regex byte-string dump, no
decompilation/repacking):
```
"Frame rate of Live View may decrease if you select 'Image Quality Priority'."
STRID_guide_liveview_quality
STRID_liveview_display_setting_quality
```
Sony's app exposes a **Live View Display Quality** setting with an explicit
documented FPS/quality tradeoff. Our frames are 160-190KB, consistent with a
"quality priority" style mode. **This means the current ~20 FPS ceiling may
be a QUALITY SETTING, not a hard transport/firmware limit** -- worth
checking the camera's own menu for this option before assuming 20 is the
true ceiling. Have NOT yet found the corresponding PTP property code for
this setting (not yet distinguished from `PROP_LiveViewStatus`/`0xD221` or
any property already in `readSonyProperties()`'s table) -- if picking this
up, that's the next concrete step: dump the full property table and cross
reference against a menu change on the camera to find which property this
maps to. (Note: do NOT confuse with `STRID_network_streaming_setting_*` /
`_50p`/`_60p` strings found in the same dump -- those are Sony's separate
"Live Streaming" broadcast feature, a different camera mode entirely, not
PTP remote-preview.)

**Sony's live-view FPS -- now measured, twice.** First attempt (adb
screenrecord + OpenCV frame-diff on a static showroom scene) returned 0
changes because nothing in frame moved, not because the stream was slow --
false negative, not a real result. Redone with the operator waving a hand
in frame, and cropped to just the live-view content region (the first pass
diffed the WHOLE screen including large static black letterbox bars, which
diluted the signal to near-zero even with real motion present):

```
141 of 183 recorded frames showed genuine content change
gap between changes: min=33ms median=33ms max=164ms
container recording rate: 30.48 fps
```

Median gap == the screen recorder's own native frame interval (33ms @
30.48fps container rate). Honest reading: **Sony's live view updates at AT
LEAST ~23-30 FPS** -- we've hit the ceiling of the MEASUREMENT TOOL
(`adb shell screenrecord` itself only samples ~30fps), not necessarily
Sony's true source rate. Do not claim a higher number than this without a
measurement method that can sample faster than 30fps (e.g. a real high-
speed camera pointed at the tablet screen, not another Android screen
recording). What IS solid: Sony's app is measurably faster than our current
~18-20 FPS -- a real gap, not assumed.

Scripts: `scratchpad/measure_fps.py` (first, flawed, whole-screen-diff --
kept for reference showing the pitfall) and `scratchpad/measure_fps2.py`
(second, correct -- crops to the live-view content region before diffing,
region hardcoded as `x=0..507,y=617..953` for `720x1600` recordings on this
tablet, RE-DERIVE if recording resolution changes). Recording via
`adb shell screenrecord --size 720x1600 --time-limit 6 /sdcard/x.mp4` (note:
`--bit-rate` flag caused `Encoder failed (err=-38)` on this tablet, omit it;
`--size` was required, default failed too). Frame extraction for visual
sanity-checks: `scratchpad/extract_frames.py`.

No evidence found anywhere (strings, measurement, or Sony docs) that 60fps
exists on the remote-preview interface at all -- that number most likely
belongs to Live Streaming (broadcast) mode or local-monitor movie-mode
frame rate, neither of which is what this integration uses.

### Sony Creators' App 3.4.1 live-view screen -- full control catalog (from screenshot, not decompilation)

Screenshot: `scratchpad/current_screen.png`. Observed live against the real
camera, in a jewellery-shop location, camera in P (Program Auto) mode.
**Operator wants ALL of these replicated in CaptureCam for jewellery photo
quality** -- listed here as the actual target control surface, not a
guess:

**Top bar:**
- Back arrow (exit remote screen)
- Touch-function toggle icon (touch-AF on/off, based on icon shape)
- Two rotate-style icons -- likely orientation lock / auto-review toggle (not confirmed)
- Shot count remaining: "9999" (storage-based, informational)
- Aspect ratio indicator: "3:2"
- Image size indicator: "L"
- Battery: icon + "25%"

**Right panel (main shooting parameters, each with < > step buttons):**
- Mode indicator: "P" (Program Auto) -- likely tappable to change exposure mode (M/A/S/P)
- **Shutter speed**: "1/50" -- CONFIRMS a settable shutter-speed property is exposed remotely; our controller does not yet expose this (only `setExposureCompensation`, not raw shutter speed)
- **Aperture**: "F 4.5" -- CONFIRMS remote aperture control exists; not yet in our controller (kit lens's motorized aperture, PTP standard prop is `0x5007` per our own code's existing `PROP_FNumber` constant reference from yesterday -- check whether that's wired up or just declared)
- **Exposure compensation**: "±0.0" -- we already have `setExposureCompensation` via `0x5010`
- **ISO**: "125" -- we already have `setIso` via `0xD21E`
- Row of small mode icons: **"K"** (white balance -- we have `setWhiteBalance`/`0x5005`), **"AF-C"** (focus mode, continuous -- we have `setFocusMode`/`0x500A` but need to confirm AF-C is a settable value we send, not just AF-S), a plain rectangle icon (likely **focus area** -- Center/Spot/Wide, NOT currently in our controller at all), **"DRO AUTO"** (Dynamic Range Optimizer -- NOT in our controller; audit doc says "Disable, preserve RAW" for production so may be intentionally skipped), a metering icon (**metering mode** -- NOT in our controller)
- **Zoom control**: a horizontal DRAG SLIDER between "W" and "T" labels, with a magnifying-glass button -- this is CONTINUOUS/proportional, not the discrete tele/wide step-pulse approach our `driveZoom()` uses. Sony's own remote zoom is analog-feeling; matching that feel (not just direction) may be part of what "best jewellery pictures" needs for precise framing. Our `setZoomRatio(ratio: Float)` already exists (uses velocity pulses internally per yesterday's audit doc) -- worth checking if it can be UI-exposed as a real drag slider instead of Tele/Wide buttons only.

**Bottom bar:**
- "MENU" -- opens Sony's full camera settings menu (deep tree, out of scope to replicate entirely)
- Large circular shutter button (full-res capture trigger)
- "AEL" -- Auto Exposure Lock, momentary/toggle button. NOT in our controller.

**Concrete gaps this reveals versus our current `SonyPtpIpController` API**
(confirmed by reading the file's current `fun` list, not guessed):
1. **Shutter speed** -- no setter exists (`PROP_ShutterSpeed` isn't even declared as a constant currently; PTP standard is a datatype-specific encoded value, needs its own research pass like ISO/WB did)
2. **Aperture (F-number)** -- no setter exists yet, only referenced as a constant note in the audit doc
3. **Focus area** (Center/Spot/Wide/Expand) -- not present at all
4. **Metering mode** -- not present at all
5. **AEL (exposure lock)** -- not present at all
6. **Exposure mode (P/A/S/M)** -- not present; audit doc recommends "Manual Exposure" for production, so this may matter more than DRO/metering do
7. **Zoom as a continuous/proportional control** in the UI, not just discrete Tele/Wide -- backend (`setZoomRatio`) may already support it, front-end (BleDiagnosticsActivity buttons) does not yet expose it that way

Do NOT implement these blind -- each new PTP property code needs the same
"find it, confirm the encoding, test against real camera, watch for the
0x2003/SessionNotOpen-style surprises" treatment ISO/WB/focus-mode got
yesterday. Aperture and shutter speed in particular are worth prioritizing
since they're core to "best jewellery pictures" (audit doc's recommended
production preset explicitly wants ISO 100, f/7.1-f/8, ~1/100s -- currently
none of aperture/shutter-speed can be SET remotely even though the audit
assumed they could).

## 2026-08-24 update — read this first, then the rest of the file below for full context

**Priority #1 from this file (one-owner latest-frame pump) is implemented, built, and installed.** See "What changed 2026-08-24" section near the top for the summary — full diff is in the working tree, uncommitted, same as everything else this file describes. Do not revert it; extend it.

**Current blocker is just physical/network, not code:** as of the last check, the camera was not reachable at `192.168.0.14` (no ping, port 22 closed) — it was off or not in Remote Shooting mode. Operator is powering it on now. Once `MENU > Network > Cnct./Remote Sht. > Remote Shoot Function > Remote Shooting > On` is confirmed, the app's existing bounded-backoff reconnect (`SonyProductionCamera.scheduleReconnect`) should pick it up automatically — no restart needed.

**Next step once connected:** run acceptance test B (preview latency / hand-wave) from section 12 below, using the new `liveViewTelemetry()` string that's now printed alongside every `renderedFps` cadence log line (`source=… decoded=… dropped=… reopens=… latestAgeMs=…`). That telemetry did not exist before today's change — use it, don't re-add a separate counter.

### What changed 2026-08-24 (this session, on top of everything below)

Implemented section 10's "exact next implementation" (one-owner latest-frame pump) in `SonyPtpIpController.kt`:

- New `LiveViewSample(sequence, jpeg, receivedAtNanos)` data class.
- New pump: `startLiveViewPump()` / `stopLiveViewPump()` / `fetchLatestLiveViewSample()` / `awaitLatestLiveViewFrame()` / `liveViewTelemetry()`. One dedicated `SonyLiveViewPump` thread owns the HTTP stream, drains it with **no pacing sleep**, and publishes into a single-slot `AtomicReference<LiveViewSample?>` — overwriting an unconsumed frame increments a drop counter instead of queuing.
- `fetchLiveViewJpeg()` (old API, still used by `BleDiagnosticsActivity`) is now a thin wrapper over `fetchLatestLiveViewSample()`, so diagnostics and production share one transport — per section 10's explicit rule, do not create a second implementation.
- Cancel-safe stop: `stopLiveViewPump()` / `disconnect()` now call `forceCloseLiveViewChannel()` **without** holding `liveViewLock`, fixing the exact hazard section 9 flagged ("Blocking read cannot currently be cancelled safely" — `closeLiveViewHttpStream()` used to need the same lock a wedged reader held).
- Stall watchdog added inside the existing keepalive thread (`startKeepAliveThread`): if no new frame lands within `LIVE_VIEW_STALL_TIMEOUT_MS` (8s), it force-closes the channel from outside the read lock; pump reopens next loop iteration.
- `SonyProductionCamera.kt`'s live loop and `BleDiagnosticsActivity.kt`'s Sony preview loop both had their `Thread.sleep(FRAME_INTERVAL_MS - elapsed)` pacing removed — `fetchLatestLiveViewSample()`/`fetchLiveViewJpeg()` now block until a genuinely new frame exists, so the old fixed-interval cap was actively working against throughput.
- Cadence log line in `SonyProductionCamera` now prints `renderedFps` **and** `liveViewTelemetry()` together on the same line — do not judge FPS from `renderedFps` alone again (that's exactly the "19 FPS but 5s stale" trap from yesterday).

Build verified: `.\gradlew.bat assembleDebug` → `BUILD SUCCESSFUL`. Installed via `adb install -r` to `192.168.0.22:5555` (tablet). This did NOT get physically validated against a live camera yet — connection dropped before/during install-verification because the camera itself was off-network. **Section 12 test B is still outstanding — do not report this as fixed until that test runs.**

Not yet done from section 10/section 9 (still open, pick up next):
- Telemetry is a formatted string (`liveViewTelemetry()`), not the structured per-metric fields section 11 asks for (p50/p95 decode/analyse ms, jpeg byte min/max, bytes/sec). Current version is enough to validate B qualitatively; extend if you need the full table.
- Section 9's "HTTP framing is not understood yet" (multipart/x-mixed-replace vs raw concatenated JPEG vs Sony LiveView Dataset) — untouched. Marker-scanning parser (`readNextLiveViewJpeg`) is unchanged aside from now being called from the pump thread instead of the old serial loop.
- Per-frame allocation reuse — untouched, still allocates/grows per frame.
- `max_input_buffer_size` 1MB JSch setting — already present from yesterday (section 8 explains why); left as-is. Re-evaluate 256KB vs 1MB only after B passes, per section 10's own ordering.
- Section 12 tests C/D/E/F (detection load, gimbal, QR, full E2E) — not started.

---

Date: 2026-08-23 IST (original handover below, unchanged)  
Status: paused by operator; continue tomorrow  
Immediate blocker: Sony Live View is still unusable because preview latency varies from under five seconds to more than five seconds. The latest build can display roughly 19 FPS, but it replays stale buffered frames instead of staying near live.

## 1. Read this first

Do not describe the Sony integration as production-ready. Transport, preview, automatic recovery, deterministic gold detection, QR integration, optical zoom control and RSC 2 control exist, but the end-to-end DSLR capture pipeline has not passed.

The next job is not another frame-rate-label tweak. Replace the synchronous fetch/decode/analyse loop with a continuously draining, latest-frame-only transport pump. Then measure source arrival FPS, decoded FPS, rendered FPS, dropped frames and end-to-end motion latency independently.

The user explicitly stopped work for the night. No drain-to-latest implementation was made after that instruction. This handover is the only new file created after stopping.

Critical user requirements:

- Persistent Sony Live View and camera control. Without them, the project is considered useless.
- Near-real-time preview. Requested target: 30 FPS. Five-second lag is unacceptable even if an FPS counter looks high.
- No local AI for gold detection. Preserve deterministic color/geometry/temporal detection.
- DSLR must replace the previous phone-camera visual pipeline without losing QR/tag detection, gold detection, focus/clarity decisions, zoom, gimbal pointing, three-angle capture, upload or self-healing.
- Capture each ornament from three gimbal angles and keep the existing catalogue/upload workflow.
- Prefer clean-room protocol inspection. Do not modify/repack Sony Creators' App, bypass authentication or copy proprietary code.
- Preserve all existing uncommitted work. The working tree contains large user/previous-session changes.

## 2. Repository and device state

Repository root:

```text
C:\Users\kaila\Desktop\CaptureCam-master-checkout
```

Android project:

```text
C:\Users\kaila\Desktop\CaptureCam-master-checkout\CaptureCam
```

Git state:

```text
Branch: production-legacy-flow
HEAD: 4e883aa58730470a3ebab71758fc4d40b6aff65b
HEAD subject: Fix TransactionID off-by-one -- PTP spec reserves 0 for OpenSession
```

Configured remotes:

- `origin` fetches from `AradhanaJewellers/aradhana-catalogue-tool`.
- `origin` pushes to both the Aradhana and personal repositories.
- `personal` points at `KAILASHRAJPUROHIT/ambic-catalogue-studio`.

Do not push or commit until the live-view fix is verified and the user asks. Current uncommitted state:

```text
M  app/src/main/AndroidManifest.xml
M  app/src/main/java/com/aradhana/capturecam/BleDiagnosticsActivity.kt
M  app/src/main/java/com/aradhana/capturecam/BoundsOverlayView.kt
M  app/src/main/java/com/aradhana/capturecam/FocusZoomController.kt
M  app/src/main/java/com/aradhana/capturecam/MainActivity.kt
M  app/src/main/java/com/aradhana/capturecam/MaterialDetector.kt
M  app/src/main/java/com/aradhana/capturecam/RSC2Controller.kt
M  app/src/main/java/com/aradhana/capturecam/SharpnessAnalyzer.kt
M  app/src/main/java/com/aradhana/capturecam/SonyPtpIpController.kt
M  app/src/main/res/layout/activity_ble_diagnostics.xml
M  app/src/main/res/layout/activity_main.xml
?? SONY_ZV_E10M2_JEWELLERY_CAPABILITY_AUDIT.md
?? app/src/main/java/com/aradhana/capturecam/SonyGoldServoController.kt
?? app/src/main/java/com/aradhana/capturecam/SonyGoldTargetDetector.kt
?? app/src/main/java/com/aradhana/capturecam/SonyProductionCamera.kt
```

The delta against HEAD is approximately 2,453 insertions and 189 deletions across the tracked files. Treat all of it as valuable work, not disposable experimentation.

Current build/install facts:

```text
APK: C:\Users\kaila\Desktop\CaptureCam-master-checkout\CaptureCam\app\build\outputs\apk\debug\app-debug.apk
APK size: 219,240,468 bytes
APK built: 2026-08-23 19:59:55 IST
Tablet install updated: 2026-08-23 20:00:38 IST
Package: com.aradhana.capturecam
versionName: 1.0
versionCode: 1
```

Latest combined build passed:

```powershell
.\gradlew.bat lintDebug assembleDebug
```

It was installed with `adb install -r`. This supersedes the original handover's older USB-install restriction/manual file-manager workflow.

Current wireless ADB target:

```text
C:\platform-tools\adb.exe -s 192.168.0.22:5555
Device model: 2509BRP2DI
Product/device: organ_in / organ
Status at handover: connected
```

Java used successfully:

```text
C:\Tools\jdk-17.0.12+7
Temurin OpenJDK 17.0.12
```

## 3. Hardware and network facts

Camera:

```text
Sony ZV-E10 II / ZV-E10M2
Current lens: Sony E PZ 16-50 mm F3.5-5.6 OSS II / SELP16502
Camera LAN IP during testing: 192.168.0.14
```

Camera and tablet are on the shop LAN, not camera-as-access-point mode.

Tablet Wi-Fi facts measured from Android:

```text
SSID: Shree_5G
Frequency: 5765 MHz
Protocol: Wi-Fi 5 / 802.11ac
RSSI: -48 dBm
Link speed: 866 Mbps
```

Tablet-to-camera ping during diagnosis:

```text
0% packet loss
Mostly 3-23 ms
One 208 ms spike
```

Conclusion: LAN bandwidth is not the main explanation for a persistent five-second backlog. Wireless ADB was idle during the earlier live-view measurements and is not the primary bottleneck. Do not claim the camera's own radio band from the tablet data; only the tablet association was directly observed.

Sony Access Authentication credentials are provisioned in the app/camera settings. Do not copy the password into more documentation or commits. If authentication fails, read the current values from camera `MENU > Network > Network Option > Access Authen. Info` and update secure local configuration.

Camera menu prerequisite:

```text
MENU > Network > Cnct./Remote Sht. > Remote Shoot Function > Remote Shooting > On
```

If Remote Shooting is Off, the camera does not expose the required SSH service.

## 4. Confirmed Sony transport architecture

These facts were verified against the physical camera, not inferred:

1. This ZV-E10 II uses PTP-IP inside an SSH tunnel for Access Authentication.
2. The camera exposes OpenSSH 7.9 on port 22.
3. The account rejects shell and exec channels with `Administratively prohibited`.
4. The account permits direct TCP forwarding only to the literal host string `localhost` on port `15740`.
5. `127.0.0.1` does not work. Do not normalize the host string.
6. The PTP-IP Init Command Request must include a four-byte protocol version after the UTF-16LE friendly name: `UInt16 major=1`, `UInt16 minor=0`.
7. With that field, the camera returns a valid Init Command Ack containing `ZV-E10M2`.
8. PTP `OpenSession` works.
9. Transaction ID 0 must be used for `OpenSession`. HEAD commit `4e883aa` changed the counter start from 1 to 0 and resolved the previous post-first-operation `SessionNotOpen (0x2003)` pattern.
10. The Sony SDIO three-phase initialization now proceeds far enough to discover properties and the Live View URL.

Dependency:

```kotlin
implementation("com.github.mwiede:jsch:0.2.17")
```

Use the maintained mwiede fork. The original JSch fails modern SSH negotiation against the camera.

## 5. Confirmed Live View path

The usable Live View path is HTTP through a separate SSH `direct-tcpip` channel:

1. PTP/SDIO property `0xD278` supplies the Live View URL.
2. Parse that URL.
3. Open another SSH forward to the URL port on literal `localhost`.
4. Send persistent HTTP GET with keep-alive.
5. Parse JPEG frames from the response body.

The PTP virtual-object alternative is not usable on this body over this session:

- `GetObjectInfo(0xFFFFC002)` / `GetObject(0xFFFFC002)` timed out or returned no complete packet.
- A direct diagnostic after a stable session reported no useful frame and the session became unhealthy.
- Do not switch production back to the USB-style `0xFFFFC002` route.

PTP operation `0x9209` also timed out when used as an idle heartbeat, including after waiting for a settled session. It was removed from the periodic keepalive path.

Current keepalive:

- JSch `serverAliveInterval = 10_000` ms.
- `serverAliveCountMax = 3`.
- App idle health check inspects local SSH/PTP tunnel health instead of issuing a PTP operation that can wedge the session.

## 6. Live View performance history

Chronology matters because it isolates bottlenecks:

| Implementation | Observed result | Interpretation |
|---|---:|---|
| Original byte-at-a-time/`available()` body parser | about 0.5 FPS | App transport implementation was catastrophically slow. |
| Bulk parser, still polling `available()` with 2 ms sleeps | initially 4.4 FPS; later 1.6-1.8 FPS | Better but still transport-bound. |
| Instrumented old loop | 1024x680; network about 984 ms; decode 15 ms; deterministic analysis 9 ms | Delay was overwhelmingly inside the frame read. |
| Blocking `InputStream.read(...)` body reads | 9.9-10.1 FPS; network 1-2 ms; decode 5-8 ms; analysis about 4 ms | Removed the largest self-inflicted stall. User confirmed 10 FPS. |
| Diagnostics interval changed 100 ms to 33 ms | momentary 29.5 FPS; variable about 6-26 FPS; reconnects | Camera/transport can burst near 30, but flow is unstable. |
| Latest combined build: blocking reads + 33 ms + UI coalescing + 1 MB JSch input buffer | screenshot about 19.4 FPS; net 41 ms; decode 5 ms; analysis 4 ms | Better throughput, still not usable. |
| Operator hand-wave test on latest build | sometimes more than 5 seconds lag, sometimes less | Stale frames still accumulate upstream of display. |

Latest status screenshot:

```text
C:\Users\kaila\AppData\Local\Temp\capturecam-postfix-status.png
```

Do not use the old capability audit's `about 10 fps` line as current truth. It predates the uncapped and combined builds.

## 7. What is already fixed in the current code

### `SonyPtpIpController.kt`

- Full SSH + PTP-IP transport for Access Authentication cameras.
- Correct transaction ID start at zero.
- Sony SDIO property discovery and control helpers.
- HTTP Live View via `0xD278`.
- Persistent stream and `liveViewCarry` for bytes following one JPEG.
- Body parser reads 64 KB blocks with blocking `InputStream.read(...)` instead of `available()` plus `Thread.sleep(2)`.
- Maximum JPEG size: 4 MB.
- Read timeout constant: 8 seconds.
- JSch session configuration:

```kotlin
session.setConfig("max_input_buffer_size", "1048576")
```

- SSH server-alive keepalive.
- Direct PTP virtual-frame diagnostic and exact failure reporting.
- Exposure, autofocus, zoom and shutter property/control scaffolding.
- Sony optical zoom direction corrected: `D2DD` is a signed byte; positive is tele, negative is wide.
- Tele and wide physical direction were visually confirmed on the real lens.
- `lastDisconnectReason` and `lastLiveViewDiagnostic` reporting.

### `BleDiagnosticsActivity.kt`

- Sony connection fields and connection/reconnect controls.
- Live View display and telemetry.
- Deterministic gold detector, overlay and RSC 2 servo test controls.
- Bounded automatic Sony reconnect.
- Live View desired/running state separation.
- Frame interval changed from 100 ms to 33 ms.
- Per-frame network/decode/analysis timing.
- FPS interpolation bug fixed.
- UI changed to a single pending update with `AtomicReference<SonyUiFrame?>` + `AtomicBoolean`; intermediate UI frames are overwritten.
- Screen kept awake.

### `SonyProductionCamera.kt`

- Lifecycle owner for Sony connect, preview, bounded reconnect, controls and still-capture transition.
- Sony is declared available only after a JPEG decodes.
- Phone CameraX remains fallback if Sony is unavailable.
- Production preview interval is 33 ms.
- Cadence logging.
- Proactive live-session renewal currently runs at 70 seconds.
- Fresh command sessions are used around zoom/focus/exposure/capture transitions because this body behaves as a single-session camera.
- Still capture path exists but is not physically proven.

### `MainActivity.kt`

- `SonyProductionCamera` integrated as a production camera source.
- Sony preview has a latest-wins UI update guard.
- Existing production phase machine can receive Sony frames.
- Deterministic material detection runs on Sony bitmaps.
- ML Kit QR/barcode scanner runs on Sony frames in TAG phase.
- Existing focus, zoom, exposure and two-frame capture calls dispatch to Sony or phone based on active source.
- Sony control ADB broadcast hooks added for diagnostics.
- Main activity releases Sony and RSC 2 ownership before opening diagnostics; restores on resume.
- Three-angle/gimbal workflow remains in the existing pipeline.

### Detection and gimbal files

- `MaterialDetector.kt`: deterministic Bitmap overload using the existing RGB gold classifier, texture gate, components and geometry. Reuses an ARGB buffer. No neural model/network call.
- `SharpnessAnalyzer.kt`: Bitmap sharpness scoring for Sony frames.
- `SonyGoldTargetDetector.kt`: strict deterministic target isolation and temporal/geometry checks.
- `SonyGoldServoController.kt`: bounded state machine for center, focus and zoom decisions.
- `RSC2Controller.kt`: reconnect hardening, duplicate-connect protection and more accurate Android BLE write handling.
- `BoundsOverlayView.kt`: Sony target/guide overlay support.
- `FocusZoomController.kt`: phone/Sony integration adjustments.

Full camera feature decisions and station preset are documented in:

```text
SONY_ZV_E10M2_JEWELLERY_CAPABILITY_AUDIT.md
```

## 8. Why the latest build still lags

Both production and diagnostics currently do this serially:

```text
fetch one old JPEG -> decode -> analyse/detect -> UI enqueue -> optional sleep -> fetch next old JPEG
```

Consequences:

1. The reader stops draining network data during JPEG decode, detection, servo decisions and deliberate pacing.
2. The camera/JSch/socket buffers continue accumulating frames.
3. The next fetch returns the oldest buffered complete frame, not the newest scene.
4. UI coalescing only drops frames after decode. It cannot discard stale frames still waiting in the transport.
5. Lag varies with transient stalls and buffer occupancy, explaining `sometimes 5+ seconds, sometimes less`.

The variable five-second symptom is strong evidence of a growing stale-frame backlog. It is not evidence that every network packet itself takes five seconds.

The 1 MB JSch buffer is a throughput fix, not a latency fix. Without a continuously draining reader it can hold roughly five 160-190 KB frames and increase visible age. Keep it only if the new reader continuously drains. After the pump works, compare 256 KB and 1 MB under identical tests.

Why the JSch setting helped throughput:

- JSch's channel input pipe defaults to 32 KB.
- Sony JPEGs are roughly 160-190 KB.
- JSch's direct-tcpip local SSH window is 128 KB.
- The shared SSH session reader writes channel data before it sends the next window adjustment.
- A fixed 32 KB consumer pipe can block the shared session reader repeatedly within one frame.
- `max_input_buffer_size=1048576` makes the pipe resizable and avoids that immediate blockage.

## 9. Current parser hazards

Fix or measure these while building the pump:

### Blocking read cannot currently be cancelled safely

`fetchLiveViewJpeg()` holds `liveViewLock` across `readNextLiveViewJpeg()`. `closeLiveViewHttpStream()` synchronizes on the same lock. If `input.read()` blocks forever, a stop/watchdog thread cannot acquire the lock to disconnect the channel.

Also, `readNextLiveViewJpeg()` checks the 8-second deadline only before the blocking call. The deadline cannot fire while `input.read()` itself is blocked.

Required change: one owner thread performs reads; stop/watchdog snapshots and disconnects the channel without waiting for the read-owner monitor. The resulting EOF/exception terminates the reader. Never hold the state lock during a potentially indefinite read.

### HTTP framing is not understood yet

`readHttpHeaders()` currently returns all headers, but `ensureLiveViewHttpStream()` only checks the status line and discards the rest. Log the headers once, with credentials/query secrets removed.

Determine whether Sony returns:

- `multipart/x-mixed-replace` with boundaries and per-part `Content-Length`,
- Sony LiveView Dataset framing, or
- a raw concatenated JPEG stream.

Prefer explicit length framing if present. Current code scans for `FFD8`/`FFD9`. Marker scanning adds work and can theoretically stop at an embedded JPEG/thumbnail marker. Do not rewrite framing based on a guess; inspect the actual response first.

### Per-frame allocations

Current parser allocates/grows a byte array and uses `copyOfRange` for JPEG and carry. At 30 FPS that creates avoidable garbage and GC jitter. First fix correctness/latency, then reuse buffers or a bounded pool. Do not add a multi-frame queue.

## 10. Exact next implementation

Implement a latest-only frame pump. Recommended ownership model:

```text
Sony HTTP reader thread (only stream reader)
    continuously parse every arriving frame
    increment source sequence and source counters
    AtomicReference.set(newest JPEG/sample)
    overwrite old unconsumed sample
    notify waiting consumer

Decode/detection consumer
    wait for sequence > last consumed
    take current AtomicReference sample
    decode only that latest sample
    run deterministic detector as required
    publish latest bitmap to UI
    never enqueue another sample behind it
```

Suggested controller API shape; names may vary:

```kotlin
data class LiveViewSample(
    val sequence: Long,
    val jpeg: ByteArray,
    val receivedAtNanos: Long
)

fun startLiveViewPump(): Boolean
fun awaitLatestLiveViewFrame(afterSequence: Long, timeoutMs: Long): LiveViewSample?
fun stopLiveViewPump()
```

Rules:

- Exactly one thread reads the HTTP stream.
- The reader has no 33 ms sleep. It drains at source speed.
- Storage depth is one frame. `AtomicReference.set()` replaces stale data.
- Consumer tracks sequence; never decodes the same sample twice.
- Record how many source frames were overwritten before consumption.
- UI retains its existing latest-wins coalescing.
- Diagnostics and `SonyProductionCamera` use the same pump; do not maintain two different transport implementations.
- Stop/disconnect must interrupt a blocked read by disconnecting the SSH Live View channel outside the read lock.
- A watchdog should close/reopen the HTTP channel if no complete source frame arrives within 8 seconds.
- A transient consumer stall must increase the dropped counter, not visible latency.

Do not implement only the proposed `read with a 5-8 ms deadline until no more frames` loop unless the underlying read can actually be cancelled at that deadline. Current JSch `InputStream.read()` is blocking, so a nominal deadline around it is ineffective. A permanent reader thread plus one-slot handoff is safer.

## 11. Telemetry required before claiming 30 FPS

Expose/log separate rolling two-second metrics:

```text
sourceFps       complete JPEG boundaries parsed by reader
decodedFps      samples decoded into Bitmap
renderedFps     UI frames actually rendered
droppedBeforeDecode
droppedBeforeRender
latestAgeMs     now - source receivedAtNanos for rendered frame
networkBytesPerSecond
jpegBytes p50/p95 or min/max
decodeMs p50/p95
analyseMs p50/p95
carryBytes or parser buffered bytes
reconnectCount
```

Add a diagnostic `transport only` mode that continuously parses/counts JPEGs without Bitmap decode, gold detection, QR, gimbal or UI rendering. This establishes the real camera/transport ceiling.

Do not infer 30 FPS only from a momentary label. The prior 29.5 FPS was brief and followed by large variation/reconnects.

## 12. Acceptance tests

Use this order. Automatic gimbal movement must remain Off until preview latency is proven.

### A. Transport-only ceiling

1. Connect camera.
2. Start transport-only reader for at least 60 seconds.
3. Record source FPS each two seconds, JPEG sizes, bytes/sec, timeouts and reconnects.
4. Pass target: stable source cadence near the camera stream's actual ceiling, ideally 25-30 FPS, with zero growing buffer age.

### B. Preview latency

1. Enable decode/display without gold detection or gimbal.
2. Wave a hand sharply through frame and stop.
3. Preview must show the stop almost immediately, never continue replaying motion for seconds.
4. Quantify with a high-frame-rate phone video containing both the physical motion and tablet screen, or point camera at a millisecond timer and compare displayed time.
5. Initial pass criterion: under 250 ms end-to-end continuously. Goal: under 150 ms.
6. Leave running 10 minutes; latency must not grow.

### C. Deterministic detection load

1. Enable gold detection with gimbal still Off.
2. Confirm preview remains current.
3. Confirm target box follows the real item, not yellow background/highlights.
4. Production analysis is currently throttled to 150 ms, about 6.7 analyses/sec. Diagnostics currently analyses every fetched frame. Decide deliberately; preview does not need detection at 30 Hz.

### D. Gimbal

1. Confirm RSC 2 reports ready.
2. Enable auto tracking only after A-C pass.
3. Use small bounded moves.
4. Confirm screen rotation is locked and axes remain correct.
5. Disconnect/reconnect BLE and confirm self-heal without duplicate scans or motion commands.

### E. QR/tag

1. Enter TAG phase.
2. Present QR/label at normal working distance.
3. Confirm ML Kit detects it from current Sony frames.
4. Ensure QR processing cannot queue frames or block preview.

### F. Full capture and three-angle E2E

Do this only after preview and QR pass.

1. Tag recognized.
2. Gold detected.
3. Gimbal centers item.
4. Autofocus physically verified.
5. Optical zoom reaches intended framing.
6. Full-resolution shutter physically fires and image downloads.
7. Repeat at three angles.
8. Existing stitch/composite/upload flow receives all three current item images plus tag.
9. No previous-item tag/image survives a restart/re-entry.

Full-resolution shutter/download is currently blocked. Existing commands have acknowledged but did not produce a confirmed physical capture. Do not claim E2E success until a real full-resolution file is downloaded and inspected.

## 13. Camera-control validation status

| Capability | Current status |
|---|---|
| SSH/PTP-IP connect | Physically confirmed. |
| Live View HTTP | Physically confirmed, but latency/throughput unstable. |
| Optical zoom direction | Tele and wide physically confirmed. |
| Lens fully wide | Operator visually confirmed after direction fix. |
| Granular zoom/absolute ratio | Code exists; controlled accuracy still needs physical validation. |
| Half-press autofocus | Code exists; physical focus-only validation pending. |
| Exposure compensation | Property path exists; physical/photometric validation pending. |
| ISO/white balance/focus-mode properties | Property support/scaffolding exists; do not claim all are remotely verified. |
| Full shutter/download | Blocked; no confirmed app-triggered full-resolution capture. |
| QR from Sony | Integrated in production path; live end-to-end validation pending. |
| RSC 2 pan/tilt | Previously established and code integrated; full Sony+gimbal E2E pending. |
| Three-angle catalogue flow | Existing app flow exists; Sony E2E pending. |

## 14. Connection/recovery findings

Old failure: controller disconnected itself about every 15 seconds because its idle keepalive issued `GetDeviceInfo`. Replacing that with `0x9209` also failed. Current design uses SSH keepalive/local health only.

A 35-second idle soak without PTP keepalive operations held the connection.

The camera later became completely unreachable around 32 minutes after a manual restart. Both PC and tablet lost `192.168.0.14`. CaptureCam stayed alive, selected phone fallback and retried. Manual DSLR restart restored the same IP, and CaptureCam reconnected without restarting the tablet/app. This strongly matches a camera 30-minute power-save setting, but the menu value was not directly read.

Required camera station hardwall:

```text
Power Save Start Time = Off
Power Save by Monitor = Does Not Link
Auto Monitor OFF = Does not turn OFF
USB Power Supply = On
Battery inserted
USB-power icon/indication confirmed
Auto Power OFF Temp. = High, with ventilation
Remote Shooting = On
```

`Cnct. while Power OFF` does not provide CaptureCam Remote Shooting/PTP-IP Live View control. It is for paired-phone card access/transfer while off.

Current production code also performs a proactive remote lease refresh at 70 seconds by closing HTTP, reading properties, then reopening preview. This may itself produce disruption. Do not remove it blindly. First log session age and confirm whether the body actually kills otherwise healthy HTTP/PTP sessions near 90 seconds. Test pump stability both sides of 70 seconds.

Sony appears to permit one remote command session. Rapid reinstall/reconnect attempts can hit a stale camera-side session lock. Bounded backoff eventually recovered during testing. Avoid hammering reconnect in tight loops.

## 15. Sony Creators' App clean-room reference

Creators' App is smooth on the same hardware and exposes useful controls. It proves the camera can provide a substantially better experience than the current CaptureCam implementation.

Installed package inspected:

```text
jp.co.sony.ips.portalapp
versionName: 3.4.1
targetSdk: 36
```

Pulled APK set:

```text
C:\Users\kaila\AppData\Local\Temp\sony-creators-3.4.1
```

Base extraction:

```text
C:\Users\kaila\AppData\Local\Temp\sony-creators-3.4.1\base
```

Observed resources/DEX strings:

```text
ptpip_remote_control_activity_layout.xml
canGetLiveView
canMakeHttpStreamConnection
mLiveviewUrl
```

JADX was not installed/decompilation was not completed. If needed, use a temporary read-only installation of JADX 1.5.6, document behavioral/protocol observations only, and do not copy Sony source.

Traffic-pattern comparison is also safe: compare packet sizes and burst cadence between Creators' App and CaptureCam on the same link. SSH payload is encrypted, but cadence and burst sizes still reveal whether CaptureCam is stalling its receive window.

Sony's official Creators help documents Touch Focus, Touch Tracking, Touch AE, AEL, W/T and step zoom in remote shooting. These features are design references, not proof that their private Android implementation can be reused.

## 16. Build, install and inspect

PowerShell:

```powershell
Set-Location 'C:\Users\kaila\Desktop\CaptureCam-master-checkout\CaptureCam'
$env:JAVA_HOME = 'C:\Tools\jdk-17.0.12+7'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
.\gradlew.bat lintDebug assembleDebug
& 'C:\platform-tools\adb.exe' -s 192.168.0.22:5555 install -r 'app\build\outputs\apk\debug\app-debug.apk'
```

Useful ADB commands:

```powershell
$adb = 'C:\platform-tools\adb.exe'
& $adb -s 192.168.0.22:5555 shell am start -n com.aradhana.capturecam/.BleDiagnosticsActivity
& $adb -s 192.168.0.22:5555 logcat -c
& $adb -s 192.168.0.22:5555 logcat -v time SonyPtpIp:V SonyProduction:V CaptureCam:V '*:S'
& $adb -s 192.168.0.22:5555 shell screencap -p /sdcard/capturecam.png
& $adb -s 192.168.0.22:5555 pull /sdcard/capturecam.png 'C:\Users\kaila\AppData\Local\Temp\capturecam.png'
```

Use logcat dump mode if wireless ADB becomes unstable:

```powershell
& $adb -s 192.168.0.22:5555 logcat -d -v time SonyPtpIp:V SonyProduction:V CaptureCam:V '*:S'
```

## 17. Source files to read first

Read in this order:

1. `app/src/main/java/com/aradhana/capturecam/SonyPtpIpController.kt`
2. `app/src/main/java/com/aradhana/capturecam/SonyProductionCamera.kt`
3. `app/src/main/java/com/aradhana/capturecam/BleDiagnosticsActivity.kt`
4. `app/src/main/java/com/aradhana/capturecam/MainActivity.kt`
5. `app/src/main/java/com/aradhana/capturecam/SonyGoldTargetDetector.kt`
6. `app/src/main/java/com/aradhana/capturecam/SonyGoldServoController.kt`
7. `app/src/main/java/com/aradhana/capturecam/MaterialDetector.kt`
8. `app/src/main/java/com/aradhana/capturecam/RSC2Controller.kt`
9. `SONY_ZV_E10M2_JEWELLERY_CAPABILITY_AUDIT.md`

Do not edit before reading the full current versions. The old handover predates most current functionality.

## 18. Primary-source transport references

JSch 0.2.17 source used to verify the buffer/window mechanism:

- Session channel-data handling: <https://raw.githubusercontent.com/mwiede/jsch/jsch-0.2.17/src/main/java/com/jcraft/jsch/Session.java>
- Channel input buffer configuration: <https://raw.githubusercontent.com/mwiede/jsch/jsch-0.2.17/src/main/java/com/jcraft/jsch/Channel.java>
- Direct TCP/IP channel defaults: <https://raw.githubusercontent.com/mwiede/jsch/jsch-0.2.17/src/main/java/com/jcraft/jsch/ChannelDirectTCPIP.java>

Sony references are collected in `SONY_ZV_E10M2_JEWELLERY_CAPABILITY_AUDIT.md`.

## 19. Final priority order

1. Implement one-owner latest-frame pump and cancel-safe disconnect.
2. Add source/decode/render/drop/age telemetry.
3. Measure transport-only source ceiling for 60 seconds.
4. Prove hand-wave latency stays under 250 ms for 10 minutes.
5. Inspect HTTP headers and replace marker scanning only if explicit framing is available.
6. Reduce allocations and compare 256 KB versus 1 MB JSch input buffer.
7. Validate deterministic gold detection without gimbal motion.
8. Validate RSC 2 tracking.
9. Validate QR/tag detection.
10. Fix and physically prove full-resolution shutter/download.
11. Run full tag + three-angle + upload E2E test.

No credit-burning external image generation or cloud AI is involved in this task. The immediate work is local Android/network code and physical hardware validation.
