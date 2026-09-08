"""calibration_repository.py: per-category 3-angle calibration profile
persistence for the RSC 2 multi-shot workflow.

Uses a temp file per test (never the real data/capture_calibration.json) so
this suite can't corrupt production calibration data or depend on it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import calibration_repository as cr
import ornament_code_map as ocm


@pytest.fixture
def repo(tmp_path):
    return cr.CalibrationRepository(path=str(tmp_path / "calibration.json"))


def _pose(yaw=0.0, pitch=0.0, roll=0.0):
    return cr.CapturePose(yaw=yaw, pitch=pitch, roll=roll)


def test_missing_profile_returns_none(repo):
    assert repo.get_profile("earring_22") is None


def test_save_and_get_round_trip(repo):
    profile = cr.CategoryCaptureProfile(
        category_key="earring_22",
        display_name="EARRING 22",
        status=cr.STATUS_CALIBRATED,
        main=_pose(0.4, -12.2, 0.3),
        angle1=_pose(-27.8, -9.7, 0.5),
        angle2=_pose(28.1, -9.9, 0.4),
    )
    repo.save_profile(profile)
    loaded = repo.get_profile("earring_22")
    assert loaded is not None
    assert loaded.status == cr.STATUS_CALIBRATED
    assert loaded.main.yaw == pytest.approx(0.4)
    assert loaded.angle1.pitch == pytest.approx(-9.7)


def test_save_updates_updated_at_but_not_created_at(repo):
    profile = cr.CategoryCaptureProfile(
        category_key="ring_test", display_name="RING TEST", status=cr.STATUS_CALIBRATED,
        main=_pose(), angle1=_pose(10), angle2=_pose(-10),
    )
    repo.save_profile(profile)
    first = repo.get_profile("ring_test")
    repo.save_profile(cr.CategoryCaptureProfile(
        category_key="ring_test", display_name="RING TEST", status=cr.STATUS_CALIBRATED,
        main=_pose(1), angle1=_pose(11), angle2=_pose(-11),
        created_at=first.created_at,
    ))
    second = repo.get_profile("ring_test")
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    assert second.main.yaw == pytest.approx(1)


def test_copy_profile_is_a_real_copy_not_a_reference(repo):
    """Spec rule 27: editing the source after a copy must not change the
    destination."""
    source = cr.CategoryCaptureProfile(
        category_key="jhumka_22", display_name="JHUMKA 22", status=cr.STATUS_CALIBRATED,
        main=_pose(0, -12, 0), angle1=_pose(-27, -9, 0), angle2=_pose(27, -9, 0),
    )
    repo.save_profile(source)

    copied = repo.copy_profile("jhumka_22", "earring_22")
    assert copied.status == cr.STATUS_COPIED
    assert copied.derived_from_category_key == "jhumka_22"
    assert copied.main.yaw == pytest.approx(0)

    # Now edit the SOURCE.
    repo.save_profile(cr.CategoryCaptureProfile(
        category_key="jhumka_22", display_name="JHUMKA 22", status=cr.STATUS_CALIBRATED,
        main=_pose(99, 99, 99), angle1=_pose(-27, -9, 0), angle2=_pose(27, -9, 0),
    ))

    destination = repo.get_profile("earring_22")
    assert destination.main.yaw == pytest.approx(0), "copy must not track source edits"


def test_copy_from_uncalibrated_source_raises(repo):
    with pytest.raises(ValueError):
        repo.copy_profile("does_not_exist", "earring_22")


def test_delete_profile(repo):
    repo.save_profile(cr.CategoryCaptureProfile(
        category_key="bangle_22", display_name="BANGLE 22", status=cr.STATUS_CALIBRATED,
        main=_pose(), angle1=_pose(10), angle2=_pose(-10),
    ))
    assert repo.get_profile("bangle_22") is not None
    repo.delete_profile("bangle_22")
    assert repo.get_profile("bangle_22") is None
    # Deleting a nonexistent key must not raise.
    repo.delete_profile("bangle_22")


def test_calibration_status_reflects_ornament_code_map_not_a_hardcoded_count(repo):
    status = repo.get_calibration_status()
    assert status["total"] == len(ocm.CATEGORIES)
    assert status["configured"] == 0
    assert status["remaining"] == len(ocm.CATEGORIES)

    repo.save_profile(cr.CategoryCaptureProfile(
        category_key=ocm.CATEGORIES[0].key, display_name=ocm.CATEGORIES[0].label,
        status=cr.STATUS_CALIBRATED, main=_pose(), angle1=_pose(10), angle2=_pose(-10),
    ))
    status = repo.get_calibration_status()
    assert status["configured"] == 1
    assert status["remaining"] == len(ocm.CATEGORIES) - 1
    row = next(r for r in status["categories"] if r["category_key"] == ocm.CATEGORIES[0].key)
    assert row["status"] == cr.STATUS_CALIBRATED


def test_export_import_round_trip(repo, tmp_path):
    repo.save_profile(cr.CategoryCaptureProfile(
        category_key="tops_22", display_name="TOPS 22", status=cr.STATUS_CALIBRATED,
        main=_pose(1, 2, 3), angle1=_pose(4, 5, 6), angle2=_pose(7, 8, 9),
    ))
    backup = repo.export_backup()
    assert "tops_22" in backup["profiles"]

    fresh = cr.CalibrationRepository(path=str(tmp_path / "restored.json"))
    imported = fresh.import_backup(backup)
    assert imported == 1
    restored = fresh.get_profile("tops_22")
    assert restored.main.yaw == pytest.approx(1)


def test_import_does_not_overwrite_by_default(repo):
    repo.save_profile(cr.CategoryCaptureProfile(
        category_key="chain_22", display_name="CHAIN 22", status=cr.STATUS_CALIBRATED,
        main=_pose(1), angle1=_pose(2), angle2=_pose(3),
    ))
    backup = {"profiles": {"chain_22": cr.CategoryCaptureProfile(
        category_key="chain_22", display_name="CHAIN 22", status=cr.STATUS_CALIBRATED,
        main=_pose(999), angle1=_pose(2), angle2=_pose(3),
    ).as_dict()}}
    repo.import_backup(backup, overwrite=False)
    assert repo.get_profile("chain_22").main.yaw == pytest.approx(1)

    repo.import_backup(backup, overwrite=True)
    assert repo.get_profile("chain_22").main.yaw == pytest.approx(999)


def test_import_rejects_malformed_backup(repo):
    with pytest.raises(ValueError):
        repo.import_backup({"profiles": {"x": {"category_key": "x"}}})


def test_pose_separation_warns_on_near_identical_poses():
    main = _pose(0, -12, 0)
    angle1 = _pose(0.4, -12, 0)  # yaw-only tiny difference, spec's own example
    angle2 = _pose(27, -9, 0)
    warnings = cr.check_pose_separation(main, angle1, angle2)
    assert any("ANGLE_1" in w for w in warnings)
    assert not any("ANGLE_2" in w and "MAIN" in w for w in warnings)


def test_pose_separation_no_warnings_for_well_separated_poses():
    main = _pose(0, -12, 0)
    angle1 = _pose(-27, -9, 0)
    angle2 = _pose(27, -9, 0)
    assert cr.check_pose_separation(main, angle1, angle2) == []


def test_pose_separation_compares_full_orientation_not_yaw_only():
    """Spec rule 24: a pitch-only variation with identical yaw must still
    count as 'close' if the full-orientation distance is small, and must NOT
    be treated as automatically distinct just because pitch differs."""
    main = _pose(0, -12, 0)
    pitch_only_tiny_shift = _pose(0, -13, 0)
    warnings = cr.check_pose_separation(main, pitch_only_tiny_shift, _pose(27, -9, 0))
    assert any("ANGLE_1" in w for w in warnings)
