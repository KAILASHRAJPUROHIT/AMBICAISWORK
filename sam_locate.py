"""
sam_locate.py — object-level ornament localisation with SAM2.

WHY THIS EXISTS
---------------
Everything else in this repo localises the ornament by COLOUR and TEXTURE.
That works on black velvet and fails everywhere else, and it fails silently:

  - beige leather display card measures S~96 with a warm hue -> scores as gold
  - skin is warm, moderately saturated, and has fingerprint texture -> scores
    as gold on both the colour gate AND the texture gate

Both were reported "clean" by the QA metrics while the output visibly
contained a hand or a card. No threshold separates them, because the signal
itself is wrong: warm-and-textured is not a definition of jewellery.

SAM2 segments by objectness. It does not care that skin and gold share a hue,
so it draws the boundary where the object actually ends.

WHY LOCALISATION IS THE PRIZE
-----------------------------
Measured this session: feeding Klein a tight 11.7% crop instead of the full
plate transformed output fidelity — the fringe rendered as real beaded chains
rather than flat ribs, and the medallion's enamel rosette appeared correctly.
Variant C's own crop policy always required this; nothing was producing the
crop, so the full plate was being uploaded every time.

So a reliable tight crop is the highest-value fix available, and reliable
localisation is what unlocks it.

NOTE: sam2 the PACKAGE was already installed, but with configs and no
checkpoint, so nothing using it could ever have run. The weights are now at
models/sam2/.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(BASE, "models", "sam2", "sam2.1_hiera_large.pt")
CFG = "configs/sam2.1/sam2.1_hiera_l.yaml"

_pred = None
# Mask of the last located piece, kept so tight_crop can derive the tilt from
# SAM2's own boundary instead of re-deriving one from colour.
_last_mask = None
# One mask per box in the most recent locate() call, same order as its
# returned boxes -- added 2026-08-19 so the side-by-side (expect>1) crop
# path can background-remove EACH piece individually using its own mask,
# instead of only the single-piece path having a mask to work with.
_last_masks: list = []


def available() -> bool:
    """Fail-open: only claim availability when BOTH SAM2's checkpoint is on
    disk and Grounding DINO's library is importable. If DINO can't load, the
    seeding step has nothing to seed with, so a capture should proceed with
    its original uncropped photo rather than block on this."""
    return os.path.isfile(CKPT) and _dino_available()


def release() -> None:
    """Drop SAM2 off the GPU and hand the VRAM back.

    Also clears _last_mask: it belongs to the predictor that is going away,
    and a stale mask outliving its model is how tight_crop would derive a
    tilt from the wrong piece.
    """
    global _pred, _last_mask
    if _pred is None:
        return
    _pred = None
    _last_mask = None
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _predictor():
    global _pred
    if _pred is not None:
        return _pred
    import torch
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_sam2(CFG, CKPT, device=dev)
    _pred = SAM2ImagePredictor(model)
    return _pred


def focus_boxes(bgr: np.ndarray, expect: int, pct: float = 99.0) -> list:
    """Locate the ornament by FOCUS rather than colour.

    On these 25MP shop plates the piece is shot close with a shallow depth of
    field, which leaves a signal nothing else in the frame has: it is the only
    SHARP thing. The black velvet stand is smooth, and the shop interior
    behind it is thrown well out of focus.

    That matters because every other cue failed on this category. Gold-ness
    picked the warm blurred background; texture picked velvet nap and bokeh;
    SAM2 on a point prompt picked the stand, which is genuinely the largest
    coherent object present. Sharpness is orthogonal to all three.

    Work is done on a downscaled copy — focus is a low-frequency property of
    the image and 25MP is pointless here — then boxes are mapped back to full
    resolution, where the detail actually lives.
    """
    H, W = bgr.shape[:2]
    scale = 900.0 / max(H, W)
    small = cv2.resize(bgr, (int(W * scale), int(H * scale)),
                       interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    lap = np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3))
    energy = cv2.GaussianBlur(lap, (0, 0), 9)

    thr = float(np.percentile(energy, pct))
    if thr <= 1e-3:
        return []
    m = (energy >= thr).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return []
    ranked = sorted(((stats[i, cv2.CC_STAT_AREA], i) for i in range(1, n)),
                    reverse=True)
    biggest = ranked[0][0]
    keep = [i for a, i in ranked[:expect] if a >= 0.15 * biggest]

    # Sharp is necessary but not sufficient: a printed QR tag and a specular
    # highlight on the stand are both sharp. Metal content is the second
    # requirement — and it is safe here because it is only ranking a few
    # already-localised candidates, not drawing a boundary.
    hsv_s = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv_s[..., 0], hsv_s[..., 1], hsv_s[..., 2]
    warm = ((hue >= 5) & (hue <= 45) & (sat >= 60) & (val >= 60))
    bright = (val >= 150) & (sat < 60)          # pavé / white stones
    metal = warm | bright

    inv = 1.0 / scale
    scored = []
    for i in keep:
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        comp = (lab[y:y + h, x:x + w] == i)
        area = float(comp.sum())
        if area < 20:
            continue
        mf = float((comp & metal[y:y + h, x:x + w]).sum()) / area
        if mf < 0.25:                            # tag, cloth, bare highlight
            continue
        pad = int(0.12 * max(w, h))
        scored.append((mf, [
            int(max(0, (x - pad) * inv)), int(max(0, (y - pad) * inv)),
            int(min(W, (x + w + pad) * inv)), int(min(H, (y + h + pad) * inv))]))

    scored.sort(key=lambda t: -t[0])
    boxes = [b for _, b in scored[:expect]]
    boxes.sort(key=lambda b: b[0])
    return boxes


_DINO_PROMPT = "jewellery. ring. bracelet. necklace. pendant. earring. bangle."
_DINO_MODEL_ID = "IDEA-Research/grounding-dino-base"
_dino_model = None
_dino_processor = None


def _dino_available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def _dino_predictor():
    """Lazy-loaded, cached (same singleton style as _predictor() below).
    Weights download automatically from the HuggingFace Hub on first call
    and are cached locally afterward -- no manual checkpoint file needed,
    unlike SAM2's."""
    global _dino_model, _dino_processor
    if _dino_model is not None:
        return _dino_processor, _dino_model
    import torch
    from transformers import AutoProcessor, GroundingDinoForObjectDetection
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    _dino_processor = AutoProcessor.from_pretrained(_DINO_MODEL_ID)
    _dino_model = GroundingDinoForObjectDetection.from_pretrained(_DINO_MODEL_ID).to(dev)
    return _dino_processor, _dino_model


def _dino_boxes(bgr: np.ndarray, expect: int, box_threshold: float = 0.25) -> list:
    """Bounding boxes of the jewellery, found by TEXT-PROMPTED detection --
    used as SAM2 BOX prompts, and as the source for the seed points below.

    Replaces the earlier gold-hue colour threshold that produced this same
    shape of result. That approach worked for warm-toned gold on a dark
    backdrop but is blind to silver/white-metal pieces (no gold-hue blob
    ever forms for them) and can be fooled by any other warm-toned object in
    frame (a beige display card, a wooden prop). Asking Grounding DINO for
    "jewellery"/"ring"/etc. directly identifies the object by what it IS,
    not by its colour, so it works the same for gold and silver alike and
    isn't confused by a colourful prop (e.g. a bright pink display clip)
    the way colour-threshold detection was.
    """
    import torch
    from PIL import Image
    processor, model = _dino_predictor()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    inputs = processor(images=image, text=_DINO_PROMPT, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model(**inputs)
    results = processor.post_process_grounded_object_detection(
        outputs, inputs["input_ids"], threshold=box_threshold,
        text_threshold=box_threshold, target_sizes=[rgb.shape[:2]],
    )[0]
    scored = sorted(zip(results["scores"].tolist(), results["boxes"].tolist()), reverse=True)
    H, W = bgr.shape[:2]
    boxes = []
    for _, (x0, y0, x1, y1) in scored[:expect]:
        w, h = x1 - x0, y1 - y0
        pad = 0.08 * max(w, h)
        boxes.append([max(0, int(x0 - pad)), max(0, int(y0 - pad)),
                      min(W, int(x1 + pad)), min(H, int(y1 + pad))])
    boxes.sort(key=lambda b: b[0])
    return boxes


def _centre_seed_from_boxes(boxes: list, bgr: np.ndarray) -> list:
    """Seed points derived from the DINO boxes' own centres. Falls back to
    the image centre if nothing was detected, matching the old function's
    fail-open behaviour."""
    if not boxes:
        h, w = bgr.shape[:2]
        return [(w // 2, h // 2)]
    pts = [((b[0] + b[2]) // 2, (b[1] + b[3]) // 2) for b in boxes]
    pts.sort(key=lambda p: p[0])
    return pts


def locate(bgr: np.ndarray, expect: int = 1, margin: float = 0.10):
    global _last_mask, _last_masks
    """Return tight boxes around each ornament, left-to-right."""
    pred = _predictor()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pred.set_image(rgb)

    H, W = bgr.shape[:2]
    gboxes = _dino_boxes(bgr, expect)
    seeds = _centre_seed_from_boxes(gboxes, bgr)
    boxes = []
    box_masks = []
    for idx, (cx, cy) in enumerate(seeds):
        gb = gboxes[idx] if idx < len(gboxes) else None
        masks, scores, _ = pred.predict(
            point_coords=np.array([[cx, cy]]),
            point_labels=np.array([1]),
            box=(np.array(gb) if gb is not None else None),
            multimask_output=True,
        )
        # Pick by SAM2's OWN CONFIDENCE, not by colour.
        #
        # The old tiebreak picked by gold-pixel-fraction specifically because
        # SAM2's top-scoring mask on a hand-held plate was often the hand, and
        # colour was the only cheap way to prefer the jewellery over it. That
        # ambiguity is already resolved now: the seed box itself came from
        # Grounding DINO being asked for "jewellery"/"ring"/etc, so a mask
        # that stays inside that box IS the jewellery by construction, not by
        # colour. Confidence among masks that already passed containment is a
        # clean tiebreak now, and unlike gold-fraction it works identically
        # for silver.
        best_score, chosen = -1.0, None
        for i in range(len(masks)):
            m = masks[i].astype(bool)
            area = float(m.sum())
            if area < 400:
                continue
            cover = area / (H * W)
            if not (0.002 < cover < 0.30):     # stand / hand / whole-frame grabs
                continue
            # A mask must not sprawl far outside the box it was prompted with;
            # that is how the velvet cone got in.
            if gb is not None:
                bw, bh = gb[2] - gb[0], gb[3] - gb[1]
                inside = m[gb[1]:gb[3], gb[0]:gb[2]].sum()
                if area > 0 and float(inside) / area < 0.80:
                    continue
                if area > 3.0 * bw * bh:
                    continue
            if float(scores[i]) > best_score:
                best_score, chosen = float(scores[i]), m
        if chosen is None:
            # SAM2 gave nothing trustworthy. The DINO box alone is a worse
            # boundary but a far better answer than the display stand.
            if gb is not None:
                boxes.append((int(gb[0]), int(gb[1]), int(gb[2]), int(gb[3])))
                box_masks.append(None)
            continue
        _last_mask = chosen
        ys, xs = np.nonzero(chosen)
        if len(xs) < 50:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        mx, my = int((x1 - x0) * margin), int((y1 - y0) * margin)
        boxes.append((int(max(0, x0 - mx)), int(max(0, y0 - my)),
                      int(min(W, x1 + mx)), int(min(H, y1 + my))))
        box_masks.append(chosen)

    order = sorted(range(len(boxes)), key=lambda i: boxes[i][0])
    boxes = [boxes[i] for i in order]
    box_masks = [box_masks[i] for i in order]
    _last_masks = box_masks
    return boxes


def _upright_angle(mask: np.ndarray) -> float:
    """Tilt of the piece, in degrees, from its minimum-area rectangle.

    minAreaRect rather than PCA: a pendant is roughly as wide as it is tall,
    and on compact shapes like that the PCA major axis flips between nearly
    equal eigenvalues and returns a wildly different angle run to run. The
    enclosing rectangle is stable for the same shape.

    OpenCV 4.5 changed minAreaRect's convention: the angle now comes back in
    [0, 90), not the (-90, 0] every older example assumes. Normalising for the
    wrong one silently produced values like 61 degrees for a nearly-upright
    piece, which then exceeded the tilt cap and disabled straightening
    entirely. Fold into (-45, 45] instead: a rectangle's two interpretations
    differ by 90 degrees, and the smaller correction is always the intended
    one — a piece is far likelier to be a few degrees off than photographed
    sideways.
    """
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 0.0
    (_, _), (_, _), ang = cv2.minAreaRect(max(cnts, key=cv2.contourArea))
    ang = ang % 90.0
    if ang > 45.0:
        ang -= 90.0
    return float(ang)


def _rotate_keep(bgr: np.ndarray, mask: np.ndarray, ang: float):
    h, w = bgr.shape[:2]
    pad = int(0.3 * max(h, w))
    bgr = cv2.copyMakeBorder(bgr, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    mask = cv2.copyMakeBorder(mask.astype(np.uint8), pad, pad, pad, pad,
                              cv2.BORDER_CONSTANT, value=0)
    ch, cw = bgr.shape[:2]
    M = cv2.getRotationMatrix2D((cw / 2, ch / 2), ang, 1.0)
    bgr = cv2.warpAffine(bgr, M, (cw, ch), flags=cv2.INTER_LANCZOS4,
                         borderMode=cv2.BORDER_REPLICATE)
    mask = cv2.warpAffine(mask, M, (cw, ch), flags=cv2.INTER_NEAREST)
    return bgr, mask


# Mangalsutra family: the black is a REAL bead chain, not hollow
# negative-space design work -- the one exception to the owner's
# "no black jewellery, black = hollow" rule (2026-08-19), called out
# directly by the owner for these categories specifically. Keyed the same
# way category_orientation.py is (ornament_code_map.Category.key).
_BLACK_IS_MATERIAL_CATEGORIES = frozenset({"wati_22", "ms_long_22", "mss_short_20", "mss_short_22"})


def _refine_mask(bgr_crop: np.ndarray, mask_crop: np.ndarray, category: str | None = None) -> np.ndarray:
    """Strips display-prop pixels SAM2 wrongly pulled into the object mask.

    Confirmed live (2026-08-19, tag WT22/19): on a navy-blue dot-print
    display card, SAM2's mask correctly covered the gold-and-ruby earrings
    but ALSO swallowed a large connected chunk of the card itself --
    visually confirmed via a mask overlay, not a crop-tightness or feather
    issue. RMBG-2.0 failed the identical way on the same image, so this
    isn't one model being weak; the card's texture/lighting genuinely reads
    as "object" to both. Same fix pattern as this repo's existing pixel-veto
    material check: no jewellery in this catalogue is blue, so any
    saturated-blue pixel inside the mask is provably wrong and gets veto'd
    regardless of which model (or how confidently) included it. Gold
    (H~15-35), ruby/red stones (H~0-10 or ~170-179), and white/silver
    (low saturation) are all untouched by this range.
    Only ONE remaining connected blob survives afterward, so the veto can't
    leave the jewellery mask fragmented into disconnected islands (a stray
    metal glint on the card, for instance) -- the real piece is always one
    solid connected region. That blob is picked by METAL/GEMSTONE CONTENT,
    not raw pixel area -- confirmed live (2026-08-19, tag BL22/135): a thin
    ring band shot against a lot of visible black interior backdrop had the
    backdrop as the larger connected region, so "largest wins" kept the
    background and painted the actual ring white, permanently destroying
    that photo (the pipeline overwrites files in place, no raw survived to
    recover it). Same warm/bright "metal" definition already proven
    elsewhere in this file (see focus_boxes()) and in capture_tool.py's own
    visibility gate -- reused here for consistency rather than inventing a
    third threshold.

    Two-stage, not a pure metal-fraction max: an early version picked
    whichever blob had the HIGHEST metal fraction, which backfired the
    opposite way -- a tiny, purely-gold sliver (100% metal, small area)
    beat the real object's full connected region (which legitimately
    includes the paper tag, dark crevices, and specular highlights outside
    the metal colour ranges, so its fraction reads lower even though it's
    unambiguously the right blob). Metal fraction is only used to DISQUALIFY
    implausible candidates now (a background blob genuinely has near-zero
    metal content); the largest surviving candidate wins, same as before,
    just with the background blob no longer eligible to compete.
    """
    hsv = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    is_blue_prop = (h >= 95) & (h <= 130) & (s >= 40)
    refined = mask_crop.astype(bool) & ~is_blue_prop

    n, lab, stats, _ = cv2.connectedComponentsWithStats(refined.astype(np.uint8), 8)
    if n > 1:
        warm = (h >= 5) & (h <= 45) & (s >= 60) & (v >= 60)
        red_stone = ((h <= 10) | (h >= 170)) & (s >= 50) & (v >= 40)
        bright = (v >= 150) & (s < 60)
        metal = warm | red_stone | bright
        # Owner rule (2026-08-19, critical): this catalogue has NO black
        # studs or black diamonds -- any black pixel inside a piece's own
        # silhouette is a hollow/negative-space design element (filigree,
        # openwork, a gap you see the backdrop through), never real
        # material. Excluded from the metal-fraction DENOMINATOR entirely
        # (not just failed as "not metal"), so an ornate lacy piece with a
        # lot of legitimate open/cutout work doesn't get unfairly scored
        # as low-metal-content and disqualified. Still ranked by its TOTAL
        # area (hollow parts included) below, since the hollow interior is
        # genuinely part of the piece's silhouette, not something to
        # shrink it for.
        #
        # ONE exception (owner-flagged, same day): mangalsutra-family
        # pieces (WATI, MS LONG, MSS-SHORT) have a REAL black bead chain --
        # there, black is legitimate material, not hollow space, and must
        # not be excluded or it gets stripped/painted white right along
        # with genuine background. _BLACK_IS_MATERIAL_CATEGORIES skips the
        # black carve-out entirely for those, falling back to the plain
        # area-based fraction (black pixels neither help nor hurt the
        # score, same treatment as any other non-metal-colour pixel).
        black_is_material = category in _BLACK_IS_MATERIAL_CATEGORIES
        is_black = v < 40
        best_label, best_area = None, -1
        for label in range(1, n):
            area = stats[label, cv2.CC_STAT_AREA]
            if area < 200:
                continue
            component = lab == label
            if black_is_material:
                denom_area = area
                numerator = component & metal
            else:
                non_black = component & ~is_black
                denom_area = int(non_black.sum())
                numerator = non_black & metal
            if denom_area < 50:
                continue
            metal_fraction = float(numerator.sum()) / float(denom_area)
            if metal_fraction < 0.15:
                continue
            if area > best_area:
                best_area, best_label = area, label
        if best_label is not None:
            refined = lab == best_label
    return refined


def _composite_on_white(bgr_crop: np.ndarray, mask_crop: np.ndarray, feather: int = 3) -> np.ndarray:
    """Cuts bgr_crop out against a white background using mask_crop (SAM2's
    own segmentation, already proven correct by being what picked this exact
    crop region) instead of asking a SEPARATE, general-purpose background-
    removal model to re-guess the foreground/background split from scratch.
    Confirmed live (2026-08-18): RMBG-2.0 completely failed to remove a dark,
    textured, branded display box even at ~45% object occupancy in the
    frame -- not a framing/crop-tightness problem, the model just doesn't
    handle that class of background. SAM2's mask is already known-good here
    because it's the same mask that produced the (visually correct) crop
    boundary. A small Gaussian blur of the mask before compositing avoids a
    hard-edged cutout look (jagged pixel-level aliasing) in favour of a soft
    antialiased edge, same effect RMBG's own alpha matte was providing when
    it worked at all."""
    mask_f = mask_crop.astype(np.float32)
    if feather > 0:
        k = feather * 2 + 1
        mask_f = cv2.GaussianBlur(mask_f, (k, k), 0)
    alpha = np.clip(mask_f, 0.0, 1.0)[:, :, None]
    white = np.full_like(bgr_crop, 255)
    return (bgr_crop.astype(np.float32) * alpha + white.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)


def _metal_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # v < 250, not just s < 60: confirmed live (2026-08-19) that the plain
    # "bright, low-saturation" silver/white-metal test also matches pure
    # WHITE -- which is exactly the padding colour _align_vertical_hang
    # fills around the piece before rotating. Without this bound, the
    # entire white padding area reads as "metal" too, making every
    # bounding-box/aspect-ratio measurement in that function meaningless
    # (the mask was effectively just the whole padded rectangle). Real
    # silver/white-metal jewellery highlights sit comfortably under 250;
    # only near-pure-white padding/background gets excluded.
    return ((h >= 5) & (h <= 45) & (s >= 60) & (v >= 60)) | ((v >= 150) & (v < 250) & (s < 60))


def _align_vertical_hang(bgr_crop: np.ndarray) -> np.ndarray:
    """Rotates a SINGLE piece's crop so its elongated axis is vertical,
    attachment end up -- for categories that hang/dangle (earrings,
    jhumka, nath, tikka) rather than lie flat. Requested explicitly
    (2026-08-19, tag TP22/83): the piece's bottom should face where the
    MAIN VIEW/LEFT ANGLE/RIGHT ANGLE caption sits, i.e. hang downward in
    frame, matching how it's actually worn -- confirmed the existing
    straighten path (a small "nearest axis" nudge, see _upright_angle's
    docstring) is the wrong tool for this, and the pair-crop path had no
    rotation correction at all.

    Must be called on ONE piece's own crop, before it's placed into any
    multi-piece canvas -- running this on a side-by-side pair composite
    would find the axis of the PAIR (wide, side-by-side) and rotate both
    pieces as one wrong unit instead of straightening each individually.

    Candidate rotations, picked by MEASURING the result, not by trusting
    a single trig formula: an earlier version computed one "correct"
    rotation via atan2 on a PCA axis and got the direction backwards --
    confirmed live (2026-08-19), it produced pieces WIDER than tall,
    the opposite of intended. This file already has one documented
    minAreaRect sign-convention bug (see _upright_angle's docstring);
    rather than risk a second unverified trig formula, this tries several
    candidate angles from minAreaRect and keeps whichever one actually
    produces the tallest (most vertical) result, verified directly on
    the pixels rather than assumed from the angle's sign.

    Which end is "up": whichever end was ALREADY topmost in the
    ORIGINAL, unrotated crop is kept on top -- confirmed live
    (2026-08-19): a mass-based guess ("the heavier/more ornate end hangs
    down") got flipped upside down on a real piece, because a small but
    highly reflective stud scored as more "gold pixel mass" than the
    actual dangling ornament. Trusting how staff physically positioned
    the piece for the photo is a far safer assumption than guessing from
    pixel content. Fails open (returns the crop unchanged) on any error
    or insufficient signal.
    """
    try:
        metal = _metal_mask(bgr_crop)
        ys, xs = np.nonzero(metal)
        if len(xs) < 50:
            return bgr_crop

        # Where the ORIGINAL top of the piece was, before any rotation --
        # tracked through each candidate's transform below to decide
        # top-vs-bottom. The CENTROID of the topmost 15% of metal pixels
        # (by original y), not a single extreme pixel: confirmed live
        # (2026-08-19) that a lone noisy/misclassified pixel near one edge
        # was enough to flip a real piece upside down on one of a pair
        # while its twin (same photo, same physical orientation) came out
        # correct -- a single-pixel extremum has zero tolerance for that
        # kind of noise, an averaged cluster does.
        y_cutoff = np.percentile(ys, 15)
        top_cluster = ys <= y_cutoff
        orig_top = (float(xs[top_cluster].mean()), float(ys[top_cluster].mean()))

        pts = np.column_stack([xs, ys]).astype(np.int32)
        rect_angle = float(cv2.minAreaRect(pts)[2])

        h0, w0 = bgr_crop.shape[:2]
        pad = int(0.5 * max(h0, w0))
        padded = cv2.copyMakeBorder(bgr_crop, pad, pad, pad, pad,
                                    cv2.BORDER_CONSTANT, value=(255, 255, 255))
        ch, cw = padded.shape[:2]
        padded_top = (orig_top[0] + pad, orig_top[1] + pad)

        def _try_angle(ang):
            matrix = cv2.getRotationMatrix2D((cw / 2, ch / 2), ang, 1.0)
            rotated = cv2.warpAffine(padded, matrix, (cw, ch), flags=cv2.INTER_LANCZOS4,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
            metal2 = _metal_mask(rotated)
            ys2, xs2 = np.nonzero(metal2)
            if len(xs2) < 50:
                return None
            margin = 20
            y0 = max(0, int(ys2.min()) - margin); y1 = min(rotated.shape[0], int(ys2.max()) + margin)
            x0 = max(0, int(xs2.min()) - margin); x1 = min(rotated.shape[1], int(xs2.max()) + margin)
            cropped = rotated[y0:y1, x0:x1]
            if cropped.shape[0] < 8 or cropped.shape[1] < 8:
                return None
            aspect = cropped.shape[0] / float(cropped.shape[1])  # height / width
            transformed = matrix @ np.array([padded_top[0], padded_top[1], 1.0])
            top_in_bottom_half = (transformed[1] - y0) > (cropped.shape[0] / 2.0)
            return (aspect, cropped, top_in_bottom_half)

        # Stage 1 -- coarse: which of the 2 perpendicular candidates (the
        # minAreaRect angle and its +90) actually makes the piece taller
        # than wide. (+180/-90 variants are the same axis, so only 2
        # DISTINCT aspect-ratio outcomes exist regardless of how many
        # were tried -- verified live 2026-08-19.)
        coarse_best = None
        for ang in (rect_angle, rect_angle + 90.0):
            result = _try_angle(ang)
            if result is not None and (coarse_best is None or result[0] > coarse_best[1]):
                coarse_best = (ang, result[0])
        if coarse_best is None:
            return bgr_crop
        coarse_ang = coarse_best[0]

        # Stage 2 -- fine: "dead straight" (2026-08-19 explicit request)
        # needs more precision than a single box-fit angle reliably gives
        # on an irregular shape (chain + bell + ball + hook is not a
        # clean rectangle, so minAreaRect's best-fit angle is a good
        # starting point but not necessarily the exact optimum). Sweep a
        # small window around the coarse angle in fine steps and keep
        # whichever produces the TIGHTEST vertical fit (max aspect
        # ratio) -- a perfectly straight piece produces the narrowest
        # possible bounding box, so maximizing aspect ratio directly
        # targets "dead straight" rather than approximating it.
        best = None
        for delta in np.arange(-4.0, 4.01, 0.25):
            result = _try_angle(coarse_ang + delta)
            if result is not None and (best is None or result[0] > best[0]):
                best = result

        if best is None:
            return bgr_crop
        _, cropped, top_in_bottom_half = best
        if top_in_bottom_half:
            cropped = cv2.rotate(cropped, cv2.ROTATE_180)
        return cropped
    except Exception:
        return bgr_crop


def tight_crop(src_path: str, out_path: str, expect: int = 1,
               margin: float = 0.10, straighten: bool = True,
               max_tilt: float = 30.0, remove_background: bool = True,
               fixed_angle: float | None = None, category: str | None = None,
               prefer_vertical: bool = False):
    """Crop a plate down to just the ornament(s). Returns (path, info).

    When ``straighten`` is on, the crop is levelled first so the piece sits
    upright in the reference Klein sees. Correcting here rather than on the
    output matters: Klein reproduces the orientation it is given, so a tilted
    reference yields a tilted catalogue image that then has to be rotated
    after generation — resampling an already-generated image and cutting into
    its edges. Straightening the input costs nothing.

    ``fixed_angle``, when given, uses that rotation directly instead of
    computing one from this image's own mask. Requested live (2026-08-19):
    a set's MAIN/ANGLE_1/ANGLE_2 shots each straighten to THEIR OWN mask's
    tilt independently, so the three panels could level to visibly
    different angles even though they're meant to read as one consistent
    triptych. The caller computes the angle from MAIN once, then passes it
    in for ANGLE_1/ANGLE_2 so all three share one rotation reference
    instead of three independent (and sometimes disagreeing) ones. Still
    gated by the same max_tilt safety cap as the auto path.

    When ``remove_background`` is on (single-piece crops only -- the
    side-by-side multi-piece path has no single aligned mask to reuse), the
    SAME SAM2 mask that determined the crop boundary is reused to composite
    the ornament onto white, replacing a separate background-removal pass
    -- see _composite_on_white()'s doc comment for why this replaced RMBG-2.0
    entirely for this path (2026-08-18). Fails open to the plain crop (no
    background removal) if no usable mask survived to this point.
    """
    bgr = cv2.imread(src_path)
    if bgr is None or not available():
        return src_path, None
    try:
        boxes = locate(bgr, expect=expect, margin=margin)
    except Exception as e:
        return src_path, {"error": f"{type(e).__name__}: {e}"}
    if not boxes:
        return src_path, None
    box_masks = list(_last_masks)

    aligned_mask = _last_mask
    tilt = None
    if straighten and expect == 1 and not prefer_vertical:
        try:
            m = _last_mask
            if m is not None:
                tilt = float(fixed_angle) if fixed_angle is not None else _upright_angle(m)
                if 0.5 < abs(tilt) <= max_tilt:
                    bgr, m2 = _rotate_keep(bgr, m, tilt)
                    aligned_mask = m2
                    ys, xs = np.nonzero(m2)
                    if len(xs) > 50:
                        H2, W2 = bgr.shape[:2]
                        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
                        mx = int((x1 - x0) * margin); my = int((y1 - y0) * margin)
                        boxes = [(int(max(0, x0 - mx)), int(max(0, y0 - my)),
                                  int(min(W2, x1 + mx)), int(min(H2, y1 + my)))]
                else:
                    tilt = 0.0
        except Exception:
            tilt = None

    H, W = bgr.shape[:2]

    if len(boxes) > 1:
        # Crop each piece and butt them together, rather than taking the union
        # box. A pair sitting apart on a stand has a union box covering
        # everything between them — measured at 84-98% of the plate on Bali,
        # i.e. barely a crop at all, which is why those came back as invented
        # jewellery. Side-by-side keeps both pieces and their relative size
        # while dropping the stand in between.
        crops = [bgr[b[1]:b[3], b[0]:b[2]] for b in boxes]
        crops = [c for c in crops if c.size and c.shape[0] > 16 and c.shape[1] > 16]
        if not crops:
            return src_path, None
        if prefer_vertical:
            # Per-piece, BEFORE scaling/pasting -- see _align_vertical_hang's
            # own docstring for why this must happen per-piece and not on
            # the assembled side-by-side canvas (that would find the
            # PAIR's own wide axis and rotate both pieces as one unit).
            crops = [_align_vertical_hang(c) for c in crops]
        th = max(c.shape[0] for c in crops)
        scaled = [cv2.resize(c, (max(1, int(c.shape[1] * th / c.shape[0])), th),
                             interpolation=cv2.INTER_AREA) for c in crops]
        gap = max(8, int(th * 0.04))
        tw = sum(c.shape[1] for c in scaled) + gap * (len(scaled) - 1)
        canvas = np.zeros((th, tw, 3), np.uint8)
        x = 0
        for c in scaled:
            canvas[:, x:x + c.shape[1]] = c
            x += c.shape[1] + gap
        cv2.imwrite(out_path, canvas)
        used = sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes)
        return out_path, {"boxes": boxes, "pieces": len(boxes), "mode": "side_by_side",
                          "occupancy": round(used / float(W * H), 4)}

    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    if (x1 - x0) < 64 or (y1 - y0) < 64:
        return src_path, None
    crop = bgr[y0:y1, x0:x1]
    bg_removed = False
    if remove_background and expect == 1 and aligned_mask is not None:
        try:
            mask_crop = aligned_mask[y0:y1, x0:x1]
            if mask_crop.shape[:2] == crop.shape[:2] and mask_crop.any():
                refined = _refine_mask(crop, mask_crop, category=category)
                # Sanity floor, not just "is it empty": confirmed live
                # (2026-08-19, tag WT22/19's LEFT ANGLE) that SAM2's raw mask
                # can be mostly noise with the paper TAG as its one solid
                # blob -- "largest connected component" then picks the tag,
                # not the jewellery, and the composite wipes out the actual
                # product. A tight crop is, by construction, mostly filled
                # by the piece (occupancy logged above typically 0.75-0.95),
                # so a kept mask covering only a sliver of the crop is a
                # sign the segmentation locked onto the wrong thing, not
                # that the piece is genuinely tiny. Bail to the plain crop
                # (no bg removal, but the full item stays visible) rather
                # than risk shipping a photo with the product cut out.
                crop_px = crop.shape[0] * crop.shape[1]
                if refined.any() and float(refined.sum()) / crop_px >= 0.15:
                    crop = _composite_on_white(crop, refined)
                    bg_removed = True
        except Exception:
            bg_removed = False
    if prefer_vertical:
        crop = _align_vertical_hang(crop)
    cv2.imwrite(out_path, crop)
    return out_path, {"box": [x0, y0, x1, y1], "pieces": len(boxes),
                      "occupancy": round((x1 - x0) * (y1 - y0) / float(W * H), 4),
                      "background_removed": bg_removed, "tilt": tilt}


def best_single_crop(src_path: str, out_path: str, margin: float = 0.12):
    """Crop the ONE most confidently-jewellery piece from the plate.

    Every automatic cue tried for finding BOTH pieces of a pair has a prop
    that mimics it: gold hue matched warm bokeh, texture matched velvet nap,
    SAM2 objectness matched the display stand, brightness matched a white
    paper tag. The first-ranked box, however, was correct on all five Bali
    plates — it is only the second that goes wrong.

    So take one piece and mirror it downstream rather than fighting for two.
    A matched pair is mirror-symmetric by manufacture, and this is the repo's
    own documented rule (.agents/AGENTS.md, "Symmetric Pairs"). It trades the
    unshown piece's individuality — a defect on it would be hidden — for a
    reference that is actually correct.
    """
    bgr = cv2.imread(src_path)
    if bgr is None:
        return src_path, None
    boxes = focus_boxes(bgr, expect=1)
    if not boxes:
        return src_path, None
    x0, y0, x1, y1 = boxes[0]
    if (x1 - x0) < 48 or (y1 - y0) < 48:
        return src_path, None
    cv2.imwrite(out_path, bgr[y0:y1, x0:x1])
    H, W = bgr.shape[:2]
    return out_path, {"box": [x0, y0, x1, y1], "mirrored": True,
                      "occupancy": round((x1 - x0) * (y1 - y0) / float(W * H), 4)}
