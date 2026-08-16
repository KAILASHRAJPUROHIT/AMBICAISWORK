"""Loads and validates a FLUX.2 edit-training manifest (CSV) into approved,
correctly-categorised training samples.

Manifest columns: sample_id, tag, category, task, split, reference, target,
approved, license, license_source.

Real rules, in the order they're actually checked:
  1. approved != "yes" -> row is silently skipped, WITHOUT even touching the
     reference/target files on disk. A rejected/pending row's image paths
     may not exist yet (still mid-shoot, still awaiting sign-off) and that
     must never surface as a dataset-build error.
  2. license must be one of the approved/owned values below — an unlicensed
     or unknown-provenance image pair can never enter a training set.
  3. category must be a real, current stock category label (exact match
     against ornament_code_map.CATEGORIES) — this is what gets normalised
     into stock_key, then canonicalised via stock_category_map.processing_key
     (e.g. "LADIES RING 22" -> stock_key "ladies_ring_22" -> canonical
     "ladies_rings", the same category-normalisation the live pipeline uses).
  4. reference and target must both exist on disk.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import ornament_code_map
import stock_category_map

# Only these license values represent imagery Ambic/AMBIC actually has
# the rights to train on. Anything else (blank, "unknown", a customer's own
# photo with no transfer of rights, ...) must never enter a training set.
_ALLOWED_LICENSES = {"company-owned", "licensed", "public-domain"}

# How many approved samples a category needs before it's honestly reportable
# as "ready for category-complete training" — deliberately conservative and
# a placeholder pending a real per-category minimum from whoever runs the
# actual training; the point is a 1-sample category must never be reported
# as ready just because it has an entry.
_MIN_SAMPLES_PER_CATEGORY = 5


@dataclass(frozen=True, slots=True)
class Sample:
    sample_id: str
    tag: str
    stock_key: str
    canonical_category: str
    task: str
    split: str
    reference: str
    target: str
    instruction: str


def _stock_key_for_label(label: str) -> str | None:
    normalised = " ".join(str(label).strip().casefold().split())
    for category in ornament_code_map.CATEGORIES:
        if category.label.strip().casefold() == normalised:
            return category.key
    return None


def _instruction_for(task: str) -> str:
    return f"AJ_{str(task).strip().upper()}_EDIT: preserve exact design, only change what the task specifies."


def load_manifest(path: str | Path) -> tuple[list[Sample], list[str]]:
    samples: list[Sample] = []
    errors: list[str] = []

    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sample_id = row.get("sample_id", "") or "<no sample_id>"

            if str(row.get("approved", "")).strip().lower() != "yes":
                continue

            license_value = str(row.get("license", "")).strip().lower()
            if license_value not in _ALLOWED_LICENSES:
                errors.append(
                    f"{sample_id}: license {row.get('license')!r} is not an approved/owned license"
                )
                continue

            stock_key = _stock_key_for_label(row.get("category", ""))
            if stock_key is None:
                errors.append(f"{sample_id}: unrecognised category {row.get('category')!r}")
                continue

            reference = row.get("reference", "")
            target = row.get("target", "")
            if not Path(reference).is_file() or not Path(target).is_file():
                errors.append(f"{sample_id}: reference/target image missing on disk")
                continue

            canonical_category = stock_category_map.processing_key(stock_key) or stock_key
            task = row.get("task", "")
            samples.append(Sample(
                sample_id=sample_id,
                tag=row.get("tag", ""),
                stock_key=stock_key,
                canonical_category=canonical_category,
                task=task,
                split=row.get("split", ""),
                reference=reference,
                target=target,
                instruction=_instruction_for(task),
            ))

    return samples, errors


def coverage(samples: list[Sample]) -> dict:
    by_category: dict[str, int] = {}
    for sample in samples:
        by_category[sample.canonical_category] = by_category.get(sample.canonical_category, 0) + 1

    ready = bool(by_category) and all(
        count >= _MIN_SAMPLES_PER_CATEGORY for count in by_category.values()
    )
    return {
        "total_samples": len(samples),
        "categories": by_category,
        "ready_for_category_complete_training": ready,
    }
