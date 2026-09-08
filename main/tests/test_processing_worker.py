import os
from pathlib import Path

import pytest

import processing_worker


@pytest.fixture
def roots(tmp_path):
    values = {
        name: tmp_path / name
        for name in ("processing", "processed", "needs_review", "rejected")
    }
    for root in values.values():
        root.mkdir()
    return values


def _queued(root: Path, relative: str, received_ns: int) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(relative.encode())
    os.utime(path, ns=(received_ns, received_ns))
    return path


@pytest.mark.parametrize(
    ("folder", "category"),
    [
        # Historical per-category form ("Label N") — still present on
        # archived/master-backup data captured before 2026-07-31.
        ("Earrings 10", "earrings"),
        ("JHUMKA 16", "earrings"),
        ("Ladies Rings 8", "ladies_rings"),
        ("Gents Ring 2", "gents_rings"),
        ("Mangalsutra (Short) 3", "mangalsutra_short"),
        ("BALI 21", "ladies_bali"),
        ("Locket 7", "locket"),
    ],
)
def test_category_is_derived_from_capture_folder(folder, category):
    assert processing_worker.category_from_tray_folder(folder) == category


@pytest.mark.parametrize(
    ("folder", "category"),
    [
        # Current global-sequence form ("N Label") — every REAL capture
        # folder uses this as of the 2026-07-31 renumbering
        # (tray_sequence_migration.py / capture_tool._tray_folder_name).
        # This exact case was missing until a real end-to-end run against
        # today's actual folders raised "Unknown capture tray category"
        # for every single one of them.
        ("10 Earrings", "earrings"),
        ("9 Ladies Rings", "ladies_rings"),
        ("33 Ladies Rings", "ladies_rings"),
        ("19 Gents Rings", "gents_rings"),
        ("32 Locket", "locket"),
    ],
)
def test_category_is_derived_from_global_sequence_folder(folder, category):
    assert processing_worker.category_from_tray_folder(folder) == category


def test_unknown_folder_fails_loudly():
    with pytest.raises(processing_worker.ProcessingWorkerError, match="Unknown"):
        processing_worker.category_from_tray_folder("Mystery 1")


@pytest.mark.parametrize(
    ("folder", "processing_key"),
    [
        # New real stock category labels (stock_category_map.py, verified
        # 2026-07-31), reused via their mapped OLD processing key so
        # existing backgrounds/models keep working unchanged.
        ("33 Ladies Ring 22", "ladies_rings"),
        ("1 Locket 18", "locket"),
        ("10 Tops 22", "tops"),
        ("5 Wati 22", "wati"),
    ],
)
def test_category_is_derived_from_new_stock_category_label(folder, processing_key):
    assert processing_worker.category_from_tray_folder(folder) == processing_key


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("1 Nath 22", "nath"),
        ("2 Nath 22", "nath"),
        ("3 Tikka 18", "maang_tika"),
        ("4 Bali 22", "bali"),
    ],
)
def test_all_real_and_legacy_categories_are_processable(folder, expected):
    assert processing_worker.category_from_tray_folder(folder) == expected


def test_queue_is_oldest_received_first_across_folders(roots):
    _queued(roots["processing"], "Locket 2/LC22_2.jpg", 300)
    oldest = _queued(roots["processing"], "Earrings 8/ER22_1.jpg", 100)
    _queued(roots["processing"], "Gents Rings 2/GR22_3.jpg", 200)

    queue = processing_worker.discover_processing_queue(roots["processing"])

    assert [item.source_path for item in queue] == [
        oldest,
        roots["processing"] / "Gents Rings 2/GR22_3.jpg",
        roots["processing"] / "Locket 2/LC22_2.jpg",
    ]
    assert queue[0].tag_code == "ER22_1"
    assert queue[0].category == "earrings"


def test_previously_blocked_category_joins_queue_in_timestamp_order(roots):
    ready = _queued(roots["processing"], "Locket 2/LC22_2.jpg", 100)
    nath = _queued(roots["processing"], "3 Nath 22/NT22_1.jpg", 50)

    queue = processing_worker.discover_processing_queue(roots["processing"])

    assert [item.source_path for item in queue] == [nath, ready]


def test_an_unrecognised_category_is_also_skipped_not_a_scan_crash(roots, capsys):
    ready = _queued(roots["processing"], "Locket 2/LC22_2.jpg", 100)
    _queued(roots["processing"], "Mystery 1/XX22_1.jpg", 50)

    queue = processing_worker.discover_processing_queue(roots["processing"])

    assert [item.source_path for item in queue] == [ready]
    assert "skipping" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("status", "destination"),
    [
        ("processed", "processed"),
        ("needs_review", "needs_review"),
        ("rejected", "rejected"),
    ],
)
def test_successful_processor_outcome_atomically_transitions_source(
    roots, status, destination
):
    source = _queued(
        roots["processing"], "Earrings 8/ER22_1.jpg", 100
    )
    worker = processing_worker.ProcessingWorker(**{
        f"{name}_root": path for name, path in roots.items()
    })

    result = worker.process_next(
        lambda item: processing_worker.ProcessingOutcome(
            status=status,
            reason="test",
        )
    )

    expected = roots[destination] / "Earrings 8/ER22_1.jpg"
    assert result.lifecycle_path == expected
    assert expected.read_bytes() == b"Earrings 8/ER22_1.jpg"
    assert not source.exists()


def test_processor_exception_leaves_oldest_item_queued(roots):
    source = _queued(
        roots["processing"], "Earrings 8/ER22_1.jpg", 100
    )
    worker = processing_worker.ProcessingWorker(**{
        f"{name}_root": path for name, path in roots.items()
    })

    def fail(item):
        raise RuntimeError("engine offline")

    with pytest.raises(RuntimeError, match="engine offline"):
        worker.process_next(fail)

    assert source.exists()
    assert not any(roots["processed"].rglob("*"))
    assert not any(roots["needs_review"].rglob("*"))
    assert not any(roots["rejected"].rglob("*"))


def test_hidden_and_tag_archive_images_are_not_queued(roots):
    _queued(
        roots["processing"],
        "Earrings 8/_tag_archive/ER22_1_tag.jpg",
        100,
    )
    _queued(roots["processing"], "_TEST/TEST_1.jpg", 50)

    assert processing_worker.discover_processing_queue(roots["processing"]) == ()
