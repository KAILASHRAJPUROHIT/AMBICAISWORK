"""Antigravity-backed jewellery scanner with conservative conflict gates.

This module never generates an image and never uses the GPU. It reads tight
ornament references through the signed-in Antigravity CLI, validates the JSON
envelope, and writes the existing ``.<stem>.design.json`` cache format.

The scanner deliberately separates *description* from *acceptance*. Model
confidence is not evidence. A dual scan is auto-approved only when the two
readers agree on identity-critical counts and material classes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable


BASE = Path(__file__).resolve().parent
AGY = BASE / "tools" / "antigravity-cli" / "agy.exe"
SCHEMA = BASE / "tools" / "antigravity-cli" / "jewellery_batch_schema.json"

MODEL_GEMINI = "Gemini 3.1 Pro (High)"
MODEL_SONNET = "Claude Sonnet 4.6 (Thinking)"
MODEL_OPUS = "Claude Opus 4.6 (Thinking)"

_SIMPLE_CATEGORY_WORDS = {"tops", "top", "stud", "studs", "nosepin", "nose pin"}
_FEATURES = {
    "stone_rows": ("stone row", "stone channel"),
    "rails": ("rail", "divider", "track"),
    "panels": ("panel", "mesh"),
    "scrolls": ("scroll", "filigree curl", "s curve", "c curve"),
    "terminal_caps": ("terminal cap", "finial", "end cap"),
    "drops": ("drop", "pearl"),
    "fringes": ("fringe", "dangling chain", "hanging strand"),
}
_IDENTITY_UNCERTAINTY = re.compile(
    r"\b(shape|count|row|rail|track|panel|mesh|scroll|terminal|cap|stone|"
    r"colour|color|metal|obstruct|hidden|occlud|quantity|piece|symmetr)\b",
    re.I,
)


def model_for_category(category: str) -> str:
    """Route simple concentric studs to Gemini; geometry-heavy work to Sonnet."""
    normal = re.sub(r"[^a-z]+", " ", (category or "").lower()).strip()
    return MODEL_GEMINI if any(word in normal for word in _SIMPLE_CATEGORY_WORDS) else MODEL_SONNET


def record_path(image_path: str | os.PathLike[str]) -> Path:
    image = Path(image_path)
    return image.with_name(f".{image.stem}.design.json")


def _normal(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _material_signature(record: dict) -> tuple[str, ...]:
    text = _normal(record.get("metal_colour"))
    classes = []
    if "yellow gold" in text or text == "gold":
        classes.append("yellow_gold")
    if any(word in text for word in ("white gold", "rhodium", "silver", "white metal")):
        classes.append("white_metal")
    if "rose gold" in text:
        classes.append("rose_gold")
    return tuple(sorted(set(classes)))


def hard_signature(record: dict) -> dict:
    """Extract comparable identity facts from otherwise free-form records."""
    signature: dict[str, object] = {
        "quantity": int(record.get("quantity") or 0),
        "material": _material_signature(record),
    }
    components = record.get("components") or []
    for feature, words in _FEATURES.items():
        total = 0
        found = False
        for component in components:
            name = _normal(component.get("name"))
            if any(word in name for word in words):
                count = component.get("count")
                if isinstance(count, int) and count > 0:
                    total += count
                    found = True
        if found:
            signature[feature] = total
    return signature


def compare_records(primary: dict, secondary: dict) -> list[str]:
    """Return identity-critical disagreements. Missing facts do not fabricate agreement."""
    left, right = hard_signature(primary), hard_signature(secondary)
    conflicts = []
    for key in sorted(set(left) & set(right)):
        if left[key] != right[key]:
            conflicts.append(f"{key}: {left[key]!r} != {right[key]!r}")
    return conflicts


def normalize_record(record: dict, expected_category: str = "") -> dict:
    """Sanitize one model record and apply conservative review rules."""
    out = dict(record)
    out["item_type"] = expected_category or str(out.get("item_type") or "jewellery")
    out["quantity"] = max(1, int(out.get("quantity") or 1))
    out["pair"] = out["quantity"] == 2
    out.setdefault("joined", False)
    out["components"] = [dict(c) for c in (out.get("components") or [])[:15] if isinstance(c, dict)]
    uncertainties = [str(x).strip() for x in (out.get("uncertain_features") or []) if str(x).strip()]
    identity_uncertain = any(_IDENTITY_UNCERTAINTY.search(x) for x in uncertainties)
    if identity_uncertain:
        out["review_required"] = True
        out["confidence"] = min(float(out.get("confidence") or 0), 0.80)
    out["scanner_identity_uncertain"] = identity_uncertain
    return out


def merge_dual(primary: dict, secondary: dict, expected_category: str = "") -> dict:
    """Keep the primary description; attach evidence and block on disagreements."""
    first = normalize_record(primary, expected_category)
    second = normalize_record(secondary, expected_category)
    conflicts = compare_records(first, second)
    first["scanner"] = {
        "primary_model": MODEL_SONNET,
        "secondary_model": MODEL_OPUS,
        "hard_signature_primary": hard_signature(first),
        "hard_signature_secondary": hard_signature(second),
        "conflicts": conflicts,
    }
    first["review_required"] = bool(
        first.get("review_required") or second.get("review_required") or conflicts
    )
    first["auto_approved"] = not first["review_required"]
    return first


def build_prompt(items: list[dict]) -> str:
    manifest = "\n".join(
        f"- source_id={item['source_id']}; expected_category={item['category']}; image={item['staged_path']}"
        for item in items
    )
    return f"""Inspect every jewellery image below. Return one record per image in the same order.
{manifest}

Treat expected_category as authoritative. Analyze jewellery only; ignore tags, QR codes, supports, fingers and background.
Describe identity-critical layers in physical order. Count pieces, stone rows, metal divider rails, panels, scrolls, terminal caps and dangling elements separately. Never merge different shapes under one name.
Distinguish stones, enamel, holes, gaps, glare, dark reflections and metal colour. Use null when a micro-count cannot be verified. List obstruction and ambiguity. Set review_required=true for uncertain identity-critical shape, count, material or topology.
Do not edit files, run commands, browse, or read tags."""


def _extract_envelope(text: str, expected: int) -> tuple[list[dict], dict]:
    envelope = json.loads(text)
    if envelope.get("status") != "SUCCESS":
        raise RuntimeError(envelope.get("error") or "Antigravity scan failed")
    structured = envelope.get("structured_output") or {}
    records = structured.get("items")
    if not isinstance(records, list) or len(records) != expected:
        raise RuntimeError(f"Expected {expected} records, received {len(records or [])}")
    return records, envelope.get("usage") or {}


def run_batch(images: Iterable[tuple[str, str, str]], model: str) -> tuple[list[dict], dict]:
    """Run a signed-in Antigravity model. ``images`` = (path, source_id, category)."""
    if not AGY.exists() or not SCHEMA.exists():
        raise FileNotFoundError("Antigravity CLI or scanner schema is not installed")
    rows = list(images)
    if not rows:
        return [], {}
    with tempfile.TemporaryDirectory(prefix="jewellery_agy_scan_") as temp:
        staged = []
        for index, (path, source_id, category) in enumerate(rows):
            source = Path(path)
            destination = Path(temp) / f"{index:02d}_{source_id}{source.suffix.lower()}"
            shutil.copy2(source, destination)
            staged.append({
                "source_id": source_id,
                "category": category,
                "staged_path": str(destination),
            })
        command = [
            str(AGY), "--model", model, "--mode", "plan", "--sandbox",
            "--dangerously-skip-permissions", "--new-project",
            "--output-format", "json", "--json-schema", str(SCHEMA),
            "--print-timeout", "10m", "-p", build_prompt(staged),
        ]
        completed = subprocess.run(
            command, cwd=temp, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=660,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or f"Antigravity exited {completed.returncode}")
        return _extract_envelope(completed.stdout, len(rows))


def save_records(rows: list[tuple[str, str]], records: list[dict], model: str, usage: dict) -> None:
    for (image_path, category), raw in zip(rows, records):
        record = normalize_record(raw, category)
        record["scanner"] = {"model": model, "usage_batch": usage}
        destination = record_path(image_path)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan jewellery images through Antigravity")
    parser.add_argument("images", nargs="+", help="image paths")
    parser.add_argument("--category", required=True)
    parser.add_argument("--model", default="auto", choices=("auto", "gemini", "sonnet", "opus"))
    args = parser.parse_args()
    models = {"gemini": MODEL_GEMINI, "sonnet": MODEL_SONNET, "opus": MODEL_OPUS}
    model = model_for_category(args.category) if args.model == "auto" else models[args.model]
    request = [(path, Path(path).stem, args.category) for path in args.images]
    records, usage = run_batch(request, model)
    save_records([(path, args.category) for path in args.images], records, model, usage)
    print(json.dumps({"scanned": len(records), "model": model, "usage": usage}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
