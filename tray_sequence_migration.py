"""Dry-run-first planning for a global capture-tray folder sequence.

The live capture service does not import this module.  Merely importing it or
building/rendering a plan performs no writes.  A migration can only be applied
through :func:`apply_plan`, whose two independent safety gates require an exact
confirmation phrase and a caller assertion that capture is stopped.

Folder conventions understood by the planner are the legacy
``<category label> <category-local number>`` form and the new
``<global number> <category label>`` form.  Ambiguous or unnumbered visible
folders make a plan unsafe rather than being guessed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal


APPLY_CONFIRMATION = "APPLY GLOBAL CAPTURE TRAY RENUMBERING"
PRIMARY_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_LEADING_SEQUENCE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")
_TRAILING_SEQUENCE = re.compile(r"^\s*(.+?)\s+(\d+)\s*$")
_SPACE_RUN = re.compile(r"\s+")
_WINDOWS_FORBIDDEN = frozenset('<>:"/\\|?*')


class MigrationError(RuntimeError):
    """Base class for migration planning/application failures."""


class UnsafePlanError(MigrationError):
    """The proposed migration contains an ambiguity or collision."""


class MigrationGateError(MigrationError):
    """An apply safety gate was not explicitly satisfied."""


class StalePlanError(MigrationError):
    """The capture tree changed after the preview was built."""


@dataclass(frozen=True, slots=True)
class TrayCandidate:
    source_name: str
    category_label: str
    received_ns: int
    timestamp_source: Literal["primary_image", "folder"]
    target_name: str


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    root: Path
    trays: tuple[TrayCandidate, ...]
    excluded: tuple[str, ...]
    issues: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "mode": "preview",
            "writes_performed": False,
            "safe_to_apply": self.safe,
            "tray_count": len(self.trays),
            "excluded": list(self.excluded),
            "issues": list(self.issues),
            "mapping": [asdict(tray) for tray in self.trays],
        }


@dataclass(frozen=True, slots=True)
class ApplyResult:
    renamed_directories: int
    state_references_updated: int
    dedup_references_updated: int


def _is_practice_or_hidden(name: str) -> bool:
    stripped = name.strip()
    if not stripped or stripped.startswith((".", "_")):
        return True
    folded = stripped.casefold()
    words = set(re.findall(r"[a-z]+", folded))
    return "practice" in words or "test" in words


def discover_top_level_trays(
    root: str | os.PathLike[str],
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Return visible top-level directories and excluded folder names.

    This is deliberately non-recursive: each top-level directory is one tray,
    while children such as ``_tag_archive`` belong to that tray.
    """

    capture_root = Path(root).resolve()
    if not capture_root.is_dir():
        raise FileNotFoundError(f"Capture root does not exist: {capture_root}")

    trays: list[Path] = []
    excluded: list[str] = []
    for child in sorted(capture_root.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
        if not child.is_dir() or child.is_symlink():
            continue
        if _is_practice_or_hidden(child.name):
            excluded.append(child.name)
        else:
            trays.append(child)
    return tuple(trays), tuple(excluded)


def _is_known_stock_category_label(label: str) -> bool:
    """True if label (case-insensitive) is a real stock_category_map label,
    e.g. "LOCKET 22" -- the gauge suffix on new-taxonomy folders is real
    domain data, not a legacy per-category counter."""
    import stock_category_map as _scm
    return _scm.match_label(label.strip().casefold()) is not None


def derive_category_label(folder_name: str) -> str:
    """Extract a category without guessing between conflicting conventions."""

    leading = _LEADING_SEQUENCE.fullmatch(folder_name)
    trailing = _TRAILING_SEQUENCE.fullmatch(folder_name)
    if leading and trailing:
        # Both patterns match -- e.g. "34 LOCKET 22", where the trailing "22"
        # could be read as a legacy per-category counter OR as the gauge
        # suffix of a real new-taxonomy stock category. A bare regex can't
        # tell those apart; stock_category_map can, since "LOCKET 22" is a
        # real label and "34 LOCKET" is not. Prefer whichever interpretation's
        # remainder is a known label; if both or neither are known, it's
        # genuinely ambiguous and must still be refused.
        leading_known = _is_known_stock_category_label(leading.group(2))
        trailing_known = _is_known_stock_category_label(trailing.group(1))
        if leading_known and not trailing_known:
            trailing = None
        elif trailing_known and not leading_known:
            leading = None
        else:
            raise ValueError(
                "matches both leading-global and trailing-legacy number formats"
            )
    elif not leading and not trailing:
        raise ValueError("has no unambiguous leading or trailing sequence number")

    raw_label = leading.group(2) if leading else trailing.group(1)  # type: ignore[union-attr]
    label = _SPACE_RUN.sub(" ", raw_label).strip()
    if not label:
        raise ValueError("has an empty category label")
    if label.endswith((".", " ")) or any(char in _WINDOWS_FORBIDDEN for char in label):
        raise ValueError("contains a Windows-unsafe category label")
    return label


def _received_timestamp(tray: Path) -> tuple[int, Literal["primary_image", "folder"]]:
    primary_times: list[int] = []
    for child in tray.iterdir():
        if (
            child.is_file()
            and not child.is_symlink()
            and not child.name.startswith((".", "_"))
            and child.suffix.casefold() in PRIMARY_IMAGE_EXTENSIONS
        ):
            primary_times.append(child.stat().st_mtime_ns)
    if primary_times:
        return min(primary_times), "primary_image"
    return tray.stat().st_mtime_ns, "folder"


def build_plan(root: str | os.PathLike[str]) -> MigrationPlan:
    """Build and fully validate a deterministic, gapless rename preview."""

    capture_root = Path(root).resolve()
    directories, excluded = discover_top_level_trays(capture_root)
    issues: list[str] = []
    parsed: list[tuple[Path, str, int, Literal["primary_image", "folder"]]] = []

    source_names: dict[str, str] = {}
    label_spellings: dict[str, str] = {}
    for directory in directories:
        source_key = directory.name.casefold()
        previous_source = source_names.get(source_key)
        if previous_source is not None:
            issues.append(
                f"case-insensitive source collision: {previous_source!r} and {directory.name!r}"
            )
            continue
        source_names[source_key] = directory.name
        try:
            label = derive_category_label(directory.name)
            received_ns, timestamp_source = _received_timestamp(directory)
        except (OSError, ValueError) as exc:
            issues.append(f"unsafe tray label {directory.name!r}: {exc}")
            continue

        label_key = label.casefold()
        previous_label = label_spellings.get(label_key)
        if previous_label is not None and previous_label != label:
            issues.append(
                f"ambiguous category spelling: {previous_label!r} and {label!r}"
            )
        else:
            label_spellings[label_key] = label
        parsed.append((directory, label, received_ns, timestamp_source))

    parsed.sort(key=lambda row: (row[2], row[0].name.casefold(), row[0].name))
    trays = tuple(
        TrayCandidate(
            source_name=directory.name,
            category_label=label,
            received_ns=received_ns,
            timestamp_source=timestamp_source,
            target_name=f"{sequence} {label}",
        )
        for sequence, (directory, label, received_ns, timestamp_source) in enumerate(
            parsed, start=1
        )
    )

    target_names: dict[str, str] = {}
    for tray in trays:
        target_key = tray.target_name.casefold()
        previous_target = target_names.get(target_key)
        if previous_target is not None:
            issues.append(
                f"case-insensitive target collision: {previous_target!r} and {tray.target_name!r}"
            )
        else:
            target_names[target_key] = tray.target_name

    source_keys = {tray.source_name.casefold() for tray in trays}
    all_children = {child.name.casefold(): child.name for child in capture_root.iterdir()}
    for tray in trays:
        target_key = tray.target_name.casefold()
        existing = all_children.get(target_key)
        if existing is not None and target_key not in source_keys:
            issues.append(
                f"target {tray.target_name!r} collides with existing entry {existing!r}"
            )

    return MigrationPlan(
        root=capture_root,
        trays=trays,
        excluded=excluded,
        issues=tuple(dict.fromkeys(issues)),
    )


def render_json(plan: MigrationPlan) -> str:
    """Render a preview without changing the filesystem."""

    return json.dumps(plan.to_dict(), indent=2, sort_keys=True)


def render_text(plan: MigrationPlan) -> str:
    """Render a human-readable preview without changing the filesystem."""

    lines = [
        "CAPTURE TRAY GLOBAL-SEQUENCE PREVIEW",
        f"Root: {plan.root}",
        f"Safe to apply: {'YES' if plan.safe else 'NO'}",
        "Writes performed: NO",
        f"Tray folders: {len(plan.trays)}",
    ]
    if plan.excluded:
        lines.append("Excluded: " + ", ".join(plan.excluded))
    if plan.issues:
        lines.append("Issues:")
        lines.extend(f"  - {issue}" for issue in plan.issues)
    lines.append("Mapping:")
    lines.extend(
        f"  {tray.source_name} -> {tray.target_name} "
        f"[{tray.timestamp_source} {tray.received_ns}]"
        for tray in plan.trays
    )
    return "\n".join(lines)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise MigrationError(f"{label} metadata is missing or unsafe: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"Cannot read {label} metadata {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise MigrationError(f"{label} metadata must contain a JSON object: {path}")
    return data


def _target_for(value: Any, mapping: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    return mapping.get(value.casefold(), value)


def _rewrite_state(data: dict[str, Any], mapping: dict[str, str]) -> tuple[dict[str, Any], int]:
    rewritten = dict(data)
    changed = 0
    for key, value in data.items():
        replacement = _target_for(value, mapping)
        if replacement != value:
            rewritten[key] = replacement
            changed += 1
    return rewritten, changed


def _rewrite_dedup(data: dict[str, Any], mapping: dict[str, str]) -> tuple[dict[str, Any], int]:
    rewritten: dict[str, Any] = {}
    changed = 0
    for tag, record in data.items():
        if isinstance(record, dict):
            record_copy = dict(record)
            old_folder = record_copy.get("folder")
            new_folder = _target_for(old_folder, mapping)
            if new_folder != old_folder:
                record_copy["folder"] = new_folder
                changed += 1
            rewritten[tag] = record_copy
        else:
            rewritten[tag] = record
    return rewritten, changed


def _stage_json(path: Path, data: dict[str, Any], token: str) -> Path:
    staged = path.with_name(f".{path.name}.tray-sequence-{token}.tmp")
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with staged.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return staged


def _atomic_restore(path: Path, payload: bytes, token: str) -> None:
    staged = path.with_name(f".{path.name}.tray-sequence-restore-{token}.tmp")
    with staged.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, path)


def _plan_signature(plan: MigrationPlan) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            tray.source_name,
            tray.category_label,
            tray.received_ns,
            tray.timestamp_source,
            tray.target_name,
        )
        for tray in plan.trays
    )


def _rollback_directories(
    root: Path,
    locations: dict[str, Path],
    token: str,
) -> None:
    staged: dict[str, Path] = {}
    for index, (source_name, current) in enumerate(locations.items(), start=1):
        if not current.exists():
            continue
        rollback_temp = root / f".tray-sequence-rollback-{token}-{index}"
        os.replace(current, rollback_temp)
        staged[source_name] = rollback_temp
    for source_name, temporary in staged.items():
        os.replace(temporary, root / source_name)


def apply_plan(
    plan: MigrationPlan,
    *,
    confirmation: str,
    capture_stopped_assertion: bool,
    state_path: str | os.PathLike[str],
    dedup_path: str | os.PathLike[str],
) -> ApplyResult:
    """Apply a validated plan with two-phase renames and metadata rewrites.

    This function is intentionally not wired to the capture application or
    command-line preview.  The caller must stop capture out-of-band and then
    satisfy both explicit safety gates.
    """

    if confirmation != APPLY_CONFIRMATION:
        raise MigrationGateError(
            f"Exact confirmation required: {APPLY_CONFIRMATION!r}"
        )
    if capture_stopped_assertion is not True:
        raise MigrationGateError("Caller must assert that capture is stopped")
    if not plan.safe:
        raise UnsafePlanError("Refusing unsafe plan: " + "; ".join(plan.issues))

    current = build_plan(plan.root)
    if not current.safe or _plan_signature(current) != _plan_signature(plan):
        raise StalePlanError("Capture tray tree changed after preview; rebuild the plan")

    state = Path(state_path).resolve()
    dedup = Path(dedup_path).resolve()
    if state == dedup:
        raise MigrationError("State and dedup metadata paths must be different")
    state_data = _load_json_object(state, "tray state")
    dedup_data = _load_json_object(dedup, "capture dedup")

    mapping = {
        tray.source_name.casefold(): tray.target_name
        for tray in plan.trays
    }
    new_state, state_changes = _rewrite_state(state_data, mapping)
    new_dedup, dedup_changes = _rewrite_dedup(dedup_data, mapping)
    state_original = state.read_bytes()
    dedup_original = dedup.read_bytes()

    token = uuid.uuid4().hex
    staged_state: Path | None = None
    staged_dedup: Path | None = None
    locations: dict[str, Path] = {}
    metadata_replaced = False
    try:
        staged_state = _stage_json(state, new_state, token)
        staged_dedup = _stage_json(dedup, new_dedup, token)

        changed = [tray for tray in plan.trays if tray.source_name != tray.target_name]
        for index, tray in enumerate(changed, start=1):
            temporary = plan.root / f".tray-sequence-{token}-{index}"
            os.replace(plan.root / tray.source_name, temporary)
            locations[tray.source_name] = temporary
        for tray in changed:
            temporary = locations[tray.source_name]
            target = plan.root / tray.target_name
            os.replace(temporary, target)
            locations[tray.source_name] = target

        os.replace(staged_state, state)
        staged_state = None
        metadata_replaced = True
        os.replace(staged_dedup, dedup)
        staged_dedup = None
    except Exception as exc:
        rollback_errors: list[str] = []
        if metadata_replaced:
            try:
                _atomic_restore(state, state_original, token)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O
                rollback_errors.append(f"state restore failed: {rollback_exc}")
        # The dedup replacement might have succeeded immediately before an
        # unusual later exception, so restoring it unconditionally is safest.
        try:
            if dedup.exists() and dedup.read_bytes() != dedup_original:
                _atomic_restore(dedup, dedup_original, token)
        except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O
            rollback_errors.append(f"dedup restore failed: {rollback_exc}")
        try:
            _rollback_directories(plan.root, locations, token)
        except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O
            rollback_errors.append(f"directory rollback failed: {rollback_exc}")
        detail = f"Migration failed and was rolled back: {exc}"
        if rollback_errors:
            detail += "; " + "; ".join(rollback_errors)
        raise MigrationError(detail) from exc
    finally:
        for staged in (staged_state, staged_dedup):
            if staged is not None:
                try:
                    staged.unlink(missing_ok=True)
                except OSError:
                    pass

    return ApplyResult(
        renamed_directories=sum(
            tray.source_name != tray.target_name for tray in plan.trays
        ),
        state_references_updated=state_changes,
        dedup_references_updated=dedup_changes,
    )


def _preview_cli(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="capture root to inspect (preview only)")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", dest="output_format"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    plan = build_plan(args.root)
    print(render_json(plan) if args.output_format == "json" else render_text(plan))
    return 0 if plan.safe else 2


if __name__ == "__main__":  # pragma: no cover - exercised manually
    raise SystemExit(_preview_cli())
