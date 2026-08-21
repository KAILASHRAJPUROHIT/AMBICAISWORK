"""Canonical directory layout for the catalogue pipeline.

This module is deliberately standalone for the first migration stage.  Existing
production modules do not import it yet, so importing it cannot change the live
capture or processing behaviour.

The target layout is:

    capture/       immutable master capture archive
    processing/    captured items waiting to be processed
    processed/     successfully processed source items
    output/        final deliverables, organised by item variety
    needs_review/  generated items that require a human decision
    rejected/      items that failed processing
    backgrounds/   background themes and variants
    models/        model poses and variants

Legacy-to-target migration map (documentation only; no migration is performed):

    capture_intake/  -> capture/
    input/           -> processing/
    processing/      -> processing/
    output_aradhana/ -> output/
    _needs_review/   -> needs_review/
    Reject/          -> rejected/
    backgrounds/     -> backgrounds/
    models/          -> models/

There is no established legacy root corresponding to ``processed/``.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


BASE = os.path.dirname(os.path.abspath(__file__))
LEGACY_CAPTURE_INTAKE_DIR = os.path.join(BASE, "capture_intake")


def _configured_root(environment_variable: str, default_name: str) -> str:
    """Resolve one target root, allowing an environment override.

    Relative overrides are resolved from ``BASE`` so every resulting path is
    deterministic and independent of the process working directory.
    """

    configured = os.environ.get(environment_variable, "").strip()
    if not configured:
        configured = default_name
    configured = os.path.expandvars(os.path.expanduser(configured))
    if not os.path.isabs(configured):
        configured = os.path.join(BASE, configured)
    return os.path.normpath(os.path.abspath(configured))


CAPTURE_DIR = _configured_root("AJ_CAPTURE_DIR", "capture")
PROCESSING_DIR = _configured_root("AJ_PROCESSING_DIR", "processing")
PROCESSED_DIR = _configured_root("AJ_PROCESSED_DIR", "processed")
OUTPUT_DIR = _configured_root("AJ_OUTPUT_DIR", "output")
NEEDS_REVIEW_DIR = _configured_root("AJ_NEEDS_REVIEW_DIR", "needs_review")
REJECTED_DIR = _configured_root("AJ_REJECTED_DIR", "rejected")
BACKGROUNDS_DIR = _configured_root("AJ_BACKGROUNDS_DIR", "backgrounds")
MODELS_DIR = _configured_root("AJ_MODELS_DIR", "models")


ROOTS_BY_NAME = {
    "capture": CAPTURE_DIR,
    "processing": PROCESSING_DIR,
    "processed": PROCESSED_DIR,
    "output": OUTPUT_DIR,
    "needs_review": NEEDS_REVIEW_DIR,
    "rejected": REJECTED_DIR,
    "backgrounds": BACKGROUNDS_DIR,
    "models": MODELS_DIR,
}

ROOTS = tuple(ROOTS_BY_NAME.values())

CURRENT_TO_TARGET = {
    "capture_intake": "capture",
    "input": "processing",
    "processing": "processing",
    "output_aradhana": "output",
    "_needs_review": "needs_review",
    "Reject": "rejected",
}


def ensure_dirs(roots: Iterable[str] | None = None) -> None:
    """Create missing target roots without modifying their contents.

    Calling this function repeatedly is safe.  In particular, it never scans,
    renames, moves, or creates anything inside the legacy ``capture_intake/``
    tree.  The optional argument exists for isolated tests and future staging;
    production callers should use the configured target roots.
    """

    legacy_capture = os.path.normcase(os.path.realpath(LEGACY_CAPTURE_INTAKE_DIR))
    for root in ROOTS if roots is None else roots:
        candidate = os.path.normcase(os.path.realpath(root))
        try:
            inside_legacy_capture = (
                os.path.commonpath((legacy_capture, candidate)) == legacy_capture
            )
        except ValueError:
            # Different Windows drives cannot contain one another.
            inside_legacy_capture = False
        if inside_legacy_capture:
            raise ValueError(
                f"Refusing to create or modify a directory under the live "
                f"capture_intake tree: {root}"
            )
        os.makedirs(root, exist_ok=True)
