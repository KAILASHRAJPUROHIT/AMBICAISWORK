"""Category -> reviewed background asset path resolution.

A handful of processing categories (Wati being the first — see
ornament_placement.background_asset_category's docstring) don't have their
own dedicated background art yet and are deliberately routed to reuse a
different, already-reviewed category's background instead. This module is
the single place that applies that substitution, so generation
(resolve_category_bg_path, used by the actual catalogue pipeline) and the
live "/img/bg/..." preview route always agree on which asset a category
really uses — nothing here deletes, renames, or overwrites the original
literally-named file; both stay on disk.
"""
from __future__ import annotations

import os
from pathlib import Path

import ornament_placement

BASE = os.path.dirname(os.path.abspath(__file__))
BACKGROUNDS_DIR = Path(BASE) / "backgrounds"


def resolve_category_bg_path(category: str, theme: str) -> Path | None:
    """Reviewed background file for `category` under `theme` (e.g. "Regular"),
    applying any category substitution — or None if no such file exists."""
    asset_category = ornament_placement.background_asset_category(category)
    candidate = BACKGROUNDS_DIR / theme / f"bg_{asset_category}.jpg"
    return candidate if candidate.is_file() else None
