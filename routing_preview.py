"""Shared, read-only Manual/Auto routing preview service."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import item_routing
import model_engine
import stock_catalog


_ALLOWED_OVERRIDE_FIELDS = frozenset(
    {
        "background_theme",
        "background_image",
        "model_theme",
        "model_group",
        "model_pose",
        "model_image",
    }
)
_PATH_OVERRIDE_FIELDS = frozenset({"background_image", "model_image"})
_COMPONENT_OVERRIDE_FIELDS = frozenset(
    {"background_theme", "model_theme", "model_group"}
)
_ALLOWED_MODEL_POSES = frozenset(
    {"face", "neck", "hand", "wrist", "feet", "waist", "bridal"}
)
_INVALID_WINDOWS_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class RoutingPreviewValidationError(ValueError):
    """The caller supplied an invalid category or override contract."""


class RoutingPreviewTagNotFound(LookupError):
    """The authoritative stock catalogue does not contain the requested tag."""


class RoutingPreviewConflict(RuntimeError):
    """Authoritative routing could not resolve a complete compatible asset set."""


class RoutingPreviewService:
    """Refresh stock and resolve exactly the same routing for Manual and Auto."""

    def __init__(
        self,
        *,
        stock: stock_catalog.StockCatalogCache | None = None,
        router: item_routing.ItemRouter | None = None,
    ):
        self.stock = stock or stock_catalog.StockCatalogCache()
        self.router = router or item_routing.ItemRouter.from_configured_manifest()

    def preview(
        self,
        *,
        tag_label: str,
        ornament_type: str,
        manual_override: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        label = _validated_label(tag_label)
        ornament = _validated_ornament(ornament_type)
        override = _validated_override(manual_override)

        try:
            self.stock.refresh()
        except Exception as exc:
            raise RoutingPreviewConflict(
                "Stock catalogue refresh failed; authoritative routing cannot be confirmed"
            ) from exc
        record = self.stock.lookup(label)
        if record is None:
            raise RoutingPreviewTagNotFound(
                f"Tag {label!r} is not present in the validated stock workbook"
            )

        try:
            decision = self.router.route(
                record,
                ornament,
                manual_override=override or None,
            )
        except (item_routing.RoutingError, OSError) as exc:
            # ItemRouter's diagnostic can contain an absolute configured path.
            # Keep the API safe while still making the failed routing state
            # explicit to the operator.
            raise RoutingPreviewConflict(
                f"No complete compatible asset route exists for "
                f"{ornament!r} / {record.routing_variety!r}"
            ) from exc

        background = _safe_existing_relative(
            decision.background_path, self.router.backgrounds_root
        )
        candidates = [
            _safe_existing_relative(candidate, self.router.models_root)
            for candidate in decision.model_candidates
        ]
        if not candidates:
            raise RoutingPreviewConflict(
                f"No compatible model candidate exists for {ornament!r}"
            )
        return {
            "tag_label": record.label_no,
            "ornament_type": decision.ornament_type,
            "variety": decision.variety,
            "output_bucket": decision.output_bucket,
            "output": {
                "studio": _safe_relative(
                    decision.studio_output, self.router.output_root
                ),
                "model": _safe_relative(
                    decision.model_output, self.router.output_root
                ),
            },
            "background": {
                "theme": decision.background_theme,
                "path": background,
            },
            "model": {
                "theme": decision.model_theme,
                "group": decision.model_group,
                "pose": decision.model_pose,
                "candidates": candidates,
            },
            "manually_overridden": decision.manually_overridden,
        }


def _validated_label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingPreviewValidationError("tag_label must be a non-empty string")
    if value != value.strip():
        raise RoutingPreviewValidationError(
            "tag_label must not contain surrounding whitespace"
        )
    return value


def _validated_ornament(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingPreviewValidationError(
            "ornament_type must be a non-empty string"
        )
    ornament = re.sub(r"[\s-]+", "_", value.strip().casefold())
    ornament = re.sub(r"[^a-z0-9_]", "", ornament).strip("_")
    if ornament not in model_engine.CATEGORY_TEMPLATES:
        raise RoutingPreviewValidationError(
            f"Unsupported ornament_type: {value!r}"
        )
    return ornament


def _validated_override(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RoutingPreviewValidationError("manual_override must be an object")
    unknown = set(value) - _ALLOWED_OVERRIDE_FIELDS
    if unknown:
        raise RoutingPreviewValidationError(
            f"Unknown manual override field(s): {', '.join(sorted(unknown))}"
        )
    override: dict[str, str] = {}
    for field, raw in value.items():
        if not isinstance(raw, str) or not raw.strip() or raw != raw.strip():
            raise RoutingPreviewValidationError(
                f"Manual override {field!r} must be a non-empty trimmed string"
            )
        if field in _PATH_OVERRIDE_FIELDS:
            _validated_relative_asset_path(raw, field)
        elif field in _COMPONENT_OVERRIDE_FIELDS:
            _validated_component(raw, field)
        elif field == "model_pose" and raw.casefold() not in _ALLOWED_MODEL_POSES:
            raise RoutingPreviewValidationError(
                f"Unsupported model_pose override: {raw!r}"
            )
        override[field] = raw.casefold() if field == "model_pose" else raw
    return override


def _validated_relative_asset_path(value: str, field: str) -> None:
    relative = Path(value)
    if (
        relative.is_absolute()
        or bool(relative.drive)
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(
            _INVALID_WINDOWS_COMPONENT.search(part) or part.rstrip(" .") != part
            for part in relative.parts
        )
    ):
        raise RoutingPreviewValidationError(
            f"Manual override {field!r} must be a root-confined relative path"
        )


def _validated_component(value: str, field: str) -> None:
    component = Path(value)
    if (
        component.is_absolute()
        or bool(component.drive)
        or len(component.parts) != 1
        or value in {".", ".."}
        or _INVALID_WINDOWS_COMPONENT.search(value)
        or value.rstrip(" .") != value
    ):
        raise RoutingPreviewValidationError(
            f"Manual override {field!r} must be one safe path component"
        )


def _safe_existing_relative(path: Path, root: Path) -> str:
    resolved = Path(path).resolve()
    base = Path(root).resolve()
    if not resolved.is_file():
        raise RoutingPreviewConflict("A configured routing asset is missing")
    return _relative_inside(resolved, base)


def _safe_relative(path: Path, root: Path) -> str:
    return _relative_inside(Path(path).resolve(), Path(root).resolve())


def _relative_inside(path: Path, root: Path) -> str:
    if path != root and root not in path.parents:
        raise RoutingPreviewConflict("A resolved route escapes its configured root")
    relative = path.relative_to(root)
    if not relative.parts:
        raise RoutingPreviewConflict("A resolved route does not identify an item")
    return relative.as_posix()
