"""Non-destructive production coverage reset.

The dashboard counts only image files created after the operator's reset
timestamp. Existing catalogue assets remain exactly where they are.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "data" / "coverage_baseline.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def reset_timestamp() -> float:
    try:
        value = json.loads(STATE.read_text(encoding="utf-8")).get("reset_at", 0)
        return float(value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0.0


def include(path: str | os.PathLike[str]) -> bool:
    """True only for an image created after the current production reset."""
    try:
        return os.path.getmtime(path) > reset_timestamp()
    except OSError:
        return False


def count_images_since(root: str | os.PathLike[str]) -> int:
    if not os.path.isdir(root):
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(("_", "."))]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS and include(path):
                total += 1
    return total
