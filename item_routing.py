"""Resolve variety-aware output paths, backgrounds, and model references.

Rules are deliberately layered and deterministic::

    explicit manual override
    ornament + exact variety rule
    ornament + GENERAL rule
    existing ornament default

Blank workbook varieties resolve as ``GENERAL``.  Structured asset layouts are
preferred, while the original ``backgrounds/<theme>/bg_<ornament>.jpg`` and
zone-named model library remain supported as safe fallbacks.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import model_engine
import paths
import stock_excel


ROUTING_MANIFEST_ENV = "AJ_ROUTING_MANIFEST"
_INVALID_PATH_CHARS = re.compile(r'[\\/:*?"<>|]')
_MODEL_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_MODEL_ZONE_KEYWORDS = {
    "face": ("ear", "face"),
    "neck": ("neck", "haar"),
    "hand": ("hand",),
    "wrist": ("wrist",),
    "feet": ("feet", "ankle"),
    "waist": ("waist",),
    "bridal": ("bridal",),
}
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


class RoutingError(RuntimeError):
    """A routing policy or asset reference is invalid."""


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    tag_code: str
    ornament_type: str
    variety: str
    output_bucket: str
    studio_output: Path
    model_output: Path
    background_theme: str
    background_path: Path
    model_theme: str
    model_group: str
    model_pose: str
    model_candidates: tuple[Path, ...]
    model_image: Path | None
    manually_overridden: bool

    @property
    def ready(self) -> bool:
        return (
            self.background_path.is_file()
            and bool(self.model_candidates or self.model_image)
        )


@dataclass(frozen=True, slots=True)
class VarietyOutputPaths:
    variety: str
    output_bucket: str
    studio_output: Path
    model_output: Path


def variety_output_paths(
    record: stock_excel.StockRecord,
    ornament_type: str,
    *,
    output_root: str | os.PathLike[str] = paths.OUTPUT_DIR,
) -> VarietyOutputPaths:
    """Resolve successful deliverables without inspecting generation assets.

    Layout is ``output_root/<category>/<tag>.jpg`` — category is the ornament
    type (e.g. ``ladies_rings``). Flat by operator decision (2026-08-06): the
    deliverables are uploaded to the app and website from one folder per
    category, and a per-variety subfolder only scattered a category's images
    across directories that nothing downstream consumed.

    ``variety`` and ``output_bucket`` are still resolved and returned — the
    routing decision and its preview report them, and the stock workbook
    remains the authority on which variety an item belongs to. The variety
    simply no longer decides where the file lands.
    """

    variety = record.routing_variety
    output_bucket = _safe_component(variety)
    category_bucket = _safe_component(ornament_type)
    tag_name = _safe_component(record.label_no)
    output_dir = Path(output_root) / category_bucket
    return VarietyOutputPaths(
        variety=variety,
        output_bucket=output_bucket,
        studio_output=output_dir / f"{tag_name}.jpg",
        model_output=output_dir / f"{tag_name}_2.jpg",
    )


class ItemRouter:
    """Resolve one stock record against reviewed rules and real assets."""

    def __init__(
        self,
        *,
        output_root: str | os.PathLike[str] = paths.OUTPUT_DIR,
        backgrounds_root: str | os.PathLike[str] = paths.BACKGROUNDS_DIR,
        models_root: str | os.PathLike[str] = paths.MODELS_DIR,
        manifest: Mapping[str, Any] | None = None,
    ):
        self.output_root = Path(output_root)
        self.backgrounds_root = Path(backgrounds_root)
        self.models_root = Path(models_root)
        self.manifest = _validate_manifest(manifest or {})

    @classmethod
    def from_configured_manifest(cls, **kwargs):
        configured = os.environ.get(ROUTING_MANIFEST_ENV, "").strip()
        manifest = load_routing_manifest(configured) if configured else {}
        return cls(manifest=manifest, **kwargs)

    def route(
        self,
        record: stock_excel.StockRecord,
        ornament_type: str,
        *,
        manual_override: Mapping[str, str] | None = None,
    ) -> RoutingDecision:
        ornament = _normalise_ornament_type(ornament_type)
        variety = record.routing_variety
        outputs = variety_output_paths(record, ornament, output_root=self.output_root)

        profile = _general_profile(ornament)
        profile.update(self.manifest["general_by_ornament"].get(ornament, {}))
        variety_rules = self.manifest["by_ornament_variety"].get(ornament, {})
        profile.update(variety_rules.get(stock_excel.GENERAL_VARIETY, {}))
        if variety != stock_excel.GENERAL_VARIETY:
            profile.update(variety_rules.get(_normalise_variety_key(variety), {}))

        manually_overridden = bool(manual_override)
        if manual_override:
            unknown = set(manual_override) - _ALLOWED_OVERRIDE_FIELDS
            if unknown:
                raise RoutingError(
                    f"Unknown manual routing field(s): {', '.join(sorted(unknown))}"
                )
            profile.update(
                {
                    key: str(value).strip()
                    for key, value in manual_override.items()
                    if str(value).strip()
                }
            )

        theme = profile["background_theme"]
        if profile.get("background_image"):
            background_path = _resolve_inside(
                self.backgrounds_root, Path(profile["background_image"])
            )
            if not background_path.is_file():
                raise RoutingError(
                    f"Configured background image does not exist: {background_path}"
                )
        else:
            background_path = _resolve_background(
                self.backgrounds_root, theme, ornament, variety
            )

        model_theme = profile.get("model_theme", "")
        model_group = profile["model_group"]
        model_pose = profile["model_pose"]
        model_image = None
        if profile.get("model_image"):
            model_image = _resolve_inside(
                self.models_root, Path(profile["model_image"])
            )
            if not model_image.is_file():
                raise RoutingError(f"Configured model image does not exist: {model_image}")
            model_candidates = (model_image,)
        else:
            model_candidates = _model_candidates(
                self.models_root,
                model_theme,
                model_group,
                ornament,
                model_pose,
                variety,
            )
            if not model_candidates:
                themed_group = f"{model_theme}/{model_group}" if model_theme else model_group
                raise RoutingError(
                    f"No model assets for ornament {ornament!r}, variety {variety!r}, "
                    f"group {themed_group!r}, and pose {model_pose!r}"
                )

        return RoutingDecision(
            tag_code=record.label_no,
            ornament_type=ornament,
            variety=variety,
            output_bucket=outputs.output_bucket,
            studio_output=outputs.studio_output,
            model_output=outputs.model_output,
            background_theme=theme,
            background_path=background_path,
            model_theme=model_theme,
            model_group=model_group,
            model_pose=model_pose,
            model_candidates=model_candidates,
            model_image=model_image,
            manually_overridden=manually_overridden,
        )


def load_routing_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Routing manifest does not exist: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RoutingError(f"Routing manifest is unreadable: {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RoutingError("Routing manifest root must be an object")
    return _validate_manifest(raw)


def _validate_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(raw) - {"version", "general_by_ornament", "by_ornament_variety"}
    if unknown:
        raise RoutingError(f"Unknown manifest section(s): {', '.join(sorted(unknown))}")
    version = raw.get("version", 1)
    if version != 1:
        raise RoutingError(f"Unsupported routing manifest version: {version!r}")
    general = _normalise_rule_map(raw.get("general_by_ornament", {}), ornament=True)
    by_variety = _normalise_variety_rule_map(raw.get("by_ornament_variety", {}))
    return {
        "version": 1,
        "general_by_ornament": general,
        "by_ornament_variety": by_variety,
    }


def _normalise_rule_map(value: Any, *, ornament: bool) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping):
        raise RoutingError("Routing rule sections must be objects")
    normalised = {}
    for raw_key, raw_rule in value.items():
        key = _normalise_ornament_type(str(raw_key))
        if not key:
            raise RoutingError("Routing rule keys cannot be blank")
        if not isinstance(raw_rule, Mapping):
            raise RoutingError(f"Routing rule {raw_key!r} must be an object")
        unknown = set(raw_rule) - _ALLOWED_OVERRIDE_FIELDS
        if unknown:
            raise RoutingError(
                f"Unknown field(s) in rule {raw_key!r}: "
                f"{', '.join(sorted(unknown))}"
            )
        rule = {
            field: str(raw_value).strip()
            for field, raw_value in raw_rule.items()
            if str(raw_value).strip()
        }
        normalised[key] = rule
    return normalised


def _normalise_variety_rule_map(
    value: Any,
) -> dict[str, dict[str, dict[str, str]]]:
    if not isinstance(value, Mapping):
        raise RoutingError("by_ornament_variety must be an object")
    normalised: dict[str, dict[str, dict[str, str]]] = {}
    for raw_ornament, raw_varieties in value.items():
        ornament = _normalise_ornament_type(str(raw_ornament))
        if not isinstance(raw_varieties, Mapping):
            raise RoutingError(
                f"Variety rules for {raw_ornament!r} must be an object"
            )
        rules: dict[str, dict[str, str]] = {}
        for raw_variety, raw_rule in raw_varieties.items():
            variety = _normalise_variety_key(str(raw_variety))
            if not isinstance(raw_rule, Mapping):
                raise RoutingError(
                    f"Routing rule {raw_ornament!r}/{raw_variety!r} must be an object"
                )
            unknown = set(raw_rule) - _ALLOWED_OVERRIDE_FIELDS
            if unknown:
                raise RoutingError(
                    f"Unknown field(s) in rule {raw_ornament!r}/{raw_variety!r}: "
                    f"{', '.join(sorted(unknown))}"
                )
            rules[variety] = {
                field: str(raw_value).strip()
                for field, raw_value in raw_rule.items()
                if str(raw_value).strip()
            }
        normalised[ornament] = rules
    return normalised


def _general_profile(ornament: str) -> dict[str, str]:
    templates = model_engine.get_templates(ornament)
    first_model = (templates.get("models") or ["F1"])[0]
    if first_model.startswith("M"):
        group = "male"
    elif first_model.startswith("K"):
        group = "kids"
    else:
        group = "female"
    if ornament == "silver":
        theme = "Silver"
    elif ornament == "diamond":
        theme = "Modern Diamond"
    else:
        theme = "Regular"
    return {
        "background_theme": theme,
        "model_theme": "",
        "model_group": group,
        "model_pose": str(templates.get("zone") or "neck"),
    }


def _resolve_background(
    backgrounds_root: Path,
    theme: str,
    ornament: str,
    variety: str,
) -> Path:
    from ornament_placement import background_asset_category

    theme_root = _resolve_inside(backgrounds_root, Path(theme))
    asset_ornament = background_asset_category(ornament)
    variety_component = _safe_component(_normalise_variety_key(variety))
    file_name = f"bg_{asset_ornament}.jpg"
    candidates = [
        theme_root / asset_ornament / variety_component / file_name,
        theme_root / asset_ornament / f"bg_{asset_ornament}_{variety_component}.jpg",
        theme_root / f"bg_{asset_ornament}_{variety_component}.jpg",
    ]
    if variety != stock_excel.GENERAL_VARIETY:
        candidates.append(theme_root / asset_ornament / stock_excel.GENERAL_VARIETY / file_name)
    candidates.extend(
        [
            theme_root / asset_ornament / file_name,
            theme_root / file_name,
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    searched = ", ".join(str(path) for path in candidates)
    raise RoutingError(
        f"No background asset for ornament {ornament!r}, variety {variety!r}, "
        f"and theme {theme!r}. Searched: {searched}"
    )


def _model_candidates(
    models_root: Path,
    model_theme: str,
    model_group: str,
    ornament: str,
    model_pose: str,
    variety: str,
) -> tuple[Path, ...]:
    group_relative = Path(model_theme) / model_group if model_theme else Path(model_group)
    group_root = _resolve_inside(models_root, group_relative)
    if not group_root.is_dir():
        return ()

    pose_root = group_root / ornament / model_pose
    variety_component = _safe_component(_normalise_variety_key(variety))
    structured_roots = [pose_root / variety_component]
    if variety != stock_excel.GENERAL_VARIETY:
        structured_roots.append(pose_root / stock_excel.GENERAL_VARIETY)
    structured_roots.append(pose_root)
    for structured_root in structured_roots:
        candidates = _image_files_directly_in(structured_root)
        if candidates:
            return candidates

    # Backward compatibility is restricted to files whose names identify the
    # requested pose.  Zone-agnostic images must not silently replace a
    # configured ornament/pose.
    candidates = []
    for path in group_root.rglob("*"):
        if (
            path.is_file()
            and path.suffix.casefold() in _MODEL_IMAGE_EXTENSIONS
            and not any(part.startswith("_") for part in path.relative_to(group_root).parts)
            and _model_zone(path.name) == model_pose
        ):
            candidates.append(path.resolve())
    return tuple(sorted(candidates))


def _image_files_directly_in(directory: Path) -> tuple[Path, ...]:
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(
            path.resolve()
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.casefold() in _MODEL_IMAGE_EXTENSIONS
            and not path.name.startswith("_")
        )
    )


def _model_zone(file_name: str) -> str | None:
    stem = Path(file_name).stem.casefold()
    for zone, keywords in _MODEL_ZONE_KEYWORDS.items():
        if any(keyword in stem for keyword in keywords):
            return zone
    return None


def _resolve_inside(root: Path, relative: Path) -> Path:
    if relative.is_absolute():
        raise RoutingError(f"Asset path must be relative: {relative}")
    base = root.resolve()
    resolved = (base / relative).resolve()
    if resolved != base and base not in resolved.parents:
        raise RoutingError(f"Asset path escapes its configured root: {relative}")
    return resolved


def _normalise_ornament_type(value: str) -> str:
    normalised = re.sub(r"[\s-]+", "_", value.strip().casefold())
    normalised = re.sub(r"[^a-z0-9_]", "", normalised).strip("_")
    if not normalised:
        raise RoutingError("ornament_type is required")
    return normalised


def _normalise_variety_key(value: str) -> str:
    normalised = re.sub(r"\s+", " ", value.strip()).upper()
    if not normalised:
        return stock_excel.GENERAL_VARIETY
    return normalised


def _safe_component(value: str) -> str:
    safe = _INVALID_PATH_CHARS.sub("_", value.strip())
    safe = safe.rstrip(" .")
    if not safe or safe in {".", ".."}:
        raise RoutingError(f"Value cannot form a safe path component: {value!r}")
    return safe
