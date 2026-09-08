"""Safe P355 composition. Produces a PDF; never invokes a printer."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf as fitz

WHITE_BG_PATTERN = re.compile(rb"1 1 1 rg\s*\n[\d.]+ [\d.]+ [\d.]+ [\d.]+ re\s*\nf\*?\s*\n")
MARGIN = 24
TERMS_HEIGHT_RATIO = 0.50
CARD_MAX_WIDTH = 6 * 72 / 2.54
CARD_MAX_HEIGHT = 4 * 72 / 2.54


def strip_full_page_white_fill(doc: fitz.Document, page: fitz.Page) -> None:
    contents = page.get_contents()
    if contents:
        raw = doc.xref_stream(contents[0])
        cleaned, _ = WHITE_BG_PATTERN.subn(b"", raw, count=1)
        doc.update_stream(contents[0], cleaned)


def fit_rect(source: fitz.Rect, target: fitz.Rect) -> fitz.Rect:
    ratio = min(target.width / source.width, target.height / source.height)
    width, height = source.width * ratio, source.height * ratio
    return fitz.Rect(target.x0 + (target.width - width) / 2, target.y0 + (target.height - height) / 2,
                     target.x0 + (target.width + width) / 2, target.y0 + (target.height + height) / 2)


def source_rect(path: Path) -> fitz.Rect:
    with fitz.open(path) as source:
        return source[0].rect


def capped_slot(slot: fitz.Rect, max_width: float, max_height: float) -> fitz.Rect:
    width = min(slot.width, max_width)
    height = min(slot.height, max_height)
    return fitz.Rect(slot.x0 + (slot.width - width) / 2, slot.y0 + (slot.height - height) / 2,
                     slot.x0 + (slot.width + width) / 2, slot.y0 + (slot.height + height) / 2)


def insert_document(page: fitz.Page, slot: fitz.Rect, path: Path, rotate: int = 0) -> None:
    source_rect_value = source_rect(path)
    if rotate % 180:
        source_rect_value = fitz.Rect(0, 0, source_rect_value.height, source_rect_value.width)
    target = fit_rect(source_rect_value, slot)
    if path.suffix.lower() == ".pdf":
        source = fitz.open(path)
        try:
            page.show_pdf_page(target, source, 0, rotate=rotate)
        finally:
            source.close()
    else:
        page.insert_image(target, filename=str(path), rotate=rotate)


def document_slots(rect: fitz.Rect, count: int) -> list[fitz.Rect]:
    """Return equal document tiles in the lower half of a P355 reverse."""
    if count < 1 or count > 4:
        raise ValueError("A reverse page supports one to four documents")
    gap = 12
    top = rect.height * TERMS_HEIGHT_RATIO + gap
    bottom = rect.height - MARGIN
    left, right = MARGIN, rect.width - MARGIN
    lower = fitz.Rect(left, top, right, bottom)
    if count == 1:
        return [lower]
    if count == 2:
        mid = (lower.x0 + lower.x1 - gap) / 2
        return [fitz.Rect(lower.x0, lower.y0, mid, lower.y1),
                fitz.Rect(mid + gap, lower.y0, lower.x1, lower.y1)]
    mid_x = (lower.x0 + lower.x1 - gap) / 2
    mid_y = (lower.y0 + lower.y1 - gap) / 2
    return [fitz.Rect(lower.x0, lower.y0, mid_x, mid_y),
            fitz.Rect(mid_x + gap, lower.y0, lower.x1, mid_y),
            fitz.Rect(lower.x0, mid_y + gap, mid_x, lower.y1),
            fitz.Rect(mid_x + gap, mid_y + gap, lower.x1, lower.y1)][:count]


def card_slots(rect: fitz.Rect, count: int) -> list[fitz.Rect]:
    """Return capped Aadhaar/PAN card slots in the lower 50% of the reverse."""
    if count < 1 or count > 6:
        raise ValueError("A reverse page supports one to six card documents")
    gap = 12
    lower = fitz.Rect(MARGIN, rect.height * TERMS_HEIGHT_RATIO + gap,
                      rect.width - MARGIN, rect.height - MARGIN)
    if count == 1:
        columns, rows = 1, 1
    elif count == 2:
        columns, rows = 2, 1
    elif count <= 4:
        columns, rows = 2, 2
    else:
        columns, rows = 3, 2
    tile_width = (lower.width - gap * (columns - 1)) / columns
    tile_height = (lower.height - gap * (rows - 1)) / rows
    slots: list[fitz.Rect] = []
    for row in range(rows):
        for column in range(columns):
            if len(slots) == count:
                return slots
            tile = fitz.Rect(lower.x0 + column * (tile_width + gap),
                             lower.y0 + row * (tile_height + gap),
                             lower.x0 + column * (tile_width + gap) + tile_width,
                             lower.y0 + row * (tile_height + gap) + tile_height)
            slots.append(capped_slot(tile, CARD_MAX_WIDTH, CARD_MAX_HEIGHT))
    return slots


def insert_terms(page: fitz.Page, slot: fitz.Rect, terms_image: Path) -> None:
    """Terms always fill the upper half in horizontal reading orientation."""
    rect = source_rect(terms_image)
    insert_document(page, slot, terms_image, rotate=90 if rect.height > rect.width else 0)


def back_pages(doc: fitz.Document, rect: fitz.Rect, terms_image: Path,
               documents: list[Path], print_mode: str) -> None:
    if not documents:
        page = doc.new_page(width=rect.width, height=rect.height)
        page.insert_image(page.rect, filename=str(terms_image))
        return
    remaining = list(documents)
    while remaining:
        page = doc.new_page(width=rect.width, height=rect.height)
        terms_slot = fitz.Rect(MARGIN, MARGIN, rect.width - MARGIN, rect.height * TERMS_HEIGHT_RATIO - 6)
        insert_terms(page, terms_slot, terms_image)
        card_batch = print_mode == "id_card"
        # Full Page mode preserves legibility: one page scan per reverse,
        # rotated to use the horizontal lower half. ID-card mode can tile six.
        page_documents = min(6 if card_batch else 1, len(remaining))
        current = [remaining.pop(0) for _ in range(page_documents)]
        if card_batch:
            for slot, item in zip(card_slots(rect, len(current)), current):
                insert_document(page, slot, item)
        else:
            for slot, item in zip(document_slots(rect, len(current)), current):
                item_rect = source_rect(item)
                rotate = 90 if len(current) == 1 and item_rect.height > item_rect.width else 0
                insert_document(page, slot, item, rotate=rotate)


def render(input_bill: Path, output_pdf: Path, front_image: Path, terms_image: Path,
           documents: list[Path], print_mode: str = "pdf") -> None:
    if print_mode not in {"pdf", "id_card"}:
        raise ValueError("print_mode must be 'pdf' or 'id_card'")
    doc = fitz.open(input_bill)
    if doc.page_count != 1:
        raise ValueError("Expected one captured customer-copy bill page")
    front = doc[0]
    rect = front.rect
    strip_full_page_white_fill(doc, front)
    front.insert_image(rect, filename=str(front_image), overlay=False)
    back_pages(doc, rect, terms_image, documents, print_mode)
    doc.save(output_pdf)
    doc.close()


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        raise SystemExit("usage: renderer bill.pdf output.pdf front.jpeg terms.jpeg [manifest.json]")
    manifest = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8")) if len(sys.argv) == 6 else {}
    docs = [Path(item["local_path"]) for item in manifest.get("documents", [])]
    if any(not path.is_file() for path in docs):
        raise SystemExit("manifest references a missing local document")
    render(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), docs,
           str(manifest.get("print_mode") or "pdf"))
