package com.aradhana.capturecam

import org.opencv.core.Mat
import kotlin.math.abs

enum class VisionState { SEARCHING, ACQUIRING, TRACKING, APPROACHING, FRAMING, LOCKED, PREDICTING, REACQUIRING }

/**
 * Single control authority for the DINO(laptop)+MIL(phone) tracking pipeline.
 * Owns all state and all servo decisions; MainActivity only feeds inputs in
 * (DINO results via onDinoDetection, camera frames via onCameraFrame) and
 * executes the ServoCommand this class hands back. No other code path may
 * issue a pan/tilt/zoom command while a target is tracked -- MainActivity is
 * expected to gate its legacy gold-hunt motion on `state == SEARCHING`.
 *
 * Threading: onDinoDetection only ever writes the @Volatile `pending*`
 * fields (it's called from the DetectorClient's OkHttp callback thread).
 * All state transitions and Mat access happen inside onCameraFrame, which
 * the caller must always invoke from the same thread (the camera analyzer
 * thread) -- that's what makes `state` itself safe without extra locking.
 */
class VisionServoController(private val log: (String) -> Unit) {

    data class ServoCommand(
        val pan: Float,       // -1..1 proportional command, 0 = hold
        val tilt: Float,      // -1..1
        val zoomStep: Float,  // +/- fractional step this tick, 0 = hold
        val state: VisionState,
        val centered: Boolean,
        val framed: Boolean,
        val targetCx: Float,
        val targetCy: Float,
    )

    /** Hard off for the physical tracking checkpoint -- reaching LOCKED
     * only logs "CAPTURE WOULD FIRE", never actually calls a shutter. */
    var shutterEnabled = false

    var state: VisionState = VisionState.SEARCHING
        private set

    private val tracker = JewelleryTracker()

    @Volatile private var pendingDino: NormalizedBox? = null
    @Volatile private var pendingDinoAgeMs: Long = 0
    @Volatile private var pendingDinoFrameId: Long = -1
    private var lastAppliedDinoFrameId = -1L

    private var trackedBox: NormalizedBox? = null
    private var reacquiringSinceMs = 0L
    private var lastServoLogMs = 0L
    private var lockLoggedOnce = false
    // The most recent DINO box that disagreed with a live MIL track but
    // wasn't yet acted on -- cleared on agreement/reseed/state-reset, only
    // ever compared against the NEXT disagreeing DINO result (see
    // applyDinoResult's TRACKING branch doc comment).
    private var pendingDisagreement: NormalizedBox? = null

    fun reset() {
        tracker.reset()
        state = VisionState.SEARCHING
        pendingDino = null
        trackedBox = null
        lockLoggedOnce = false
        pendingDisagreement = null
        log("[STATE] -> SEARCHING (reset)")
    }

    /** Called from the DetectorClient callback (any thread). Validates
     * staleness and stores the result; no motor calls, no Mat access. */
    fun onDinoDetection(frameId: Int, ageMs: Long, box: NormalizedBox?) {
        if (box == null) return
        if (ageMs > STALE_DISCARD_MS) {
            log("[STALE] dropping DINO frame=$frameId age=${ageMs}ms (>${STALE_DISCARD_MS}ms)")
            return
        }
        pendingDino = box
        pendingDinoAgeMs = ageMs
        pendingDinoFrameId = frameId.toLong()
        log("[DINO] frame=$frameId age=${ageMs}ms box=${fmt(box)}")
    }

    /** Called once per suitable analysis frame with an upright Mat (any
     * pixel format TrackerMIL accepts). Runs MIL, fuses any pending DINO
     * result, advances the state machine, and returns what to physically
     * do this tick (null if nothing should move). This is the ONLY place
     * that produces a servo output. */
    fun onCameraFrame(mat: Mat, nowMs: Long): ServoCommand? {
        val dino = pendingDino
        if (dino != null && pendingDinoFrameId != lastAppliedDinoFrameId) {
            lastAppliedDinoFrameId = pendingDinoFrameId
            applyDinoResult(mat, dino)
        }

        if (tracker.isTracking) {
            val result = tracker.update(mat)
            if (result == null) {
                onTrackerLost(nowMs)
            } else {
                trackedBox = NormalizedBox.fromCenterSize(result.cx, result.cy, result.w, result.h)
                log("[MIL] cx=${"%.2f".format(result.cx)} cy=${"%.2f".format(result.cy)} " +
                    "w=${"%.2f".format(result.w)} h=${"%.2f".format(result.h)} predicted=${result.predicted}")
                onTrackerFrame(result.predicted, nowMs)
            }
        }

        if (state == VisionState.REACQUIRING && nowMs - reacquiringSinceMs > REACQUIRE_TIMEOUT_MS) {
            log("[STATE] REACQUIRING -> SEARCHING (timeout, no recovery)")
            state = VisionState.SEARCHING
            trackedBox = null
        }

        return computeServo(nowMs)
    }

    private fun applyDinoResult(mat: Mat, dino: NormalizedBox) {
        when (state) {
            VisionState.SEARCHING, VisionState.ACQUIRING -> {
                tracker.seed(mat, dino.toRectF())
                trackedBox = dino
                pendingDisagreement = null
                log("[STATE] SEARCHING -> ACQUIRING")
                log("[MIL] seeded")
                // MIL is live the instant init() returns -- there is no
                // separate "second measurement" to wait for, so ACQUIRING
                // has no distinct hold frame of its own.
                state = VisionState.TRACKING
                log("[STATE] ACQUIRING -> TRACKING")
            }
            VisionState.TRACKING, VisionState.APPROACHING, VisionState.FRAMING, VisionState.LOCKED -> {
                val current = trackedBox
                if (current == null) {
                    tracker.seed(mat, dino.toRectF())
                    log("[RESEED] no current box -- seeding from DINO")
                    return
                }
                val iou = current.iou(dino)
                val dist = current.centerDist(dino)
                when {
                    iou >= AGREEMENT_IOU_GOOD || dist <= AGREEMENT_DIST_GOOD -> {
                        log("[DINO] agrees with MIL (iou=${"%.2f".format(iou)} dist=${"%.2f".format(dist)}) -- no reseed")
                        pendingDisagreement = null
                    }
                    iou >= AGREEMENT_IOU_MODERATE || dist <= AGREEMENT_DIST_MODERATE -> {
                        tracker.seed(mat, dino.toRectF())
                        log("[RESEED] moderate drift (iou=${"%.2f".format(iou)}) -- reseeding from DINO")
                        pendingDisagreement = null
                    }
                    else -> {
                        // One bad DINO box must not violently redirect an
                        // already-good MIL lock -- but MIL can also drift
                        // onto the wrong (static) patch while still
                        // reporting update()=true every frame, which never
                        // trips consecutiveMisses/PREDICTING at all. Two
                        // independent DINO results that disagree with MIL
                        // but AGREE WITH EACH OTHER is the confirmation
                        // signal that it's MIL that's wrong, not one noisy
                        // DINO box -- accept the reseed in that case even
                        // though MIL never technically "failed".
                        val prior = pendingDisagreement
                        if (prior != null && (prior.iou(dino) >= AGREEMENT_IOU_MODERATE || prior.centerDist(dino) <= AGREEMENT_DIST_MODERATE)) {
                            tracker.seed(mat, dino.toRectF())
                            log("[RESEED] two independent DINO detections agree (iou=${"%.2f".format(prior.iou(dino))}) " +
                                "and disagree with MIL -- MIL likely drifted, reseeding")
                            pendingDisagreement = null
                        } else {
                            log("[DINO] large disagreement (iou=${"%.2f".format(iou)} dist=${"%.2f".format(dist)}) with live MIL -- awaiting confirmation")
                            pendingDisagreement = dino
                        }
                    }
                }
            }
            VisionState.PREDICTING -> {
                tracker.seed(mat, dino.toRectF())
                pendingDisagreement = null
                state = VisionState.TRACKING
                log("[STATE] PREDICTING -> TRACKING (DINO reseed)")
                log("[RESEED] from PREDICTING")
            }
            VisionState.REACQUIRING -> {
                tracker.seed(mat, dino.toRectF())
                pendingDisagreement = null
                state = VisionState.TRACKING
                log("[STATE] REACQUIRING -> TRACKING (DINO reacquired)")
                log("[RESEED] from REACQUIRING")
            }
        }
    }

    private fun onTrackerFrame(predicted: Boolean, nowMs: Long) {
        if (predicted) {
            if (state == VisionState.TRACKING || state == VisionState.APPROACHING ||
                state == VisionState.FRAMING || state == VisionState.LOCKED
            ) {
                state = VisionState.PREDICTING
                log("[STATE] -> PREDICTING (MIL miss, bridging)")
            }
        } else if (state == VisionState.PREDICTING) {
            state = VisionState.TRACKING
            log("[STATE] PREDICTING -> TRACKING (MIL recovered)")
        }
    }

    private fun onTrackerLost(nowMs: Long) {
        log("[LOSS] tracker genuinely lost (exceeded MIL miss budget)")
        if (state != VisionState.SEARCHING && state != VisionState.REACQUIRING) {
            state = VisionState.REACQUIRING
            reacquiringSinceMs = nowMs
            log("[STATE] -> REACQUIRING (tracker lost)")
        }
        trackedBox = null
    }

    private fun computeServo(nowMs: Long): ServoCommand? {
        if (state == VisionState.SEARCHING || state == VisionState.REACQUIRING) return null
        val box = trackedBox ?: return null

        val ex = box.cx - 0.5f
        val ey = box.cy - 0.5f
        val occupancy = (box.w * box.h).coerceIn(0f, 1f)
        val centered = abs(ex) <= CENTER_DEADBAND && abs(ey) <= CENTER_DEADBAND
        val framed = occupancy >= CAPTURE_MIN_OCCUPANCY - ZOOM_DEADBAND

        // PREDICTING is a bridging sub-state of an active track -- don't
        // let framing progress overwrite it; the caller cares that MIL is
        // currently unconfirmed more than it cares about geometry this tick.
        if (state != VisionState.PREDICTING) {
            state = when {
                centered && framed -> VisionState.LOCKED
                centered -> VisionState.FRAMING
                else -> VisionState.APPROACHING
            }
        }

        val pan = nonlinearCommand(ex)
        val tilt = nonlinearCommand(-ey)
        val zoomStep = when {
            occupancy < CAPTURE_MIN_OCCUPANCY - ZOOM_DEADBAND -> ZOOM_STEP
            occupancy > CAPTURE_MIN_OCCUPANCY + ZOOM_DEADBAND -> -ZOOM_STEP
            else -> 0f
        }

        if (nowMs - lastServoLogMs > SERVO_LOG_INTERVAL_MS) {
            lastServoLogMs = nowMs
            log("[SERVO] ex=${"%.2f".format(ex)} ey=${"%.2f".format(ey)} size=${"%.2f".format(occupancy)} state=$state")
            if (pan != 0f) log("[PAN] ${"%+.2f".format(pan)}")
            if (tilt != 0f) log("[TILT] ${"%+.2f".format(tilt)}")
            if (zoomStep != 0f) log("[ZOOM] step=${"%+.3f".format(zoomStep)}")
        }
        if (state == VisionState.LOCKED) {
            if (!lockLoggedOnce) {
                lockLoggedOnce = true
                log("[LOCK] TRACK LOCKED CENTER=OK FRAME=OK -- CAPTURE WOULD FIRE (shutterEnabled=$shutterEnabled)")
            }
        } else {
            lockLoggedOnce = false
        }

        return ServoCommand(pan, tilt, zoomStep, state, centered, framed, box.cx, box.cy)
    }

    /** sign(error) x nonlinearMagnitude(error) -- large errors get close to
     * full configured speed, small errors taper fast toward zero at the
     * dead-zone edge. Absolute speeds are tuned against the physical RSC2,
     * not derived theoretically -- MIN_SERVO_MAGNITUDE/the curve shape are
     * the only knobs here. */
    private fun nonlinearCommand(error: Float): Float {
        val mag = abs(error)
        if (mag < CENTER_DEADBAND) return 0f
        val scaled = ((mag - CENTER_DEADBAND) / (0.5f - CENTER_DEADBAND)).coerceIn(0f, 1f)
        val magnitude = MIN_SERVO_MAGNITUDE + scaled * scaled * (1f - MIN_SERVO_MAGNITUDE)
        return if (error > 0) magnitude else -magnitude
    }

    private fun fmt(b: NormalizedBox) =
        "${"%.2f".format(b.cx)},${"%.2f".format(b.cy)},${"%.2f".format(b.w)},${"%.2f".format(b.h)}"

    companion object {
        // Measured against the real pipeline (RTX 5070, warm Grounding
        // DINO): server_latency alone runs ~350-400ms, plus JPEG encode +
        // network -- observed round-trip age 440-550ms. 300ms was an
        // unmeasured design-discussion number and discarded EVERY real
        // detection outright. 900ms gives margin above the observed ceiling
        // while still rejecting a truly hung/backed-up response -- DINO is
        // the periodic corrector here, not the per-frame loop (MIL owns
        // that), so this budget is intentionally generous.
        const val STALE_DISCARD_MS = 900L
        const val CENTER_DEADBAND = 0.04f
        const val ZOOM_DEADBAND = 0.05f
        const val CAPTURE_MIN_OCCUPANCY = 0.75f
        const val ZOOM_STEP = 0.05f
        const val REACQUIRE_TIMEOUT_MS = 4000L
        const val AGREEMENT_IOU_GOOD = 0.5f
        const val AGREEMENT_DIST_GOOD = 0.06f
        const val AGREEMENT_IOU_MODERATE = 0.15f
        const val AGREEMENT_DIST_MODERATE = 0.18f
        const val MIN_SERVO_MAGNITUDE = 0.15f
        const val SERVO_LOG_INTERVAL_MS = 400L
    }
}
