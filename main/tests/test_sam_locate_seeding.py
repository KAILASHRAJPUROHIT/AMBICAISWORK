"""
Unit tests for sam_locate.py's DINO-seeded mask selection.

These do NOT load real SAM2/Grounding DINO models (that needs a GPU-class
machine and real weights) -- they monkeypatch _predictor() and _dino_boxes()
with fixtures and check that locate()'s selection logic behaves correctly:
picks the highest-confidence mask among ones that pass the containment
filter, ignores masks that sprawl outside the seed box or grab most of the
frame, and falls back to the seed box itself when nothing passes.
"""
import numpy as np
import pytest

import sam_locate


class _FakePredictor:
    def __init__(self, masks, scores):
        self._masks = masks
        self._scores = scores

    def set_image(self, rgb):
        pass

    def predict(self, point_coords, point_labels, box, multimask_output):
        return self._masks, self._scores, None


def _rect_mask(shape, x0, y0, x1, y1):
    m = np.zeros(shape, dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


@pytest.fixture(autouse=True)
def _reset_globals(monkeypatch):
    monkeypatch.setattr(sam_locate, "_pred", None)
    monkeypatch.setattr(sam_locate, "_last_mask", None)
    yield


def test_locate_picks_highest_confidence_contained_mask(monkeypatch):
    shape = (200, 200)
    bgr = np.zeros((200, 200, 3), dtype=np.uint8)
    seed_box = [50, 50, 150, 150]

    # Three candidate masks: one is the "hand" (high confidence, sprawls well
    # outside the box), one is a tiny noise blob, one is the jewellery
    # (properly contained, lower raw confidence than the hand but the only
    # one that survives the containment filter).
    hand = _rect_mask(shape, 0, 0, 200, 200)          # whole frame -> filtered by coverage cap
    noise = _rect_mask(shape, 10, 10, 15, 15)          # too small -> filtered by area
    jewel_low_conf = _rect_mask(shape, 60, 60, 140, 140)
    jewel_high_conf = _rect_mask(shape, 65, 65, 135, 135)

    masks = [hand, noise, jewel_low_conf, jewel_high_conf]
    scores = [0.95, 0.10, 0.40, 0.88]

    monkeypatch.setattr(sam_locate, "_predictor", lambda: _FakePredictor(masks, scores))
    monkeypatch.setattr(sam_locate, "_dino_boxes", lambda bgr, expect: [seed_box])
    monkeypatch.setattr(sam_locate, "_centre_seed_from_boxes",
                         lambda boxes, bgr: [(100, 100)])

    boxes = sam_locate.locate(bgr, expect=1, margin=0.0)

    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    # Should match jewel_high_conf's extent (65..135), not jewel_low_conf's
    # wider one -- confidence, not gold-fraction, decided the tiebreak.
    assert (x0, y0, x1, y1) == (65, 65, 134, 134)


def test_locate_falls_back_to_seed_box_when_nothing_survives(monkeypatch):
    shape = (200, 200)
    bgr = np.zeros((200, 200, 3), dtype=np.uint8)
    seed_box = [50, 50, 150, 150]

    # Only a whole-frame grab and a tiny noise blob -- neither should survive
    # the geometric filters, so locate() should fall back to the seed box.
    hand = _rect_mask(shape, 0, 0, 200, 200)
    noise = _rect_mask(shape, 10, 10, 15, 15)
    masks = [hand, noise]
    scores = [0.99, 0.05]

    monkeypatch.setattr(sam_locate, "_predictor", lambda: _FakePredictor(masks, scores))
    monkeypatch.setattr(sam_locate, "_dino_boxes", lambda bgr, expect: [seed_box])
    monkeypatch.setattr(sam_locate, "_centre_seed_from_boxes",
                         lambda boxes, bgr: [(100, 100)])

    boxes = sam_locate.locate(bgr, expect=1, margin=0.0)

    assert boxes == [(50, 50, 150, 150)]


def test_centre_seed_from_boxes_falls_back_to_image_centre():
    bgr = np.zeros((80, 120, 3), dtype=np.uint8)
    assert sam_locate._centre_seed_from_boxes([], bgr) == [(60, 40)]


def test_centre_seed_from_boxes_uses_box_centroids_left_to_right():
    bgr = np.zeros((100, 100, 3), dtype=np.uint8)
    boxes = [[60, 10, 80, 30], [10, 10, 30, 30]]
    pts = sam_locate._centre_seed_from_boxes(boxes, bgr)
    assert pts == [(20, 20), (70, 20)]
