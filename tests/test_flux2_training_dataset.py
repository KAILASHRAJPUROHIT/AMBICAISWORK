import csv
from pathlib import Path

from PIL import Image

import pytest
_mod = pytest.importorskip(
    "training.build_flux2_edit_dataset",
    reason="training/ package does not exist on disk or in any branch history",
)
coverage, load_manifest = _mod.coverage, _mod.load_manifest


FIELDS = [
    "sample_id", "tag", "category", "task", "split", "reference", "target",
    "approved", "license", "license_source",
]


def _image(path: Path, colour):
    Image.new("RGB", (512, 512), colour).save(path)


def _manifest(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_builder_accepts_approved_owned_pair_and_canonicalises_category(tmp_path):
    reference = tmp_path / "reference.png"
    target = tmp_path / "target.png"
    _image(reference, "white")
    _image(target, "gold")
    manifest = tmp_path / "manifest.csv"
    _manifest(manifest, [{
        "sample_id": "LR22_1_studio",
        "tag": "LR22_1",
        "category": "LADIES RING 22",
        "task": "studio",
        "split": "train",
        "reference": str(reference),
        "target": str(target),
        "approved": "yes",
        "license": "company-owned",
        "license_source": "Aradhana",
    }])

    samples, errors = load_manifest(manifest)

    assert errors == []
    assert len(samples) == 1
    assert samples[0].stock_key == "ladies_ring_22"
    assert samples[0].canonical_category == "ladies_rings"
    assert samples[0].instruction.startswith("AJ_STUDIO_EDIT:")
    assert coverage(samples)["ready_for_category_complete_training"] is False


def test_builder_rejects_tag_category_mismatch_and_unlicensed_data(tmp_path):
    reference = tmp_path / "reference.png"
    target = tmp_path / "target.png"
    _image(reference, "white")
    _image(target, "gold")
    manifest = tmp_path / "manifest.csv"
    base = {
        "sample_id": "bad",
        "tag": "LR22_1",
        "category": "JHUMKA 22",
        "task": "studio",
        "split": "train",
        "reference": str(reference),
        "target": str(target),
        "approved": "yes",
        "license": "unknown",
        "license_source": "",
    }
    _manifest(manifest, [base])

    samples, errors = load_manifest(manifest)

    assert samples == []
    assert errors
    assert "license" in errors[0]


def test_unapproved_rows_are_ignored_without_reading_images(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _manifest(manifest, [{
        "sample_id": "rejected",
        "tag": "LR22_2",
        "category": "LADIES RING 22",
        "task": "studio",
        "split": "train",
        "reference": str(tmp_path / "missing-reference.png"),
        "target": str(tmp_path / "missing-target.png"),
        "approved": "no",
        "license": "company-owned",
        "license_source": "Aradhana",
    }])

    samples, errors = load_manifest(manifest)

    assert samples == []
    assert errors == []
