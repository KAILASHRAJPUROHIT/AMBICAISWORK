from pathlib import Path
import sys

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))
from p355_document_renderer import render


def image(path, color, text):
    doc = fitz.open(); page = doc.new_page(width=360, height=220)
    page.draw_rect(page.rect, fill=color); page.insert_text((30, 110), text, fontsize=18, color=(1, 1, 1))
    page.get_pixmap().save(str(path)); doc.close()


def main():
    out = Path(r"C:\PrintBridge\document_test_output")
    out.mkdir(parents=True, exist_ok=True)
    bill, front, terms = out / "TEST_ONLY_bill.pdf", out / "front.png", out / "terms.png"
    doc = fitz.open(); page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), "TEST ONLY — DO NOT PRINT TO CUSTOMER", fontsize=18)
    doc.save(bill); doc.close()
    image(front, (0.05, 0.17, 0.45), "ARADHANA TEST LETTERHEAD")
    image(terms, (0.3, 0.2, 0.08), "TEST TERMS")
    docs = []
    for index in range(3):
        path = out / f"TEST_ID_{index + 1}.png"; image(path, (0.1, 0.3, 0.2), f"TEST ID {index + 1}"); docs.append(path)
    output = out / "TEST_ONLY_P355_DOCUMENT_LAYOUT.pdf"
    render(bill, output, front, terms, docs, print_mode="id_card")
    with fitz.open(output) as result:
        print(f"OK: {output} ({result.page_count} pages; PDF only, nothing printed)")


if __name__ == "__main__":
    main()
