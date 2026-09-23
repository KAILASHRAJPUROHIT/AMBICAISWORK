"""One definition of the pipeline's numbers, used by every surface.

Agreed with the catalogue owner 2026-09-02:

    output/                     -> FINALISED (done)
    capture_intake/             -> not processed, PLUS rejected items sent back
    processed/ + capture_intake -> everything captured so far

The old counters disagreed with this: `captured_total` counted capture_intake
alone, so items that had been processed silently stopped being "captured" and
the headline total went DOWN as work progressed.

capture_intake holds two different situations that must be flagged apart: an
item never processed yet, and one whose delivery was rejected and whose raw
master came back for rework. They look identical on disk, so the split comes
from the review verdict.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _labels(root: Path, since: float = 0.0) -> set[str]:
    """Item labels under `root`. Hidden/underscore folders are skipped, so
    .multi_angle_sources raws and _superseded archives never inflate a count.
    Sidecars (_1/_2/_studs/_detail) collapse onto their item."""
    import review_queue
    found: set[str] = set()
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(("_", "."))]
        for name in filenames:
            if name.startswith("."):
                continue              # in-flight delivery temp, not an item
            if Path(name).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            path = os.path.join(dirpath, name)
            try:
                if since and os.path.getmtime(path) <= since:
                    continue
            except OSError:
                continue
            found.add(review_queue._label_from_path(name))
    return found


def counts(
    apply_baseline: bool = True,
    *,
    capture_root=None,
    processed_root=None,
    output_root=None,
    rejected_root=None,
) -> dict:
    """Roots default to this installation's, but are injectable so callers
    that are already parameterised by root (and their tests) stay honest."""
    import coverage_baseline
    import review_queue

    # The operator's coverage reset belongs to THIS installation's folders.
    # Applying it to injected roots silently filtered everything out when a
    # caller passed directories whose files predate the reset (2026-09-02).
    injected = any((capture_root, processed_root, output_root, rejected_root))
    since = coverage_baseline.reset_timestamp() if (apply_baseline and not injected) else 0.0
    done = _labels(Path(output_root or BASE / "output"), since)
    intake = _labels(Path(capture_root or BASE / "capture_intake"), since)
    processed = _labels(Path(processed_root or BASE / "processed"), since)

    # Which intake items are there because they were REJECTED, rather than
    # because they have not been processed yet.
    verdicts = review_queue._load_state()
    rejected_labels = {
        label for label in intake
        if (verdicts.get(label) or {}).get("verdict") == review_queue.REJECTED
    }
    rejected_labels |= intake & _labels(Path(rejected_root or BASE / "rejected"), since)
    awaiting = intake - rejected_labels

    return {
        "done": len(done),                       # output/ -- finalised
        "captured_total": len(processed | intake),  # everything shot so far
        "in_intake": len(intake),
        "awaiting_processing": len(awaiting),    # never processed
        "rejected_for_rework": len(rejected_labels),
        "processed": len(processed),
        "baseline_applied": bool(since),
    }
