"""
anatomical_landmarks.py — deterministic, local placement/scale anchors for
model-shoot generation, computed from MediaPipe Face Mesh / Hands landmarks
instead of trusting the generative model's own visual judgement.

Real virtual-try-on tools (GemFit, GlamTry) compute an exact attachment point
and target scale from detected landmarks BEFORE rendering, then place the
accessory there. Our pipeline previously handed the AI only a text
description ("match scale to the visible earlobe") and let it guess both
position and size — this module gives it a concrete pixel/fractional target
instead, and lets verification check the output against that same target.

MediaPipe Face Mesh's 468 points do not label the ear directly (no official
ear landmark), so the ear anchor here is a documented approximation: the
face-oval side point (234 left / 454 right) offset down by a fraction of
measured face height, which is the same approximation used across the
open-source virtual-try-on projects that don't have a dedicated ear model.
Ring/bangle anchors use MediaPipe Hands' documented finger-joint indices,
which ARE exact (no approximation needed there).
"""

import os

FACE_TOP = 10          # forehead midpoint
FACE_CHIN = 152        # chin tip
FACE_LEFT_SIDE = 234   # left cheek/jaw contour, nearest ear attachment
FACE_RIGHT_SIDE = 454  # right cheek/jaw contour, nearest ear attachment

# Fraction of measured face height the earlobe sits below the face-mesh side
# point (234/454 tracks roughly to the top of the ear, not the lobe).
_EAR_LOBE_DROP_FRAC = 0.16

# MediaPipe Hands landmark indices (documented, exact).
WRIST = 0
THUMB_CMC = 1
INDEX_MCP, INDEX_PIP = 5, 6
MIDDLE_MCP, MIDDLE_PIP = 9, 10
RING_MCP, RING_PIP = 13, 14
PINKY_MCP = 17

_FINGER_JOINTS = {
    "index":  (INDEX_MCP, INDEX_PIP),
    "middle": (MIDDLE_MCP, MIDDLE_PIP),
    "ring":   (RING_MCP, RING_PIP),
}


# MediaPipe Pose's 33-point body model (documented, exact) — used for every
# zone the face/hand models can't reach: neck, wrist, upper_arm, waist, feet.
POSE_LEFT_SHOULDER, POSE_RIGHT_SHOULDER = 11, 12
POSE_LEFT_ELBOW, POSE_RIGHT_ELBOW = 13, 14
POSE_LEFT_WRIST, POSE_RIGHT_WRIST = 15, 16
POSE_LEFT_HIP, POSE_RIGHT_HIP = 23, 24
POSE_LEFT_KNEE, POSE_RIGHT_KNEE = 25, 26
POSE_LEFT_ANKLE, POSE_RIGHT_ANKLE = 27, 28


_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mediapipe_models")
_FACE_MODEL = os.path.join(_MODEL_DIR, "face_landmarker.task")
_HAND_MODEL = os.path.join(_MODEL_DIR, "hand_landmarker.task")
_POSE_MODEL = os.path.join(_MODEL_DIR, "pose_landmarker.task")

_face_detector = None
_hand_detector = None
_pose_detector = None


def _get_face_detector():
    global _face_detector
    if _face_detector is None:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_FACE_MODEL),
            num_faces=1,
        )
        _face_detector = vision.FaceLandmarker.create_from_options(options)
    return _face_detector


def _get_hand_detector():
    global _hand_detector
    if _hand_detector is None:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_HAND_MODEL),
            num_hands=1,
        )
        _hand_detector = vision.HandLandmarker.create_from_options(options)
    return _hand_detector


def _get_pose_detector():
    global _pose_detector
    if _pose_detector is None:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_POSE_MODEL),
            num_poses=1,
        )
        _pose_detector = vision.PoseLandmarker.create_from_options(options)
    return _pose_detector


def _dist_px(lm, i, j, w, h) -> float:
    a, b = lm[i], lm[j]
    return (((a.x - b.x) * w) ** 2 + ((a.y - b.y) * h) ** 2) ** 0.5


def _midpoint_frac(lm, i, j):
    a, b = lm[i], lm[j]
    return (a.x + b.x) / 2, (a.y + b.y) / 2


# Landmarks outside the visible frame are still "detected" by MediaPipe Pose
# — it extrapolates a guessed position rather than refusing, since the model
# always outputs all 33 points. A closeup photo that doesn't actually show
# the wrist/waist/feet at all was confirmed live to return coordinates far
# outside [0,1] normalized space with low visibility scores — this is the
# real signal to reject on, not just "did detect() return landmarks".
_MIN_VISIBILITY = 0.5
_FRAC_MARGIN = 0.05  # small tolerance for a landmark right at the frame edge


def _landmark_usable(pt) -> bool:
    visibility = getattr(pt, "visibility", 1.0)
    if visibility is not None and visibility < _MIN_VISIBILITY:
        return False
    return (-_FRAC_MARGIN <= pt.x <= 1 + _FRAC_MARGIN and
            -_FRAC_MARGIN <= pt.y <= 1 + _FRAC_MARGIN)


def pose_anchor(image_path: str, zone: str) -> dict:
    """Return a deterministic body-landmark anchor for zones MediaPipe's
    face/hand models don't cover: neck, wrist, upper_arm, waist, feet.
    Uses MediaPipe Pose's 33-point body model (documented, exact landmark
    indices — no approximation, unlike the face-mesh ear anchor).

    Returns {"ok": True, "point_px", "point_frac", "reference_px", "image_size"}
    on success — reference_px is the physical ruler for that zone (shoulder
    span for neck, forearm length for wrist, upper-arm length for upper_arm,
    hip span for waist, shin length for feet), matching the same shape
    face_anchor/hand_anchor already return so callers don't need per-zone
    branching beyond picking which anchor function to call."""
    import mediapipe as mp
    mp_img = mp.Image.create_from_file(image_path)
    w, h = mp_img.width, mp_img.height

    result = _get_pose_detector().detect(mp_img)
    if not result.pose_landmarks:
        return {"ok": False, "reason": "no pose detected"}
    lm = result.pose_landmarks[0]

    required = {
        "neck": (POSE_LEFT_SHOULDER, POSE_RIGHT_SHOULDER),
        "wrist": (POSE_LEFT_ELBOW, POSE_LEFT_WRIST),
        "upper_arm": (POSE_LEFT_SHOULDER, POSE_LEFT_ELBOW),
        "waist": (POSE_LEFT_HIP, POSE_RIGHT_HIP),
        "feet": (POSE_LEFT_KNEE, POSE_LEFT_ANKLE),
    }.get(zone, ())
    if not all(_landmark_usable(lm[i]) for i in required):
        return {"ok": False, "reason": f"{zone} not visible in this photo"}

    if zone == "neck":
        fx, fy = _midpoint_frac(lm, POSE_LEFT_SHOULDER, POSE_RIGHT_SHOULDER)
        shoulder_span_px = _dist_px(lm, POSE_LEFT_SHOULDER, POSE_RIGHT_SHOULDER, w, h)
        # Nudge the point up from the shoulder midline toward the base of
        # the neck — a necklace/pendant sits above the collarbone line, not
        # exactly on it.
        fy -= 0.12 * (shoulder_span_px / w if w else 0)
        reference_px = shoulder_span_px
    elif zone == "wrist":
        fx, fy = lm[POSE_LEFT_WRIST].x, lm[POSE_LEFT_WRIST].y
        reference_px = _dist_px(lm, POSE_LEFT_ELBOW, POSE_LEFT_WRIST, w, h)
    elif zone == "upper_arm":
        fx, fy = _midpoint_frac(lm, POSE_LEFT_SHOULDER, POSE_LEFT_ELBOW)
        reference_px = _dist_px(lm, POSE_LEFT_SHOULDER, POSE_LEFT_ELBOW, w, h)
    elif zone == "waist":
        fx, fy = _midpoint_frac(lm, POSE_LEFT_HIP, POSE_RIGHT_HIP)
        reference_px = _dist_px(lm, POSE_LEFT_HIP, POSE_RIGHT_HIP, w, h)
    elif zone == "feet":
        fx, fy = lm[POSE_LEFT_ANKLE].x, lm[POSE_LEFT_ANKLE].y
        reference_px = _dist_px(lm, POSE_LEFT_KNEE, POSE_LEFT_ANKLE, w, h)
    else:
        return {"ok": False, "reason": f"pose_anchor has no rule for zone '{zone}'"}

    # A profile/side-view shot can foreshorten shoulder or hip span down to
    # a few pixels in 2D projection — technically nonzero but not a usable
    # physical ruler. 20px is well below any real measurement seen on a
    # normal reference photo (confirmed live: full-body shots measure
    # 30-100+px per zone) but well above profile-view foreshortening noise.
    if reference_px < 20:
        return {"ok": False, "reason": f"degenerate pose measurement ({reference_px:.1f}px, likely a profile/foreshortened view)"}

    return {
        "ok": True,
        "point_px": (round(fx * w, 1), round(fy * h, 1)),
        "point_frac": (round(fx, 4), round(fy, 4)),
        "reference_px": round(reference_px, 1),
        "image_size": (w, h),
    }


def face_anchor(image_path: str, side: str = "left") -> dict:
    """Return a deterministic ear-attachment anchor for earrings/tops/bali.

    Returns {"ok": True, "point_px": (x, y), "point_frac": (fx, fy),
    "face_height_px": h} on success, {"ok": False, "reason": str} otherwise.
    `side` is which ear is visible in the reference photo ("left" or "right"
    face-mesh side landmark — this is the SUBJECT's side as seen by the
    camera, i.e. "left" means the landmark near image-left).
    """
    import mediapipe as mp
    mp_img = mp.Image.create_from_file(image_path)
    w, h = mp_img.width, mp_img.height

    result = _get_face_detector().detect(mp_img)
    if not result.face_landmarks:
        return {"ok": False, "reason": "no face detected"}

    lm = result.face_landmarks[0]
    top = lm[FACE_TOP]
    chin = lm[FACE_CHIN]
    face_height_px = abs(chin.y - top.y) * h
    if face_height_px <= 1:
        return {"ok": False, "reason": "degenerate face height"}

    side_idx = FACE_LEFT_SIDE if side == "left" else FACE_RIGHT_SIDE
    anchor = lm[side_idx]
    ax, ay = anchor.x * w, anchor.y * h + _EAR_LOBE_DROP_FRAC * face_height_px

    return {
        "ok": True,
        "point_px": (round(ax, 1), round(ay, 1)),
        "point_frac": (round(ax / w, 4), round(ay / h, 4)),
        "face_height_px": round(face_height_px, 1),
        "image_size": (w, h),
    }


def hand_anchor(image_path: str, finger: str = "ring") -> dict:
    """Return a deterministic finger-joint anchor for rings, and a wrist-width
    measurement for bangles/bracelets.

    Returns {"ok": True, "point_px": (x, y), "point_frac": (fx, fy),
    "finger_width_px": w, "wrist_width_px": w} on success.
    """
    import mediapipe as mp
    mp_img = mp.Image.create_from_file(image_path)
    w, h = mp_img.width, mp_img.height

    result = _get_hand_detector().detect(mp_img)
    if not result.hand_landmarks:
        return {"ok": False, "reason": "no hand detected"}

    lm = result.hand_landmarks[0]
    mcp_idx, pip_idx = _FINGER_JOINTS.get(finger, _FINGER_JOINTS["ring"])
    mcp, pip = lm[mcp_idx], lm[pip_idx]
    fx = (mcp.x + pip.x) / 2 * w
    fy = (mcp.y + pip.y) / 2 * h
    finger_width_px = ((mcp.x - pip.x) ** 2 + (mcp.y - pip.y) ** 2) ** 0.5 * w

    wrist, thumb_cmc, pinky_mcp = lm[WRIST], lm[THUMB_CMC], lm[PINKY_MCP]
    wrist_width_px = ((thumb_cmc.x - pinky_mcp.x) ** 2 +
                      (thumb_cmc.y - pinky_mcp.y) ** 2) ** 0.5 * w

    return {
        "ok": True,
        "point_px": (round(fx, 1), round(fy, 1)),
        "point_frac": (round(fx / w, 4), round(fy / h, 4)),
        "finger_width_px": round(finger_width_px, 1),
        "wrist_width_px": round(wrist_width_px, 1),
        "image_size": (w, h),
    }


ZONE_ANCHOR_FN = {
    "face": face_anchor,
    "hand": hand_anchor,
    "neck":      lambda image_path: pose_anchor(image_path, "neck"),
    "wrist":     lambda image_path: pose_anchor(image_path, "wrist"),
    "upper_arm": lambda image_path: pose_anchor(image_path, "upper_arm"),
    "waist":     lambda image_path: pose_anchor(image_path, "waist"),
    "feet":      lambda image_path: pose_anchor(image_path, "feet"),
    # "bridal" deliberately excluded: forehead/hairline placement varies too
    # much by piece (maang tikka vs matha patti vs full headpiece) for one
    # generic anchor to be meaningful — the existing text-prompt guidance
    # stays the sole source of placement/scale for that zone.
}


def anchor_for_zone(zone: str, image_path: str, **kwargs) -> dict:
    """Dispatch to the right landmark anchor for a placement zone, or
    {"ok": False, "reason": "no anchor for this zone"} when the zone has no
    deterministic landmark support (currently just "bridal" — see
    ZONE_ANCHOR_FN's comment)."""
    fn = ZONE_ANCHOR_FN.get(zone)
    if fn is None:
        return {"ok": False, "reason": f"no deterministic anchor for zone '{zone}' yet"}
    if not os.path.exists(image_path):
        return {"ok": False, "reason": f"image not found: {image_path}"}
    try:
        return fn(image_path, **kwargs)
    except Exception as e:
        return {"ok": False, "reason": f"landmark detection error: {e}"}
