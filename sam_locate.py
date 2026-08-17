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
    global _last_mask
    """Return tight boxes around each ornament, left-to-right."""
    pred = _predictor()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pred.set_image(rgb)

    H, W = bgr.shape[:2]
    gboxes = _dino_boxes(bgr, expect)
    seeds = _centre_seed_from_boxes(gboxes, bgr)
    boxes = []
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
            continue
        _last_mask = chosen
        ys, xs = np.nonzero(chosen)
        if len(xs) < 50:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        mx, my = int((x1 - x0) * margin), int((y1 - y0) * margin)
        boxes.append((int(max(0, x0 - mx)), int(max(0, y0 - my)),
                      int(min(W, x1 + mx)), int(min(H, y1 + my))))

    boxes.sort(key=lambda b: b[0])
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


def tight_crop(src_path: str, out_path: str, expect: int = 1,
               margin: float = 0.10, straighten: bool = True,
               max_tilt: float = 30.0):
    """Crop a plate down to just the ornament(s). Returns (path, info).

    When ``straighten`` is on, the crop is levelled first so the piece sits
    upright in the reference Klein sees. Correcting here rather than on the
    output matters: Klein reproduces the orientation it is given, so a tilted
    reference yields a tilted catalogue image that then has to be rotated
    after generation — resampling an already-generated image and cutting into
    its edges. Straightening the input costs nothing.
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

    tilt = None
    if straighten and expect == 1:
        try:
            m = _last_mask
            if m is not None:
                tilt = _upright_angle(m)
                if 0.5 < abs(tilt) <= max_tilt:
                    bgr, m2 = _rotate_keep(bgr, m, tilt)
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
    cv2.imwrite(out_path, bgr[y0:y1, x0:x1])
    return out_path, {"box": [x0, y0, x1, y1], "pieces": len(boxes),
                      "occupancy": round((x1 - x0) * (y1 - y0) / float(W * H), 4)}


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
