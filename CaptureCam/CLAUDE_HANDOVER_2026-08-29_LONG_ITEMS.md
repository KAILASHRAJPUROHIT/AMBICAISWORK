# Handover: Long-item (NECK_CURVE) capture — 2026-08-29

**Branch:** `codex/sony-production-2026-08-25`
**Latest commit:** `4480f6c` (pushed to both `origin` and `personal`)
**Status:** Long items (chains, mangalsutras, malas) still do not reliably
reach a successful auto-capture. Multiple real bugs were found and fixed
today, each one uncovering the next. The session is being handed to Codex
because progress has been real but slow, and a fresh set of eyes / a
different approach may close this out faster than continuing to iterate
one live-test at a time.

## Context you need first

- Physical rig: Sony ZV-E10 II on a robotic pan/tilt/zoom stand (RSC2
  gimbal over BLE + Sony PTP/SSH), controlled by this Android app
  (`com.aradhana.capturecam`). "Long items" are jewellery hung from
  `Mount.TOP_RAIL` — chains, mangalsutras, "MS LONG"-style malas — which
  drape **vertically down** from a rail, unlike most other categories
  (rings, studs, pendants) which sit compact and are photographed head-on.
- The composition/shape reference data (`CaptureCompositionProfile.kt`,
  `CategoryOrientation.kt`) originally came from `category_orientation.py`
  in the **desktop** JewelleryCatalogTool, which assumes items are laid
  flat on a table. That assumption is wrong for this rig's TOP_RAIL mount
  and was the source of several early bugs today (see below).
- Earlier today (separate incident, now resolved): another Claude session
  deleted the working-tree folder mid-merge. It was a git **worktree** of
  the `JewelleryCatalogTool` repo, so the committed history (up to
  `9edb52f`) survived; everything after that had to be reconstructed from
  this conversation's own record and re-applied. That reconstruction is
  believed complete and is reflected in the commits below.

## Everything fixed today, in order (all on this branch, all pushed)

1. **`9edb52f`** (survived the deletion) — exposure alignment with
   production, upload-rejection review UI, non-crashing category-count
   check, live FPS graph, PTP bulk-transfer logging throttle,
   angle1/angle2 capture overlap, Sony camera IP auto-discovery
   (`SonyCameraDiscovery.kt`).
2. **Tag-scan OCR removal** (folded into later commits) — running OCR in
   parallel with barcode scanning on every tag-phase frame was costing
   ~40ms/frame for zero benefit (OCR results were never used for
   acceptance). Reverted to barcode-only. Confirmed live: per-scan cost
   dropped from ~51ms to ~10-20ms.
3. **`82bed35`** — updated a stale default camera-IP seed constant
   (`.14` → `.20`); cosmetic, not a functional bug (discovery already
   handled the real case).
4. **Category-resolution timeout hardwall** — `UploadClient`'s
   category/stud-flag lookups were reusing the main HTTP client's
   multi-minute upload timeouts, so a slow/unresponsive
   `capture_server.py` could leave the operator stuck on "Checking tag
   category…" for up to 8 minutes. Added a separate `metadataClient` with
   6-8s timeouts.
5. **DNS/server-IP hardwall** — `UploadClient`'s custom `Dns` override
   **always** hardcoded `ARADHANA.local` → `192.168.0.3`/`.7`, skipping
   real mDNS resolution entirely. The laptop running `capture_server.py`
   had since moved to `.12`. Fixed to try mDNS first, then a
   `ServerDiscovery` subnet sweep (new file, mirrors
   `SonyCameraDiscovery`'s pattern — probes `/api/heartbeat` for the
   `capture_version` key), then the stale hardcoded pair as last resort.
6. **FPS graph drift fix** — was sampling the Sony camera's raw
   frame-**arrival** rate (inherently jittery — shutter-speed-linked, network
   bursts) instead of the actual on-screen render loop's own fixed-cadence
   tick. Rewired to sample the render loop itself (`postAtTime`-scheduled,
   drift-free), so the graph now reflects what the operator actually sees.
7. **`f5bf09c`, `6856c6f`, `73ce8e6`, `a1781e8`, `ee34095`, `59484da`,
   `4480f6c`** — see the detailed timeline below. This is where the real,
   still-unresolved work is.

## The long-item saga, in detail

### Bug A — wrong shape/size reference data (FIXED, `CaptureCompositionProfile.kt` / `CategoryOrientation.kt`)
The desktop tool's "laid flat on a table" convention gave `ms_long_22` (and
siblings `chain_22`, `fancy_mala_18/22`, `haar_chain_22`, `mss_short_20/22`,
`necklace_22`) a **wide** target aspect (1.3-1.7, width > height). On this
rig, a TOP_RAIL item hangs and reads **tall** (measured live: ratio
~0.25-0.29, not the ~0.67 a naive reciprocal-inversion guess predicted).
Corrected using directly-measured data (162 live samples). This fix is
solid — confirmed via logcat that the aspect gate stopped firing false
rejections.

### Bug B — zoom-climb vs. follow-gold oscillation (FIXED)
The normal per-item zoom-climb (chase 75% frame-area occupancy) fought a
newly-added "follow the gold, zoom out if off-center/edge-clipped" rule:
climb pushes zoom in, follow-gold reads the resulting edge-proximity and
pulls back out, forever. Fixed by having `isLongItemCategory` categories
skip the climb entirely and pin near the zoom floor instead
(`longItemTargetZoom = zoomRange.start * 1.2f`, not the absolute floor —
see Bug F).

### Bug C — chain-extension fix landed in the wrong function (FOUND AND FIXED, `MaterialDetector.kt`)
**This one is embarrassing and worth flagging loudly for Codex.**
`MaterialDetector.kt` has **two nearly-identical connected-component blob
algorithms** — one for the phone camera (`analyse(image: ImageProxy, ...)`,
line ~287) and one for Sony's decoded live-view bitmaps
(`analyse(bitmap: Bitmap, ...)`, line ~635). `analyseSonyJewelFrame` in
`MainActivity.kt` calls the **Bitmap** overload exclusively. Every
"chain-strap extension" edit made earlier in the day had been applied to
the **ImageProxy** overload — dead code for this app's actual camera path.
The real, live-observed instability (bounds flickering between "sees the
whole necklace" and "sees only the dense center") was the **unmodified**
Bitmap function's own raw 8-connectivity noise the entire time. **If you
touch blob detection again, double check which of the two `analyse()`
overloads you're actually in.**

Once found, the extension logic was ported to the correct function, with a
fix to its own internal bug too: the gap tolerance was originally computed
as a fraction of the union box's *own currently-grown size* — a
self-referential, bistable design (whether a borderline component gets
absorbed on one tick can depend on whether it was absorbed on the
*previous* tick). Changed to a fixed, frame-relative tolerance
(`0.12f * max(cols, rows)`) that can't create that feedback loop.

### Bug D — category-anchored box replaced empirical detection wholesale (FIXED, then refined)
To reduce dependence on the still-imperfect blob-linking, a "category
anchor" was added: `MaterialDetector.Result.primaryBounds` now exposes the
dense-cluster component *before* any strap-linking is attempted (this part
is genuinely stable tick-to-tick). `categoryAnchoredResult()` in
`MainActivity.kt` uses it plus the category's known target shape as a
fallback box.

First version used `Profile.targetFrame()` — a function meant for an
on-screen "aim for this" **composition guide overlay**, not a real-time
size estimate. For `ms_long_22` that works out to ~82% of frame height.
Anchoring a box that tall to the pendant's position pushed the computed
center well above the necklace's real on-screen position — live-confirmed
as "way too high". Fixed (`a1781e8`) to: (a) only intervene when raw
bounds looks genuinely partial (barely bigger than the anchor itself, not
just "different from ideal"), and (b) cap the synthesized height to
`TARGET_HEIGHT_CAP = 0.65f`, a value read off real logged full-necklace
detections, not the aspirational guide value.

**This whole approach (box-anchor-to-known-shape) may be the wrong level
of abstraction.** See "Where we're stuck" below.

### Bug E — capture was mathematically impossible for ANY long-item category (FOUND AND FIXED, `a1781e8`)
This is probably the single most important finding today.
`meetsHardCaptureRules()` — the final hard gate before a shutter fires —
required `occupancy >= CAPTURE_MIN_OCCUPANCY` (**0.75**, i.e. 75% of frame
area), with only one escape hatch: being stuck at the zoom **ceiling**.
Every NECK_CURVE category's own `CaptureCompositionProfile.targetArea`
sits at **0.52-0.58** — the system's own data said correct framing is
~55%, which can mathematically never reach 75%, and long items pin near
the zoom **floor**, so the ceiling escape hatch never applied either.

**This means literally no long-item capture could ever have succeeded,
regardless of how good tracking/AF/centering became**, from whenever this
constant was introduced until this fix. Fixed by making the occupancy
floor category-aware (`captureOccupancyFloor()`, uses
`min(0.75, categoryTargetArea * 0.85)` when a lower category target
exists). **If long items still won't capture after everything else is
fixed, re-verify this gate specifically — it's exactly the kind of
"looks fine, silently blocks everything" bug that's easy to reintroduce.**

### Bug F — one-sided zoom-floor tolerance silently no-op'd its own fix (FOUND AND FIXED, `59484da`)
After Bug B's fix pinned long items to `longItemTargetZoom` (a small margin
above the absolute floor, meant to give AF more resolution/contrast to
work with), the tolerance check `atZoomFloor = zoom <= longItemTargetZoom + 0.05f`
was **one-sided**: with target=1.2x, it accepted the *true* floor (1.0x)
as "already at target" too (1.0 ≤ 1.25), so the zoom-in-to-1.2x step never
fired at all. Operator observed live: zoom sitting at 1.0x with visible
room to zoom in that the app wasn't using. Fixed to a symmetric
`abs(zoom - target) <= 0.05f` check.

### Bug G — exposure never reset between items (FOUND AND FIXED, `ee34095`)
`resetForNewItem()` resets essentially every per-item exposure-cycle field
(`exposureClipStreak`, `exposureClearStreak`, `manualExposureOverride`)
**except the actual accumulated EV value**. Confirmed live: EV had
crashed to **-3.00** (near its -4.0 floor) during one item's tracking; that
darkness carried into the *next* item, making it too dark for
`MaterialDetector` to find reliably (`"Tracking ornament — reacquiring…"`
indefinitely). Worse: `applyAutoExposure()` only runs once coverage is
*already* trustworthy, so once dark enough to prevent detection, there was
no path back to a usable brightness — a genuine chicken-and-egg deadlock.
Fixed by calling `queueAutoExposure(0f)` (not a direct field assignment —
that would desync the app's belief from the camera's real hardware state)
on every new-item transition. **The core exposure correction algorithm
itself was deliberately left untouched** — the user stated early in this
session that its existing behavior is proven/correct for the general
case; this fix only ensures each new item starts its own cycle from
neutral, matching what every other per-item field already does.

**This bug is NOT long-item-specific** — it could affect any category if
the same leftover-darkness condition occurs. Worth specifically
re-verifying on a compact category (ring/stud) too, not just long items.

### Bug H — box tracking is the wrong representation for a curved item (ACKNOWLEDGED, PARTIALLY ADDRESSED, UNTESTED)
Operator's own diagnosis, and it's correct: a rectangular bounding box is
a poor fit for a long, curved, draped shape — its area/center are both
distorted by however much empty space the box pads around the curve. This
is arguably the root cause underlying Bugs C, D, and part of E (occupancy
math built on box area is close to meaningless for a shape this far from
rectangular).

**Only a small first step was taken before hand-off** (commit `4480f6c`,
**compiles clean, NOT live-tested**): `smoothedCenter()` now computes a
**flow centroid** — the plain average position of every classified gold
point in `MaterialDetector.Result.points` — instead of a box's geometric
center, for NECK_CURVE categories. This feeds both gimbal centering and AF
targeting (both already routed through `smoothedCenter()`). This is a
real, defensible improvement in principle (the point cloud is a strictly
richer signal than a box), but it has had **zero live verification** — it
was written and committed in the same turn the user asked for a handover.

## Where we're actually stuck

The proximate symptom at hand-off: the necklace's current framing looked
visually close to correct on-screen (operator's own words: "what it
expects and what is placed is exactly similar, it just needs to move left
a bit and align... has room for zoom in"), auto-tracking was not making
that small correction on its own, and capture had still not fired. Bug F
(zoom-floor tolerance) was found and fixed in direct response to the
"room to zoom in" half of that report; the flow-centroid change (Bug H)
was in response to the "wrong tracking method" comment but is unverified.

**What is NOT yet confirmed:**
- Whether Bug F's fix actually gets zoom to the intended 1.2x margin now.
- Whether the flow-centroid change actually improves — or accidentally
  regresses — centering accuracy and stability (it changes what
  `smoothedCenter()` returns for every consumer: gimbal nudges, AF
  targeting, `isCenteredNow()`, `isRoughlyCenteredForZoom()`, and the
  `meetsHardCaptureRules()` centering check, all at once, for every
  NECK_CURVE category).
- Whether, with all of the above in place, a long item can actually
  complete a full `HOLDING(3/3)` → `captureJewel()` cycle end-to-end.
  **This has not yet been observed to happen even once, on any long-item
  category, all session.**

**Suspected but not confirmed root causes still worth investigating:**
- The flow-centroid approach may itself need refinement — e.g. weighting
  points by local density, or excluding the sparse/noisy tail ends of a
  chain strap, rather than a flat unweighted average of every gold point
  (which a stray reflection elsewhere in `points` could still skew).
- `categoryAnchoredResult()`'s fallback (Bug D) and the flow centroid (Bug
  H) are two different, not-fully-reconciled ideas about "what is this
  item's true position/extent" now both active simultaneously for
  NECK_CURVE categories — `bounds` (box, possibly anchor-corrected) drives
  `coverage`/occupancy math, while `smoothedCenter()` (flow) now drives
  positioning. It is not verified that these two signals agree with each
  other, or that having them disagree is harmless.
- Coverage/occupancy (`meetsHardCaptureRules()`, Bug E's fix) still reads
  from box **area** (`bounds.area()` / ML box), not from any
  density/point-count-based "real flow coverage" metric. If the operator's
  "box is the wrong method" critique is taken to its logical conclusion,
  this should probably also change to a points-based metric (e.g.
  `Result.goldRatio`, which is already a full-frame-normalized point
  density independent of box shape) — this was proposed in conversation
  but **not implemented**.
- Root cause of the original EV crash to -3.00 (Bug G's *trigger*, not
  just its lack of recovery) was never identified. Something drove
  exposure down hard during a long-item tracking attempt — possibly the
  ring-light exclusion (`RING_LIGHT_EXCLUDE_TOP_FRACTION`, currently 0.04)
  isn't sufficient, or the scene genuinely has a bright element in frame
  during long-item framing that isn't present for compact categories.
  Worth checking `sceneClipFraction` values in logcat next time this
  happens, before it's masked by the new per-item reset.

## Suggested next steps for Codex

1. Live-test the current `4480f6c` build as-is first, before changing
   anything else — it's the first point where every known structural bug
   (A through G) is fixed, so it's the first real chance to see how far
   the remaining behavior actually gets.
2. Watch logcat for `tickJewel`, `centering nudge`, `AF request`, and
   `wrongShape`/`edgeClipped` lines specifically — this is how every
   finding above was actually confirmed, not guessed. Screenshots of the
   live framing alongside logcat timestamps were essential for diagnosing
   Bugs D and F.
3. If the flow centroid (Bug H) makes things worse, it's a clean, isolated
   revert (`git revert 4480f6c` or hand-edit `smoothedCenter()` back) —
   it's the last commit and touches only that one function.
4. Seriously consider extending "flow, not box" to the occupancy/coverage
   metric too (see the bullet above under Bug H) — the operator's
   framing-is-wrong-method critique likely applies there at least as much
   as to centering.
5. `RING_LIGHT_EXCLUDE_TOP_FRACTION` (0.04) and `TARGET_HEIGHT_CAP` (0.65)
   are both values read off a small number of live observations, not
   rigorously derived — treat them as starting points, not settled
   constants.
