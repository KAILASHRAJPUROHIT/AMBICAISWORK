"""Per-category shot plans -- server-side view (2026-09-25).

Single source of truth for which stock categories are NOT photographed, so
they drop out of the shoot schedule (pending-capture list, recommendations,
coverage table, missing-tag downloads) automatically.

The plan itself lives in config/shot_plans.json so it can be edited without
touching code. The Android app carries its own compiled copy of the same
plan (ShotPlans.kt) -- keep the two in step.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config" / "shot_plans.json"

_DEFAULT: dict[str, Any] = {
    "no_shoot_prefixes": ["gold_coin_"],
    "no_shoot_keys": ["haar_chain_22"],
}

_cache: dict[str, Any] = {"mtime": None, "data": _DEFAULT}


def _load() -> dict[str, Any]:
    try:
        mtime = CONFIG_PATH.stat().st_mtime_ns
    except OSError:
        return _DEFAULT
    if _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = _DEFAULT
    _cache["mtime"] = mtime
    _cache["data"] = data
    return data


def category_key(label: str | None) -> str:
    """'Gold Coin 0.025 M' -> 'gold_coin_0_025_m'; 'MSS-SHORT 20' -> 'mss_short_20'."""
    return re.sub(r"[^a-z0-9]+", "_", str(label or "").lower()).strip("_")


def is_no_shoot_key(key: str | None) -> bool:
    key = category_key(key)
    if not key:
        return False
    data = _load()
    if key in {category_key(k) for k in data.get("no_shoot_keys", [])}:
        return True
    return any(key.startswith(category_key(p) + "_") or key == category_key(p)
               for p in data.get("no_shoot_prefixes", []))


def is_no_shoot_label(label: str | None) -> bool:
    return is_no_shoot_key(category_key(label))
