"""
category_topology.py — piece count and topology derived from the CATEGORY.

WHY
---
The operator was being asked, per batch, to state piece count, relationship,
and three topology constraints. That is data the category already determines:
a BALI is always a pair, an EARRING is always a pair, a NECKLACE SET is always
two earrings plus a necklace. Asking a human to re-enter a constant is a
reliable way to eventually get it wrong, and the panel was five controls deep
before anything could be processed.

So the answer is looked up here instead. The only genuinely ambiguous case is
WATI, which ships as either one ornament or two, and that is decided by
looking at the actual photograph rather than guessing from the name.
"""
from __future__ import annotations

from ornament_placement import normalise_category

# Always a matched pair.
_PAIR = {
    "bali", "ladies_bali", "mens_bali", "bangles", "dul", "earrings",
    "jhumka", "kaan_chain", "baby_kadli", "mangota", "tops",
}

# Two earrings + one necklace shipped as one SKU.
_SET = {"necklace_set", "pendant_set"}

# Genuinely varies per item — resolved from the image, never assumed.
_AMBIGUOUS = {"wati"}


def _resolve(category: str) -> str:
    """Map a REAL folder name onto a canonical category key.

    normalise_category expects a clean name. The archive does not have one:
    every folder is stock-numbered — "56 TOPS 22", "10 EARRING 22",
    "6 BALI 22" — and all of them normalised to 'generic' (measured across all
    18 capture_intake folders, 2026-08-09). Falling through to 'generic' made
    topology_for return SINGLE for every paired category, so the output gate
    expected 1 piece, a correct pair rendered 2, and the item was rejected as
    PIECE_COUNT_MISMATCH. Wati never reached its ambiguous branch either.

    So the stock numbers are stripped before normalising, and if the result is
    still 'generic' the words are matched directly — with singular/plural and
    the local spelling "pendent" folded in, because "56 TOPS 22" and "55 TOPS
    18" must resolve identically.
    """
    import re

    raw = (category or "").strip()
    cleaned = re.sub(r"\d+", " ", raw).strip()

    for candidate in (raw, cleaned, cleaned.replace(" ", "_")):
        try:
            got = normalise_category(candidate)
        except Exception:
            continue
        if got and got != "generic":
            return got

    # Word-level fallback. Longest key first so "earring" is never shadowed by
    # "ring" — an earring is a PAIR and a ring is SINGLE, and getting that
    # backwards duplicates a ring or halves a pair.
    words = re.sub(r"[^a-z]+", " ", cleaned.lower())
    known = sorted(_PAIR | _SET | _AMBIGUOUS, key=len, reverse=True)
    for key in known:
        base = key.replace("_", " ")
        for variant in (base, base.rstrip("s"), base + "s"):
            if re.search(r"\b" + re.escape(variant) + r"\b", words):
                return key
    # Local spellings and singulars the sets don't carry verbatim.
    for word, key in (("pendent", "pendant"), ("pendant", "pendant"),
                      ("earring", "earrings"), ("bangle", "bangles"),
                      ("dull", "dul")):
        if re.search(r"\b" + word + r"s?\b", words):
            return key if key in (_PAIR | _SET | _AMBIGUOUS) else "generic"
    return "generic"


def topology_for(category: str, jewel_path: str | None = None) -> dict:
    """Return {visible_piece_count, relationship, independent_objects, ...}.

    ``jewel_path`` is only consulted for the ambiguous categories; every other
    answer is a constant and needs no image.
    """
    cat = _resolve(category)

    if cat in _SET:
        # Independent stays True: the necklace and the two earrings are
        # separate objects even though they are sold together, and Klein has
        # previously fused pieces that were merely near each other.
        return _mk(3, "SET", source="category")

    if cat in _PAIR:
        return _mk(2, "PAIR", source="category")

    if cat in _AMBIGUOUS:
        n = _count_pieces(jewel_path)
        if n >= 2:
            # A Wati's two elements are PHYSICALLY JOINED — it is the centre
            # component of a Maharashtrian mangalsutra, two cups on a shared
            # body, not a matched pair.
            #
            # Left as independent_objects this fired the anti-fusion clause
            # ("completely separate objects, keep them fully detached"), which
            # exists for earrings after Klein fused ER22_1 at the bail. Klein
            # obeyed and pulled every Wati apart: the 2026-08-08 batch of 29
            # was rejected in full, every note reading "not joined".
            #
            # So a two-element Wati declares its connection instead, which
            # selects the "physically joined, keep the existing connection
            # exactly as it appears" clause.
            return _mk(2, "TWO_ELEMENT_SKU", source="image",
                       independent_objects=False,
                       physical_connection_allowed=True)
        return _mk(1, "SINGLE", source="image" if n else "fallback")

    return _mk(1, "SINGLE", source="default")


def _mk(count: int, relationship: str, source: str,
        independent_objects: bool = True,
        physical_connection_allowed: bool = False) -> dict:
    return {
        "visible_piece_count": count,
        "relationship": relationship,
        # Pieces of a pair or set are separate objects. This is the flag that
        # tells Klein not to fuse two earrings at the bail — the ER22_1 defect.
        # Overridden for SKUs whose elements are genuinely joined, such as a
        # Wati, where the same clause causes the opposite defect.
        "independent_objects": independent_objects,
        "shared_components_allowed": False,
        "physical_connection_allowed": physical_connection_allowed,
        "operator_confirmed": False,
        "source": f"category_topology:{source}",
    }


def _count_pieces(jewel_path: str | None) -> int:
    """How many ornaments are actually in this photo? 0 when undecidable.

    Used only for WATI. Deliberately conservative: an uncertain answer returns
    0 so the caller falls back to SINGLE rather than inventing a second piece
    that does not exist — duplicating a single Wati is a documented failure in
    this repo's own rules.
    """
    if not jewel_path:
        return 0
    try:
        import cv2
        import sam_locate as sl

        bgr = cv2.imread(jewel_path)
        if bgr is None:
            return 0
        boxes = sl.focus_boxes(bgr, expect=2)
        if len(boxes) < 2:
            return len(boxes)
        # Two boxes only count as two pieces if they are of comparable size;
        # a large ornament plus a small bright speck is one piece and noise.
        a0 = (boxes[0][2] - boxes[0][0]) * (boxes[0][3] - boxes[0][1])
        a1 = (boxes[1][2] - boxes[1][0]) * (boxes[1][3] - boxes[1][1])
        if min(a0, a1) < 0.35 * max(a0, a1):
            return 1
        return 2
    except Exception:
        return 0
