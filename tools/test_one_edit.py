"""Run ONE item through the current catalogue prompt and score the result.

    py tools\test_one_edit.py LR22_95
    py tools\test_one_edit.py LR22_95 --category ladies_ring_22

Writes to _prompt_test/new/<ITEM>.jpg and leaves output/ untouched, so the
previous render stays available as a before/after baseline.
"""
import argparse, sys, time, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import azure_catalogue_engine as engine  # noqa: E402


def find_source(item: str) -> Path:
    hits = sorted(glob.glob(str(ROOT / "processed" / "*" / f"{item}.jpg")))
    if not hits:
        raise SystemExit(f"No stitched source found for {item} under processed/")
    return Path(hits[0])


def score(path: Path) -> tuple[float, float] | None:
    """Same two measures used to rank the problem items: percentage of the
    piece rendered near-black (reflections/blobs) and mean high-frequency
    detail on it (surface noise)."""
    try:
        import cv2, numpy as np
    except ImportError:
        return None
    im = cv2.imread(str(path))
    if im is None:
        return None
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    subject = gray < 235
    if subject.sum() < 2000:
        return None
    value = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)[:, :, 2]
    dark = ((value < 70) & subject).sum() / subject.sum() * 100
    noise = float(abs(cv2.Laplacian(gray, cv2.CV_64F))[subject].mean())
    return dark, noise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("item")
    ap.add_argument("--category", default="ladies_ring_22")
    args = ap.parse_args()

    source = find_source(args.item)
    out = ROOT / "_prompt_test" / "new" / f"{args.item}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)

    import prompt_governance
    if not prompt_governance.approval_status()["approved"]:
        raise SystemExit("Prompt is not approved. Approve it before testing.")

    print(f"source   {source}")
    started = time.time()
    engine.generate(source, out, category=args.category)
    print(f"rendered {out}  ({time.time() - started:.0f}s)")

    previous = sorted(glob.glob(str(ROOT / "output" / "*" / f"{args.item}.jpg")))
    before = score(Path(previous[0])) if previous else None
    after = score(out)
    if after:
        print(f"\n{'':10}{'dark%':>8}{'noise':>9}")
        if before:
            print(f"{'before':10}{before[0]:8.1f}{before[1]:9.1f}")
        print(f"{'after':10}{after[0]:8.1f}{after[1]:9.1f}")
        if not before:
            print("(no previous render found to compare against)")


if __name__ == "__main__":
    main()
