"""
One-off benchmark: does YOLO-World reliably find a TINY, CORNER-placed
jewellery cutout, and at what resolution/latency?

Synthesizes exactly the test case the "gold visible in corner, hunt never
finds it" bug report described -- takes a real jewellery photo, shrinks it
to a known % of a large canvas, places it in a corner, and runs YOLO-World
at 640/960/1280 to compare recall and latency. No training involved --
YOLO-World is zero-shot, driven by a text prompt vocabulary.
"""
import time
import cv2
import numpy as np
from ultralytics import YOLO

SRC = r"C:\Users\kaila\Desktop\JewelleryCatalogTool\capture_intake\16 GENTS RING 22\GR22_145.jpg"
OUT_DIR = r"C:\Users\kaila\AppData\Local\Temp\claude\C--Kuldeep-Avatar\056171e1-0462-44c7-827c-fcedf6329dfc\scratchpad\yolo_bench"
import os
os.makedirs(OUT_DIR, exist_ok=True)

VOCAB = ["jewellery", "gold jewellery", "ring", "earring", "necklace", "pendant", "bracelet", "bangle", "chain"]

CANVAS = 1600  # square canvas, background-filled, piece placed small in a corner
SIZES_PCT = [0.02, 0.05, 0.10, 0.25]
CORNERS = ["top_left", "top_right", "bottom_left", "bottom_right", "center"]
RESOLUTIONS = [640, 960, 1280]


def make_scene(piece_bgr, size_pct, corner):
    canvas = np.full((CANVAS, CANVAS, 3), 60, dtype=np.uint8)  # neutral gray background
    target_area = (CANVAS * CANVAS) * size_pct
    ph, pw = piece_bgr.shape[:2]
    scale = (target_area / (pw * ph)) ** 0.5
    new_w, new_h = max(4, int(pw * scale)), max(4, int(ph * scale))
    piece_small = cv2.resize(piece_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    margin = 20
    positions = {
        "top_left": (margin, margin),
        "top_right": (CANVAS - new_w - margin, margin),
        "bottom_left": (margin, CANVAS - new_h - margin),
        "bottom_right": (CANVAS - new_w - margin, CANVAS - new_h - margin),
        "center": ((CANVAS - new_w) // 2, (CANVAS - new_h) // 2),
    }
    x, y = positions[corner]
    canvas[y:y + new_h, x:x + new_w] = piece_small
    gt_box = (x / CANVAS, y / CANVAS, (x + new_w) / CANVAS, (y + new_h) / CANVAS)
    return canvas, gt_box


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def main():
    piece = cv2.imread(SRC)
    if piece is None:
        print("FAILED to load source image")
        return

    print("Loading YOLO-World...")
    t0 = time.time()
    model = YOLO("yolov8s-worldv2.pt")
    model.set_classes(VOCAB)
    print(f"Model loaded in {time.time()-t0:.1f}s")

    results_summary = []
    for res in RESOLUTIONS:
        for size_pct in SIZES_PCT:
            for corner in CORNERS:
                scene, gt_box = make_scene(piece, size_pct, corner)
                t0 = time.time()
                r = model.predict(scene, imgsz=res, conf=0.10, verbose=False)[0]
                latency_ms = (time.time() - t0) * 1000

                best_iou = 0.0
                best_conf = 0.0
                detected = False
                if r.boxes is not None and len(r.boxes) > 0:
                    for box, conf in zip(r.boxes.xyxyn.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                        bb = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
                        i = iou(bb, gt_box)
                        if i > best_iou:
                            best_iou = i
                            best_conf = float(conf)
                    detected = best_iou > 0.3

                results_summary.append({
                    "res": res, "size_pct": size_pct, "corner": corner,
                    "detected": detected, "iou": round(best_iou, 2),
                    "conf": round(best_conf, 2), "latency_ms": round(latency_ms, 1),
                })
                status = "HIT" if detected else "MISS"
                print(f"res={res:5d} size={size_pct*100:4.0f}% corner={corner:12s} "
                      f"-> {status}  iou={best_iou:.2f} conf={best_conf:.2f} {latency_ms:.0f}ms")

    print("\n--- Summary by resolution ---")
    for res in RESOLUTIONS:
        rows = [r for r in results_summary if r["res"] == res]
        hits = sum(1 for r in rows if r["detected"])
        avg_lat = sum(r["latency_ms"] for r in rows) / len(rows)
        print(f"res={res}: {hits}/{len(rows)} detected, avg latency {avg_lat:.0f}ms ({1000/avg_lat:.1f} fps)")

    print("\n--- Summary by size ---")
    for size_pct in SIZES_PCT:
        rows = [r for r in results_summary if r["size_pct"] == size_pct]
        hits = sum(1 for r in rows if r["detected"])
        print(f"size={size_pct*100:.0f}%: {hits}/{len(rows)} detected")


if __name__ == "__main__":
    main()
