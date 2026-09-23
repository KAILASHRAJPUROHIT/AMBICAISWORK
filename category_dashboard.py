"""Live per-category lifecycle counts for the Operations dashboard."""
from __future__ import annotations

import os
import re
from pathlib import Path

import coverage_baseline
import ornament_code_map as ocm

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_LEADING_NUM = re.compile(r"^\d+\s+(.+)$")


def _count_images(root: str) -> int:
    if not os.path.isdir(root):
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(("_", "."))]
        total += sum(1 for f in filenames if os.path.splitext(f)[1].lower() in _IMG_EXT)
    return total


def _counts_by_tag(root: str, after_reset: bool = False) -> tuple[dict[str, int], dict[str, set[str]]]:
    labels: dict[str, set[str]] = {}
    folders: dict[str, set[str]] = {}
    if not os.path.isdir(root):
        return {}, folders
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(("_", "."))]
        relative = os.path.relpath(dirpath, root)
        top_folder = None if relative == "." else relative.split(os.sep, 1)[0]
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() not in _IMG_EXT:
                continue
            if after_reset and not coverage_baseline.include(os.path.join(dirpath, filename)):
                continue
            resolved = ocm.category_from_tag_code(os.path.splitext(filename)[0])
            if resolved is None:
                continue
            # One catalogue label may temporarily have both legacy PNG and
            # Ornate NX .Jpg files. Count the label once, not each extension.
            labels.setdefault(resolved.key, set()).add(
                os.path.splitext(filename)[0].casefold()
            )
            if top_folder:
                folders.setdefault(resolved.key, set()).add(top_folder)
    return {key: len(values) for key, values in labels.items()}, folders


def _verdict_counts(review_state) -> tuple[dict[str, int], dict[str, int]]:
    approved: dict[str, int] = {}
    rejected: dict[str, int] = {}
    items = review_state.items() if hasattr(review_state, "items") else review_state or ()
    for label, saved in items:
        resolved = ocm.category_from_tag_code(str(label))
        if resolved is None:
            continue
        verdict = saved.get("verdict") if isinstance(saved, dict) else str(saved)
        target = approved if verdict == "approved" else rejected if verdict == "rejected" else None
        if target is not None:
            target[resolved.key] = target.get(resolved.key, 0) + 1
    return approved, rejected


def category_breakdown(capture_root: str, processed_root: str,
                       stock_labels=(), review_state=(), uploaded_root=None,
                       uploaded_labels=()) -> list[dict]:
    """One row per one of the 57 real stock categories: captured count (from
    its numbered capture_intake tray folder) and processed source count from
    the lifecycle ``processed`` root.  Counting output images was incorrect:
    each success can have studio + model files and resetting project memory
    does not delete finished deliverables."""
    captured_by_key, capture_folders = _counts_by_tag(capture_root, after_reset=True)
    processed_by_key, _ = _counts_by_tag(processed_root, after_reset=True)
    uploaded_by_key, _ = _counts_by_tag(str(uploaded_root)) if uploaded_root else ({}, {})
    for label in uploaded_labels or ():
        resolved = ocm.category_from_tag_code(str(label))
        if resolved is not None:
            uploaded_by_key[resolved.key] = uploaded_by_key.get(resolved.key, 0) + 1
    approved_by_key, rejected_by_key = _verdict_counts(review_state)

    stock_by_key: dict[str, int] = {}
    for label in stock_labels or ():
        resolved = ocm.category_from_tag_code(str(label))
        if resolved is not None:
            stock_by_key[resolved.key] = stock_by_key.get(resolved.key, 0) + 1

    rows = []
    for cat in ocm.CATEGORIES:
        folders = sorted(capture_folders.get(cat.key, ()))
        processed = processed_by_key.get(cat.key, 0)
        # Approved raws leave capture_intake/ and move to processed/. Coverage
        # must therefore count both lifecycle locations; otherwise a fully
        # approved category appears to lose coverage as work completes.
        captured = captured_by_key.get(cat.key, 0) + processed
        approved = approved_by_key.get(cat.key, 0)
        rejected = rejected_by_key.get(cat.key, 0)
        uploaded = uploaded_by_key.get(cat.key, 0)
        stock_total = stock_by_key.get(cat.key, 0)
        rows.append({
            "key": cat.key,
            "label": cat.label,
            "prefix": cat.prefix,
            "folder": folders[-1] if folders else None,
            "folders": folders,
            "captured": captured,
            "processed": processed,
            "approved": approved,
            "rejected": rejected,
            "uploaded": uploaded,
            "stock_total": stock_total,
        })
    return rows


def missing_labels(category_key: str, capture_root: str, processed_root: str,
                    output_root: str, stock_labels=()) -> list[str]:
    """Stock tags for one category that have never been captured.

    "Captured" means present in capture_intake, processed, OR output --
    matching the owner's rule (2026-09-02) that a tag in any of those three
    is already shot and must never be recaptured. A tag only counts as
    missing when it is in none of them.

    Returns tag codes in their original "/" form (e.g. "LR22/104"), sorted
    numerically by the trailing number so the download reads in tray order
    rather than lexical order (LR22/9 before LR22/10).
    """
    import pipeline_counts

    captured_safe = (
        pipeline_counts._labels(Path(capture_root))
        | pipeline_counts._labels(Path(processed_root))
        | pipeline_counts._labels(Path(output_root))
    )
    captured_safe = {label.upper() for label in captured_safe}

    missing = []
    for tag_code in stock_labels or ():
        resolved = ocm.category_from_tag_code(str(tag_code))
        if resolved is None or resolved.key != category_key:
            continue
        safe = re.sub(r'[/\\:*?"<>|]', "_", str(tag_code)).strip().upper()
        if safe not in captured_safe:
            missing.append(str(tag_code))

    def _sort_key(tag_code: str):
        match = re.search(r"(\d+)\s*$", tag_code)
        return (int(match.group(1)) if match else 0, tag_code)

    return sorted(set(missing), key=_sort_key)
