"""
design_verify_local.py — fully local design-fidelity check.

Answers the only question that matters for the catalogue: is the ornament in
the AI-generated image the SAME physical piece as the one in the original
photograph?

WHY THIS EXISTS / WHY IT LOOKS LIKE THIS
========================================
Four families were benchmarked on the real archive plus a known-bad pair (a
ladies ring whose "generation" was actually a previous item's earrings), and
every one of them failed when fed the images as-shot:

    qwen2.5vl:7b (VLM)   answer follows the PROMPT, not the images — says YES
                         to everything, or NO to an image compared to itself
    CLIP ViT-B/32        correct 0.804 vs wrong 0.800  → +0.004, noise
    DINOv2 (raw)         correct 0.707 vs wrong 0.677  → +0.030, noise
    LoFTR keypoints      correct 27 vs wrong 44 → INVERTED
    Gemini flash (API)   all free models answered SAME_DESIGN: YES, HIGH, on
                         the known-bad pair

They share one root cause: the source is a phone photo of a piece held on
paper, the output is a studio render on a velvet box. That BACKGROUND domain
gap is larger, in every representation tested, than the difference between two
genuinely different rings. The design signal is real but buried.

Segmenting the ornament out of BOTH images first removes the gap, and the two
cases then move in OPPOSITE directions — which is the signature of real signal
rather than a threshold that happens to fit:

                          as-shot      segmented
    correct generation      0.707    →    0.752   (up)
    wrong product           0.677    →    0.609   (down)
    margin                 +0.030    →   +0.143

Hence: segment (RMBG-2.0) → tight-crop to the ornament → embed (DINOv2) →
cosine. Fully local, no API, no quota, ~2s per pair on the RTX 5070.

HONEST LIMITS
-------------
* The threshold below is provisional — derived from a two-pair margin. Run
  calibrate() over a batch with known verdicts before trusting it to gate
  production, and prefer flagging for review over silent rejection until then.
* This detects "different piece". It will NOT catch a subtle single-stone
  substitution; nothing tested locally can.
* Segmentation can retain a fragment of the operator's fingertip. That is
  usually harmless but is why crops are inspected in calibrate().
"""

import os
import threading

BASE = os.path.dirname(os.path.abspath(__file__))

# Provisional, from the 2-pair benchmark above (correct 0.752 / wrong 0.609).
# Sits nearer the wrong-pair side so the check errs toward letting work
# through rather than quarantining good output on thin evidence.
SIMILARITY_ACCEPT = 0.68

# Below this, the pieces are so unalike that it is almost certainly a
# different ornament rather than a poor rendering of the right one.
SIMILARITY_HARD_FAIL = 0.55

_SEG_MODEL = "briaai/RMBG-2.0"
_EMB_MODEL = "facebook/dinov2-base"

_lock = threading.Lock()
_seg = _emb = _proc = _tf = _dev = None


def _load():
    """Lazy, once. Loading is ~10s and must not happen at import time — this
    module is imported by the Flask app, which has to answer /api/health long
    before any verification is requested."""
    global _seg, _emb, _proc, _tf, _dev
    if _emb is not None:
        return
    with _lock:
        if _emb is not None:
            return
        import torch
        from torchvision import transforms
        from transformers import AutoModelForImageSegmentation, AutoModel, AutoImageProcessor
        _dev = "cuda" if torch.cuda.is_available() else "cpu"
        torch.set_float32_matmul_precision("high")
        _seg_m = AutoModelForImageSegmentation.from_pretrained(
            _SEG_MODEL, trust_remote_code=True).to(_dev).eval()
        _emb_m = AutoModel.from_pretrained(_EMB_MODEL).to(_dev).eval()
        globals()["_seg"] = _seg_m
        globals()["_emb"] = _emb_m
        globals()["_proc"] = AutoImageProcessor.from_pretrained(_EMB_MODEL)
        globals()["_tf"] = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])


def _segment(path):
    """Return ``(RGB image, mask)`` using the shared local segmenter."""
    import torch
    from PIL import Image
    from torchvision import transforms
    _load()
    with Image.open(path) as opened:
        im = opened.convert("RGB")
    with torch.no_grad():
        x = _tf(im).unsqueeze(0).to(_dev)
        pred = _seg(x)[-1].sigmoid().cpu()[0].squeeze()
    mask = transforms.ToPILImage()(pred).resize(im.size)
    return im, mask


def foreground_bbox(path, threshold=40):
    """Return ``((width, height), bbox)`` for the segmented foreground."""
    im, mask = _segment(path)
    try:
        bbox = mask.point(lambda v: 255 if v > threshold else 0).getbbox()
        return im.size, bbox
    finally:
        im.close()
        mask.close()


# Above this 95th-percentile masked mean-absolute-pixel-difference (0-255
# scale) on the BACKGROUND-ONLY region (jewellery masked out), the generated
# output's background is treated as redrawn rather than reproduced from the
# source file. Verified directly on synthetic good/bad pairs: an untouched
# background scored p95=2.0, a deliberately redrawn corner scored p95=73.3 —
# a 35x gap, comfortable margin either side of 15. Provisional starting
# point for real production drift (like SIMILARITY_ACCEPT/HARD_FAIL above,
# there's too little real production history yet to calibrate over a full
# batch), but backed by an actual measured separation, not a guess. Purely
# local/classical (no model, no API, no quota) — this is a structural pixel
# comparison, not a judgment call, so it needs no vision model at all.
BACKGROUND_DIFF_MAX = 15.0


def verify_background_fidelity(generated_path, source_background_path, debug_dir=None):
    """Detect background redraw/drift: is the generated image's background
    (everything outside the jewellery/subject) still the real source
    background file, or did the engine reinterpret it?

    Real incident this addresses (2026-08-02, TP22_8): a studio composite's
    decorative wallpaper linework was regenerated rather than reproduced —
    subtly different left vs right, a visible seam — despite the prompt
    explicitly saying "reproduce background EXACTLY, pixel-perfect". A
    generative model asked to preserve background pixels approximates them;
    it does not literally copy them. Fine repeating detail (florals,
    linework, patterns) is exactly what that approximation reproduces least
    reliably, and no amount of stronger prompt wording changes that — this
    check catches the failure mode directly instead.

    Segments the GENERATED image locally (reusing the same RMBG-2.0 call
    already used for design-fidelity) to find the jewellery/subject region,
    masks that region OUT of both images, and measures the masked mean-
    absolute pixel difference. A real background-preservation success scores
    near 0 (same file, only JPEG noise); a redrawn/reinterpreted region
    scores much higher. Runs entirely locally — no API call, no quota,
    sub-second.

    Uses raw pixel difference rather than SSIM: verified directly that SSIM
    is close to blind to this exact failure mode when the redrawn region is
    a large flat/low-texture area — a uniform color patch has little internal
    structure to disagree on even when its actual color is completely wrong,
    so SSIM regularly scored a synthetic redrawn corner as "similar" to the
    real source in testing. Plain absolute pixel difference has no such
    blind spot — it does not care whether a region is textured or flat, only
    whether the actual pixel values match.

    Returns {"same": True|False|None, "score": float, "reason": str}.
    same=None means the check itself could not run (missing file, source/
    generated size mismatch beyond what a simple resize should reconcile,
    or an internal error) — the caller must treat that as unverified, never
    as a pass, same convention as verify_design.
    """
    import numpy as np
    from PIL import Image

    res = {"same": None, "score": None, "reason": ""}
    try:
        if not (os.path.exists(generated_path) and os.path.exists(source_background_path)):
            res["reason"] = "Background check unavailable: generated or source background missing"
            return res

        im, mask = _segment(generated_path)
        try:
            # Dilate the foreground mask generously — the jewellery's own
            # contact shadow and any prop it rests on are legitimately new/
            # engine-placed content too, not source-background pixels, and
            # must not count against fidelity.
            fg_mask = mask.point(lambda v: 255 if v > 30 else 0)
            from PIL import ImageFilter
            fg_mask = fg_mask.filter(ImageFilter.MaxFilter(31))
            # Feather the dilated edge (soft alpha, not a hard binary cutoff)
            # before excluding it: a binary mask boundary still leaves a thin
            # ring of anti-aliased jewellery-edge pixels classified as
            # "background", and those pixels genuinely differ between
            # generated/source images (edge position shifts slightly) for
            # reasons that have nothing to do with background fidelity —
            # counting them inflates the score with false drift. Blurring the
            # mask and excluding anything above a low threshold widens the
            # exclusion zone gradually so no partially-jewellery pixel can
            # leak into the background comparison.
            fg_mask = fg_mask.filter(ImageFilter.GaussianBlur(4))
            bg_mask = fg_mask.point(lambda v: 0 if v > 8 else 255)

            with Image.open(source_background_path) as _raw_src:
                src = _raw_src.convert("RGB")
            if src.size != im.size:
                src = src.resize(im.size)

            gen_arr = np.asarray(im.convert("RGB")).astype(np.int16)
            src_arr = np.asarray(src.convert("RGB")).astype(np.int16)
            mask_arr = np.asarray(bg_mask) > 0

            if mask_arr.sum() < 0.05 * mask_arr.size:
                res["reason"] = "Background check unavailable: jewellery/subject covers too much of the frame"
                return res

            # 95th percentile, not the mean or max: the mean would dilute a
            # small redrawn region back down (the same blind spot that made
            # a naive global SSIM average miss it); the max is too sensitive
            # to single-pixel JPEG/compression outliers. The 95th percentile
            # ignores compression noise in the bulk of a truly-matching
            # background while still surfacing any region large enough to
            # matter (verified: a redrawn patch covering ~12% of the masked
            # background area moved p95 from 2.0 to 73.3).
            diff = np.abs(gen_arr - src_arr).mean(axis=2)
            bg_diff = diff[mask_arr]
            score = float(np.percentile(bg_diff, 95)) if bg_diff.size else 0.0
            res["score"] = round(score, 2)

            if debug_dir:
                os.makedirs(debug_dir, exist_ok=True)
                gen_bg_only = np.where(mask_arr[..., None], np.asarray(im.convert("RGB")), 0).astype(np.uint8)
                src_bg_only = np.where(mask_arr[..., None], np.asarray(src.convert("RGB")), 0).astype(np.uint8)
                Image.fromarray(gen_bg_only).save(os.path.join(debug_dir, "gen_bg_only.jpg"))
                Image.fromarray(src_bg_only).save(os.path.join(debug_dir, "src_bg_only.jpg"))

            if score > BACKGROUND_DIFF_MAX:
                res.update(same=False, reason=(
                    f"Background does not match the source file — pixel difference {score:.1f} "
                    f"above {BACKGROUND_DIFF_MAX} (background likely redrawn, not reproduced)"
                ))
            else:
                res.update(same=True, reason=f"Background matches source — pixel difference {score:.1f}")
            return res
        finally:
            im.close()
            mask.close()
    except Exception as e:
        res["reason"] = f"Background check unavailable: {type(e).__name__}: {e}"
        return res


def cutout(path, save_to=None):
    """Isolate the ornament on white and crop tight to it.

    Cropping matters as much as masking: it removes scale and position as
    variables, so a piece shot small-and-centred and the same piece rendered
    large-and-offset land in the same place before embedding.
    """
    from PIL import Image
    im, mask = _segment(path)
    out = Image.new("RGB", im.size, (255, 255, 255))
    out.paste(im, mask=mask)
    bbox = mask.point(lambda v: 255 if v > 40 else 0).getbbox()
    if bbox:
        out = out.crop(bbox)
    if save_to:
        os.makedirs(os.path.dirname(save_to), exist_ok=True)
        out.save(save_to, "JPEG", quality=92)
    im.close()
    mask.close()
    return out


def _embed(img):
    import torch
    _load()
    with torch.no_grad():
        i = _proc(images=img, return_tensors="pt").to(_dev)
        v = _emb(**i).last_hidden_state[:, 0]
    return v / v.norm(dim=-1, keepdim=True)


def similarity(original_path, generated_path, debug_dir=None):
    """Cosine similarity between the two SEGMENTED ornaments (0..1)."""
    a = cutout(original_path, os.path.join(debug_dir, "a.jpg") if debug_dir else None)
    b = cutout(generated_path, os.path.join(debug_dir, "b.jpg") if debug_dir else None)
    return float((_embed(a) @ _embed(b).T).item())


def verify_design(original_path, generated_path, debug_dir=None):
    """
    Returns {"same": True|False|None, "score": float, "confidence": str,
             "reason": str}

    same=None means "could not verify" — the caller should treat that as
    unverified and flag, never as a pass. Mirrors the fail-open convention the
    rest of the pipeline already uses so a broken GPU pauses nothing, but it
    is recorded rather than silently swallowed.
    """
    res = {"same": None, "score": None, "confidence": "low", "reason": ""}
    try:
        if not (os.path.exists(original_path) and os.path.exists(generated_path)):
            res["reason"] = "Design check unavailable: source or output missing"
            return res
        s = similarity(original_path, generated_path, debug_dir)
        res["score"] = round(s, 4)
        if s < SIMILARITY_HARD_FAIL:
            res.update(same=False, confidence="high",
                       reason=f"Different ornament — similarity {s:.3f} "
                              f"far below {SIMILARITY_HARD_FAIL}")
        elif s < SIMILARITY_ACCEPT:
            res.update(same=False, confidence="medium",
                       reason=f"Design mismatch — similarity {s:.3f} "
                              f"below accept threshold {SIMILARITY_ACCEPT}")
        else:
            res.update(same=True,
                       confidence="high" if s >= SIMILARITY_ACCEPT + 0.06 else "medium",
                       reason=f"Design matches — similarity {s:.3f}")
        return res
    except Exception as e:
        # Never let a verification fault fail a pair; report it as unverified.
        res["reason"] = f"Design check unavailable: {type(e).__name__}: {e}"
        return res


def calibrate(pairs, debug_dir=None):
    """
    pairs: [(original_path, generated_path, expected_same_bool), ...]

    Prints the score distribution and the best separating threshold. This is
    how SIMILARITY_ACCEPT should be set — the shipped value came from only two
    pairs and is a starting point, not a measurement.
    """
    same_s, diff_s, errs = [], [], []
    for a, b, expect in pairs:
        try:
            s = similarity(a, b, debug_dir)
            (same_s if expect else diff_s).append((s, os.path.basename(b)))
        except Exception as e:
            errs.append((os.path.basename(b), str(e)[:60]))
    print(f"  matching pairs   : n={len(same_s)}"
          + (f"  {min(x[0] for x in same_s):.3f} – {max(x[0] for x in same_s):.3f}" if same_s else ""))
    print(f"  mismatching pairs: n={len(diff_s)}"
          + (f"  {min(x[0] for x in diff_s):.3f} – {max(x[0] for x in diff_s):.3f}" if diff_s else ""))
    for name, e in errs:
        print(f"  ERROR {name}: {e}")
    if same_s and diff_s:
        lo, hi = min(x[0] for x in same_s), max(x[0] for x in diff_s)
        if lo > hi:
            print(f"  CLEAN SEPARATION — any threshold in ({hi:.3f}, {lo:.3f}); "
                  f"suggest {(lo + hi) / 2:.3f}")
        else:
            print(f"  OVERLAP of {hi - lo:.3f} — no threshold separates these; "
                  f"do not gate on this alone")
    return {"same": same_s, "diff": diff_s, "errors": errs}
