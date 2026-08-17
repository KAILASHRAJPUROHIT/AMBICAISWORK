"""Per-category 3-angle capture calibration profiles for the RSC 2 multi-shot
workflow (MAIN / ANGLE_1 / ANGLE_2 relative gimbal poses).

Calibration belongs to a CATEGORY (one of the 57 in ornament_code_map.py),
never to an individual tag/item -- 3,000 items must never mean 3,000
calibrations (see the handover spec, rule 31). A tag resolves to a category
via ornament_code_map.category_from_tag_code(); this module is what that
category then resolves to for the three saved physical poses.

Deliberately data-driven against ornament_code_map.CATEGORIES rather than
hardcoded to "57" anywhere -- if the stock master's category count changes,
the dashboard status just reflects a different total instead of anything
breaking (spec rule 11).

Persistence: a single JSON file, same atomic-write pattern as the rest of
this codebase's data/ stores (see capture_tool.py's _atomic_write_json).
Not coupled to Flask/request state so it's usable from tests and any future
caller without spinning up the server.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field

import ornament_code_map as _ocm

BASE = os.path.dirname(os.path.abspath(__file__))
CALIBRATION_PATH = os.path.join(BASE, "data", "capture_calibration.json")

STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STATUS_CALIBRATED = "CALIBRATED"
STATUS_COPIED = "COPIED"
STATUS_COPIED_AND_MODIFIED = "COPIED_AND_MODIFIED"

_SLOTS = ("main", "angle1", "angle2")

_lock = threading.RLock()


@dataclass(frozen=True, slots=True)
class CapturePose:
    yaw: float
    pitch: float
    roll: float

    def as_dict(self) -> dict:
        return {"yaw": self.yaw, "pitch": self.pitch, "roll": self.roll}

    @staticmethod
    def from_dict(d: dict) -> "CapturePose":
        return CapturePose(
            yaw=float(d.get("yaw", 0.0)),
            pitch=float(d.get("pitch", 0.0)),
            roll=float(d.get("roll", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class CategoryCaptureProfile:
    category_key: str
    display_name: str
    status: str
    main: CapturePose
    angle1: CapturePose
    angle2: CapturePose
    derived_from_category_key: str | None = None
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["main"] = self.main.as_dict()
        d["angle1"] = self.angle1.as_dict()
        d["angle2"] = self.angle2.as_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "CategoryCaptureProfile":
        return CategoryCaptureProfile(
            category_key=d["category_key"],
            display_name=d["display_name"],
            status=d["status"],
            main=CapturePose.from_dict(d["main"]),
            angle1=CapturePose.from_dict(d["angle1"]),
            angle2=CapturePose.from_dict(d["angle2"]),
            derived_from_category_key=d.get("derived_from_category_key"),
            version=int(d.get("version", 1)),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
        )


def _atomic_write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _load_raw(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class CalibrationRepository:
    """Thread-safe JSON-backed store. One process-wide instance (see
    `repository` below) mirrors how capture_tool.py's own dedup store works."""

    def __init__(self, path: str = CALIBRATION_PATH):
        self.path = path

    def get_profile(self, category_key: str) -> CategoryCaptureProfile | None:
        with _lock:
            raw = _load_raw(self.path)
        entry = raw.get(category_key)
        if entry is None:
            return None
        return CategoryCaptureProfile.from_dict(entry)

    def save_profile(self, profile: CategoryCaptureProfile) -> None:
        with _lock:
            raw = _load_raw(self.path)
            updated = CategoryCaptureProfile(
                category_key=profile.category_key,
                display_name=profile.display_name,
                status=profile.status,
                main=profile.main,
                angle1=profile.angle1,
                angle2=profile.angle2,
                derived_from_category_key=profile.derived_from_category_key,
                version=profile.version,
                created_at=profile.created_at,
                updated_at=time.time(),
            )
            raw[profile.category_key] = updated.as_dict()
            _atomic_write_json(self.path, raw)

    def copy_profile(self, source_category_key: str, destination_category_key: str) -> CategoryCaptureProfile:
        """Copy-on-use, never a live reference (spec rule 27) -- editing the
        source later must not silently change anything already copied from
        it. derived_from_category_key is kept purely for traceability."""
        source = self.get_profile(source_category_key)
        if source is None:
            raise ValueError(f"No calibrated profile for source category {source_category_key!r}")
        dest_cat = _ocm.BY_KEY.get(destination_category_key)
        display_name = dest_cat.label if dest_cat else destination_category_key
        copied = CategoryCaptureProfile(
            category_key=destination_category_key,
            display_name=display_name,
            status=STATUS_COPIED,
            main=source.main,
            angle1=source.angle1,
            angle2=source.angle2,
            derived_from_category_key=source_category_key,
            version=1,
        )
        self.save_profile(copied)
        return copied

    def delete_profile(self, category_key: str) -> None:
        """Used by RESET (spec rule 44). Archived, not silently unrecoverable
        -- callers that need "removed category" archival semantics (spec rule
        47) should read the profile before deleting if they want to keep it,
        this just removes the active entry."""
        with _lock:
            raw = _load_raw(self.path)
            if category_key in raw:
                del raw[category_key]
                _atomic_write_json(self.path, raw)

    def all_profiles(self) -> dict[str, CategoryCaptureProfile]:
        with _lock:
            raw = _load_raw(self.path)
        return {k: CategoryCaptureProfile.from_dict(v) for k, v in raw.items()}

    def get_calibration_status(self) -> dict:
        """Dashboard summary (spec rule 12) -- driven by ornament_code_map's
        CURRENT category list, not a hardcoded count, so a stock-master
        change is reflected automatically rather than needing a code edit
        (spec rule 11)."""
        profiles = self.all_profiles()
        rows = []
        for cat in _ocm.CATEGORIES:
            profile = profiles.get(cat.key)
            if profile is None:
                rows.append({
                    "category_key": cat.key,
                    "display_name": cat.label,
                    "status": STATUS_NOT_CONFIGURED,
                    "derived_from_category_key": None,
                })
            else:
                rows.append({
                    "category_key": cat.key,
                    "display_name": cat.label,
                    "status": profile.status,
                    "derived_from_category_key": profile.derived_from_category_key,
                })
        configured = sum(1 for r in rows if r["status"] != STATUS_NOT_CONFIGURED)
        return {
            "total": len(rows),
            "configured": configured,
            "remaining": len(rows) - configured,
            "categories": rows,
        }

    def export_backup(self) -> dict:
        """Spec rule 48-49: 57 categories' worth of manual calibration work
        must not live only in one JSON file with no export path."""
        with _lock:
            raw = _load_raw(self.path)
        return {"exported_at": time.time(), "profiles": raw}

    def import_backup(self, backup: dict, *, overwrite: bool = False) -> int:
        profiles = backup.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("Backup payload missing 'profiles' object")
        with _lock:
            raw = _load_raw(self.path)
            imported = 0
            for key, entry in profiles.items():
                if key in raw and not overwrite:
                    continue
                # Validate shape before accepting -- a corrupt/foreign backup
                # must not silently poison the live store.
                CategoryCaptureProfile.from_dict(entry)
                raw[key] = entry
                imported += 1
            _atomic_write_json(self.path, raw)
        return imported


repository = CalibrationRepository()


def pose_angle_difference(a: CapturePose, b: CapturePose) -> float:
    """Full-orientation difference (spec rule 24) -- yaw/pitch/roll combined,
    not yaw-only, since a category may intentionally need a pitch-only
    variation between two of its three views."""
    return (
        (a.yaw - b.yaw) ** 2
        + (a.pitch - b.pitch) ** 2
        + (a.roll - b.roll) ** 2
    ) ** 0.5


MIN_POSE_SEPARATION_DEGREES = 3.0


def check_pose_separation(main: CapturePose, angle1: CapturePose, angle2: CapturePose) -> list[str]:
    """Returns warning strings for any pair of poses that are suspiciously
    close (spec rule 24) -- a soft guard the caller surfaces to the operator
    ("use anyway?"), never a hard block, since some categories may
    legitimately need near-identical yaw with only a small pitch shift."""
    warnings = []
    pairs = (("MAIN", main, "ANGLE_1", angle1),
             ("MAIN", main, "ANGLE_2", angle2),
             ("ANGLE_1", angle1, "ANGLE_2", angle2))
    for name_a, pose_a, name_b, pose_b in pairs:
        diff = pose_angle_difference(pose_a, pose_b)
        if diff < MIN_POSE_SEPARATION_DEGREES:
            warnings.append(f"{name_b} is very close to {name_a} (difference: {diff:.1f}°)")
    return warnings
