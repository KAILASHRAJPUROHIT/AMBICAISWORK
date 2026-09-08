import importlib.util
from pathlib import Path

import pymupdf as fitz


RENDERER = Path(__file__).parents[1] / "renderer" / "p355_document_renderer.py"
spec = importlib.util.spec_from_file_location("renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def image(path: Path, color: tuple[float, float, float], width: int = 300, height: int = 180) -> None:
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.draw_rect(page.rect, fill=color)
    page.insert_text((30, 90), path.stem, fontsize=20, color=(1, 1, 1))
    pix = page.get_pixmap()
    pix.save(str(path))
    doc.close()


def bill(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(page.rect, fill=(1, 1, 1))
    page.insert_text((50, 120), "TEST BILL — NOT FOR CUSTOMER USE", fontsize=18)
    doc.save(path)
    doc.close()


def test_no_documents_keeps_two_pages(tmp_path):
    source, output = tmp_path / "bill.pdf", tmp_path / "out.pdf"
    front, terms = tmp_path / "front.png", tmp_path / "terms.png"
    bill(source); image(front, (0.1, 0.2, 0.6)); image(terms, (0.4, 0.2, 0.1))
    renderer.render(source, output, front, terms, [])
    with fitz.open(output) as document:
        assert document.page_count == 2


def test_full_page_documents_keep_one_scan_per_reverse(tmp_path):
    source, output = tmp_path / "bill.pdf", tmp_path / "out.pdf"
    front, terms = tmp_path / "front.png", tmp_path / "terms.png"
    bill(source); image(front, (0.1, 0.2, 0.6)); image(terms, (0.4, 0.2, 0.1))
    docs = []
    for index in range(5):
        path = tmp_path / f"page_{index}.png"
        image(path, (0.1 * index, 0.4, 0.2), width=180, height=300)
        docs.append(path)
    renderer.render(source, output, front, terms, docs)
    with fitz.open(output) as document:
        assert document.page_count == 6  # bill + one readable full-page scan per reverse


def test_six_id_cards_fit_on_one_reverse_with_size_cap(tmp_path):
    source, output = tmp_path / "bill.pdf", tmp_path / "out.pdf"
    front, terms = tmp_path / "front.png", tmp_path / "terms.png"
    bill(source); image(front, (0.1, 0.2, 0.6)); image(terms, (0.4, 0.2, 0.1))
    cards = []
    for index in range(6):
        path = tmp_path / f"card_{index}.png"; image(path, (0.1, 0.4, 0.2)); cards.append(path)
    renderer.render(source, output, front, terms, cards, print_mode="id_card")
    slots = renderer.card_slots(fitz.Rect(0, 0, 595, 842), 6)
    assert len(slots) == 6
    assert all(slot.width <= renderer.CARD_MAX_WIDTH + 0.01 and slot.height <= renderer.CARD_MAX_HEIGHT + 0.01 for slot in slots)
    with fitz.open(output) as document:
        assert document.page_count == 2
